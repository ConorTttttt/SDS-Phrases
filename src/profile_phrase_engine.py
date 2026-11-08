"""Profile-first recommendations of original eSDScom Core English phrase text.

This is an evidence/candidate *relevance* engine, NOT an SDS compliance
assessor, CLP classification calculator or verified precautionary selection
service. It derives phrase discovery cues from user-supplied classified H
codes and physical data, then verifies exact original source rows locally.
No source wording is in Git or synthesized by these rules.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from catalogue_browser import connect
from catalogue_index import SECTIONS
from section_recommendations import load_candidates

ROOT=Path(__file__).resolve().parents[1]
PACK_PATH=ROOT/"rules"/"eu_profile_phrase_relevance_v01.json"
SCHEMA="sds-phrase-profile-recommendations/v0.1"
CODE=re.compile(r"(?:H[2-4]\d{2}|EUH\d{3})\Z")
ALLOWED_FIELDS={
    "product_type":{"unknown","mixture","substance"},
    "physical_state":{"unknown","liquid","solid","gas"},
    "physical_form":{"unknown","powder","granules","other"},
    "colour":{"unknown","colourless","coloured"},
    "dust_generating":{"unknown","yes","no"},
    "volatile":{"unknown","yes","no"},
    "heat_sensitive":{"unknown","yes","no"},
    "sunlight_sensitive":{"unknown","yes","no"},
    "heat_pressure_risk":{"unknown","yes","no"},
    "professional_use":{"unknown","yes","no"},
}
ALLOWED_KEYS=set(ALLOWED_FIELDS)|{
    "hazards","jurisdiction","as_of","ph","flash_point_c","classification_reference"
}
KIND_PRIORITY={
    "reported_property":0,
    "profile_match":1,
    "classification_related":1,
    "property_related":2,
    "conditional_safety":3,
    "layout_fragment":4,
}
REVIEW_NOTICE=(
    "All phrases are exact local eSDScom source text only. Input-based "
    "relevance is not legally verified suitability. Do not publish without "
    "appropriate product-specific regulatory, medical, PPE, fire and "
    "transport review. A missing suggestion is not a missing legal requirement."
)


class ProfileRecommendationError(ValueError):
    pass


def check(condition,message):
    if not condition:
        raise ProfileRecommendationError(message)


def validate_profile(data):
    check(isinstance(data,dict),"Product profile must be an object.")
    check(set(data)<=ALLOWED_KEYS,"Unexpected product profile fields.")
    check(data.get("jurisdiction")=="EU","This profile-based recommendation pilot supports EU source structure only.")
    day=data.get("as_of")
    check(isinstance(day,str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}",day)),
          "Assessment date must be YYYY-MM-DD.")
    try:date.fromisoformat(day)
    except ValueError as exc:raise ProfileRecommendationError("Invalid assessment date.") from exc
    hazards=data.get("hazards",[])
    check(isinstance(hazards,list) and len(hazards)<=80,"Hazards must be a list of up to 80 H/EUH codes.")
    check(all(isinstance(h,str) and CODE.fullmatch(h) for h in hazards),"Enter Hnnn / EUHnnn codes.")
    check(len(hazards)==len(set(hazards)),"Duplicate hazard codes.")
    for key,choices in ALLOWED_FIELDS.items():
        value=data.get(key,"unknown")
        check(isinstance(value,str) and value in choices,f"{key} has an unsupported value.")
    for key,bounds in (("ph",(-2,16)),("flash_point_c",(-200,500))):
        val=data.get(key)
        check(val is None or (type(val) in (float,int) and bounds[0]<=val<=bounds[1]),
              f"{key} must be a number in the supported range or null.")
    reference=data.get("classification_reference","")
    check(isinstance(reference,str) and len(reference)<=400,
          "Classification reference must be text (up to 400 characters).")
    return {**{key:"unknown" for key in ALLOWED_FIELDS},
            **{key:None for key in ("ph","flash_point_c")},
            "classification_reference":"",**data}


def _condition(node,profile):
    """Return (matched, relevant input labels) for small, inspectable cues."""
    op,arg=next(iter(node.items()))
    if op=="all":
        parts=[_condition(x,profile) for x in arg]
        return all(p[0] for p in parts),sum((p[1] for p in parts if p[0]),[])
    if op=="any":
        parts=[_condition(x,profile) for x in arg]
        good=[p for p in parts if p[0]]
        return bool(good),sum((p[1] for p in good),[])
    if op=="hazards_any":
        hits=sorted(set(arg)&set(profile["hazards"]))
        return bool(hits),["hazard "+x for x in hits]
    if op=="has_any_hazards":
        hits=[h for h in profile["hazards"] if h.startswith("H")]
        return bool(hits),["hazard "+x for x in sorted(hits)]
    if op=="field_equals":
        actual=profile[arg["name"]]
        hit=actual==arg["value"]
        return hit,[arg["name"]+" = "+actual] if hit else []
    if op=="flash_point_below":
        actual=profile["flash_point_c"]
        hit=actual is not None and actual<arg
        return hit,[f"flash point {actual:g} °C (screening only)"] if hit else []
    if op=="ph_outside":
        actual=profile["ph"]
        hit=actual is not None and (actual<arg[0] or actual>arg[1])
        return hit,[f"pH {actual:g} (screening only)"] if hit else []
    raise ProfileRecommendationError("Unsupported profile relevance operator.")


def _validate_trigger(node,depth=0):
    check(depth<=7,"Relevance conditions are too deeply nested.")
    check(isinstance(node,dict) and len(node)==1,"Invalid profile cue.")
    op,arg=next(iter(node.items()))
    if op in ("all","any"):
        check(isinstance(arg,list) and 1<=len(arg)<=15,"Invalid cue group.")
        for item in arg:_validate_trigger(item,depth+1)
    elif op=="hazards_any":
        check(isinstance(arg,list) and 1<=len(arg)<=80 and
              len(arg)==len(set(arg)) and all(isinstance(h,str) and CODE.fullmatch(h) for h in arg),
              "Invalid H-statement relevance list.")
    elif op=="has_any_hazards":
        check(arg is True,"Invalid has_any_hazards cue.")
    elif op=="field_equals":
        check(isinstance(arg,dict) and set(arg)=={"name","value"} and
              arg["name"] in ALLOWED_FIELDS and arg["value"] in ALLOWED_FIELDS[arg["name"]],
              "Invalid reported property cue.")
    elif op=="flash_point_below":
        check(type(arg) in (int,float) and -200<=arg<=500,"Invalid flash point screening cue.")
    elif op=="ph_outside":
        check(isinstance(arg,list) and len(arg)==2 and
              all(type(x) in (float,int) for x in arg) and
              -2<=arg[0]<arg[1]<=16,"Invalid pH screening cue.")
    else:
        raise ProfileRecommendationError("Unknown profile trigger operator: "+str(op))


def load_pack():
    pack=json.loads(PACK_PATH.read_text(encoding="utf8"))
    check(pack.get("schema")==SCHEMA,"Invalid product-profile rule pack.")
    check(pack.get("status")=="draft_phrase_relevance_not_legally_verified",
          "A phrase rule pack cannot claim legal verification.")
    check(pack.get("jurisdiction")=="EU","Unexpected jurisdiction in profile pack.")
    current=load_candidates()
    known={r["id"]:r for r in current["rules"]}
    ids=set()
    rules=pack.get("rules")
    check(isinstance(rules,list) and 1<=len(rules)<=200,"Invalid profile recommendation list.")
    for rule in rules:
        check(isinstance(rule,dict),"Invalid profile relevance rule.")
        id=rule.get("rule_id")
        check(isinstance(id,str) and id in known and id not in ids,
              "Missing or duplicated curated source mapping: "+str(id))
        ids.add(id)
        _validate_trigger(rule.get("trigger"))
        check(rule.get("kind") in KIND_PRIORITY,"Unknown candidate kind.")
        check(type(rule.get("sort")) is int and 0<=rule["sort"]<=100,
              "Invalid relevance ordering.")
        check(isinstance(rule.get("why"),str) and bool(rule["why"].strip()),
              "Missing relevance explanation.")
        confirm=rule.get("confirm")
        check(isinstance(confirm,list) and len(confirm)>=1 and len(confirm)<=5 and
              all(isinstance(x,str) and 10<=len(x)<=500 for x in confirm),
              "Missing human review conditions.")
    return pack,known


def _conflicts(p):
    h=set(p["hazards"])
    state=p["physical_state"]
    conflicts=[]
    if state not in ("unknown","liquid") and h.intersection({"H224","H225","H226"}):
        conflicts.append("Flammable-liquid H224–H226 conflicts with reported non-liquid physical state. Recheck classification/state.")
    if state not in ("unknown","gas") and h.intersection({"H220","H221"}):
        conflicts.append("Flammable-gas H220/H221 conflicts with reported non-gas physical state.")
    if state not in ("unknown","solid") and "H228" in h:
        conflicts.append("Flammable-solid H228 conflicts with reported non-solid physical state.")
    if p["physical_form"]=="powder" and state not in ("unknown","solid"):
        conflicts.append("Powder physical form conflicts with reported non-solid physical state.")
    if {"H318","H319"}<=h:
        conflicts.append("H318 and H319 indicate different eye-hazard categories. Check that both should be present.")
    return conflicts


def _source_rows(db, rules):
    conn=connect(db)  # Also verifies that local Core catalogue was indexed.
    try:
        codes=sorted({r["structurecode"] for r in rules})
        placeholders=",".join("?" for _ in codes)
        records=[dict(r) for r in conn.execute(
            """SELECT e.entry_key,e.catalogue_version,e.collection,e.source_file,
                      e.excel_row,e.structurecode,e.esdscom_phrase_id,e.original_code,
                      e.english,e.sds_section,e.jurisdiction_structure,e.grammar,
                      e.source,e.info,i.wording_hash,i.phrase_kind,i.quality_flags
               FROM entries e LEFT JOIN catalogue_index i ON i.entry_key=e.entry_key
               WHERE e.collection='Core' AND e.structurecode IN (""" + placeholders +")",
            codes)]
    finally:conn.close()
    grouped={}
    for row in records:grouped.setdefault(row["structurecode"],[]).append(row)
    return grouped


def recommend_profile(db_path,product,pack=None,source_pack=None):
    p=validate_profile(product)
    if pack is None or source_pack is None:
        loaded,known=load_pack()
        pack=pack or loaded
        source_pack=source_pack or known
    check(pack.get("schema")==SCHEMA,"Unknown profile pack schema.")
    violations=_conflicts(p)
    output={i:[] for i in range(1,17)}
    if violations:
        return _response(p,output,violations,blocked=True)
    relevant=[]
    for item in pack["rules"]:
        matched,evidence=_condition(item["trigger"],p)
        if matched:
            relevant.append((item,source_pack[item["rule_id"]],list(dict.fromkeys(evidence))))
    if not relevant:
        return _response(p,output,[],blocked=False)
    originals=_source_rows(db_path,[r for _,r,_ in relevant])
    for item,ref,evidence in relevant:
        matches=originals.get(ref["structurecode"],[])
        row=matches[0] if len(matches)==1 else None
        flags=json.loads(row["quality_flags"]) if row and row.get("quality_flags") else []
        verified=bool(row and row["catalogue_version"]=="5.5" and
            row["collection"]=="Core" and row["jurisdiction_structure"]=="EU" and
            row["sds_section"]==ref["section"] and
            isinstance(row.get("wording_hash"),str) and
            bool(re.fullmatch(r"[0-9a-f]{64}",row["wording_hash"])) and
            row["english"] and
            hashlib.sha256(row["english"].encode("utf8")).hexdigest()==ref["expected_english_sha256"] and
            (ref.get("expected_grammar") is None or row["grammar"]==ref["expected_grammar"]) and
            not flags)
        section=ref["section"]
        candidate={
            "rule_id":item["rule_id"],"section":section,
            "subsection":ref.get("subsection_hint") or _section_context(ref),
            "topic":ref["topic"],"kind":item["kind"],"sort":item["sort"],
            "reason":item["why"],"matched_inputs":evidence,
            "confirmation_required":item["confirm"],
            "source_integrity":"exact_source_match" if verified else "blocked_catalogue_mismatch",
            "phrase":row["english"] if verified else None,
            "source":{key:row[key] for key in (
                "entry_key","catalogue_version","collection","source_file","excel_row",
                "structurecode","esdscom_phrase_id","original_code","sds_section",
                "wording_hash","grammar"
            )} if verified else None,
            "text_sha256":hashlib.sha256(row["english"].encode("utf8")).hexdigest() if verified else None,
            "is_fragment":bool(row and row["grammar"]!="Sentence"),
            "legal_applicability_verified":False,
            "approved_for_sds":False,
            "review_status":"draft_unreviewed",
        }
        output[section].append(candidate)
    return _response(p,output,[],blocked=False)


def _section_context(ref):
    context=ref.get("reference",{}).get("sds_content_context","")
    match=re.search(r"Part A (\d{1,2}\.\d{1,2})",context)
    return match.group(1) if match else ""


def _response(profile,grouped,conflicts,blocked):
    sections=[]
    for section,title in SECTIONS.items():
        recommendations=sorted(grouped[section],
            key=lambda r:(KIND_PRIORITY[r["kind"]],r["sort"],r["rule_id"]))
        sections.append({
            "section":section,"title":title,"candidates":recommendations,
            "source_matches":sum(r["source_integrity"]=="exact_source_match" for r in recommendations),
            "unmatched_source":sum(r["source_integrity"]!="exact_source_match" for r in recommendations),
            "section_complete":False,
        })
    return {
        "schema":SCHEMA,"jurisdiction":"EU",
        "as_of":profile["as_of"],"hazards":profile["hazards"],
        "profile_conflicts":conflicts,"blocked_due_to_profile_conflict":blocked,
        "sections":sections,
        "total_recommended_source_phrases":sum(s["source_matches"] for s in sections),
        "total_blocked_source_mappings":sum(s["unmatched_source"] for s in sections),
        "classification_approved":False,"legal_applicability_verified":False,
        "sds_compliant":False,"sections_complete":False,
        "warning":REVIEW_NOTICE,
        "limitations":[
            "No CLP hazard classification is calculated from numeric pH/flash point.",
            "No negative claims (non-hazardous, non-DG, no data, no CSA) are inferred from absent H codes.",
            "First aid, PPE, fire and storage wording is only a review candidate.",
            "No automatic legal P-statement selection is performed.",
        ],
    }
