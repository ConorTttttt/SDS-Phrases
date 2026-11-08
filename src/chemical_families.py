"""Source-verified eSDScom chemical-family phrase candidate crosswalk.

Family tags are user-declared, not an analytical determination of composition
or hazard classification. This module retrieves only exact, unique original
licensed Core 5.5 English source records for manually curated family/cue
relationships. It never generates wording, legal labels, storage prescriptions
or chemical-family classifications.

The catalogue lives in data/catalogue.sqlite locally, never in Git.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from catalogue_browser import connect

ROOT=Path(__file__).resolve().parents[1]
FAMILY_PACK=ROOT/"rules"/"eu_chemical_family_phrase_cues_v01.json"
SCHEMA="sds-chemical-family-phrase-cues/v0.1"
CODE=re.compile(r"01(?:\.\d+)+\.\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")
H_CODE=re.compile(r"(?:H[2-4]\d{2}|EUH\d{3})\Z")
FAMILY_KINDS={
    "family_fragment", "family_process_review",
    "family_label_review", "family_safety_review",
}
VALID_GRAMMARS={"Sentence","List-Element","List-Start","Header","Data"}
SOURCE_FIELDS=(
    "entry_key","catalogue_version","collection","source_file",
    "excel_row","structurecode","esdscom_phrase_id","original_code",
    "sds_section","wording_hash","grammar",
)


class ChemicalFamilyError(ValueError):
    pass


def check(assertion,message):
    if not assertion:
        raise ChemicalFamilyError(message)


def load_family_pack():
    pack=json.loads(FAMILY_PACK.read_text(encoding="utf8"))
    check(pack.get("schema")==SCHEMA,"Unknown chemical-family source pack schema.")
    check(pack.get("jurisdiction")=="EU" and pack.get("language")=="en",
          "Unexpected family source jurisdiction/language.")
    check(pack.get("status")=="family_related_draft_candidates_not_legally_verified",
          "Family source pack cannot claim legal applicability.")
    families=pack.get("families")
    rules=pack.get("rules")
    check(isinstance(families,list) and 1<=len(families)<=30,
          "Invalid chemical-family list.")
    names=set()
    for group in families:
        check(isinstance(group,dict) and
              isinstance(group.get("id"),str) and
              re.fullmatch(r"[a-z][a-z_]{2,60}",group["id"]) and
              group["id"] not in names and
              isinstance(group.get("label"),str) and len(group["label"])>=4 and
              isinstance(group.get("note"),str) and len(group["note"])>=10,
              "Invalid chemical-family metadata.")
        names.add(group["id"])
    assessments=pack.get("assessments",[])
    check(isinstance(assessments,list) and len(assessments)<=15,"Invalid family assessment list.")
    assessment_ids=set()
    for assess in assessments:
        check(isinstance(assess,dict) and
              isinstance(assess.get("id"),str) and
              re.fullmatch(r"[a-z][a-z_]{2,60}",assess["id"]) and
              assess["id"] not in assessment_ids and
              isinstance(assess.get("label"),str) and bool(assess["label"]),
              "Invalid family assessment metadata.")
        assessment_ids.add(assess["id"])
    check(isinstance(rules,list) and 1<=len(rules)<=250,
          "Missing family-linked catalogue entries.")
    ids=set()
    for rule in rules:
        check(isinstance(rule,dict) and isinstance(rule.get("id"),str) and
              rule["id"] not in ids and rule.get("family") in names,
              "Duplicated family rule or unknown family.")
        ids.add(rule["id"])
        check(isinstance(rule.get("structurecode"),str) and
              CODE.fullmatch(rule["structurecode"]),
              "Invalid family source code.")
        check(type(rule.get("section")) is int and 1<=rule["section"]<=16,
              "Invalid source section.")
        check(isinstance(rule.get("subsection"),str) and
              re.fullmatch(str(rule["section"])+r"(?:\.\d{1,2})?",rule["subsection"]),
              "Invalid subsection hint.")
        check(rule.get("expected_grammar") in VALID_GRAMMARS and
              isinstance(rule.get("expected_english_sha256"),str) and
              SHA.fullmatch(rule["expected_english_sha256"]),
              "Family source grammar/hash must be pinned.")
        check(rule.get("kind") in FAMILY_KINDS,
              "Unknown family source review kind.")
        check(rule.get("legal_status")=="not_verified" and
              rule.get("review_status")=="human_applicability_review_required",
              "Family source may not be declared approved.")
        check(isinstance(rule.get("topic"),str) and bool(rule["topic"]) and
              isinstance(rule.get("review_note"),str) and len(rule["review_note"])>=20,
              "Missing source rationale or caution.")
        needs=rule.get("requires_hazard_any",[])
        check(isinstance(needs,list) and all(isinstance(v,str) and H_CODE.fullmatch(v) for v in needs),
              "Invalid family-specific H-statement prerequisite.")
        if "assessment" in rule:
            check(rule["assessment"] in assessment_ids,
                  "Unknown additional process assessment.")
        for field_group in ("requires_fields","requires_any_fields"):
            match=rule.get(field_group,{} if field_group=="requires_fields" else [])
            if field_group=="requires_fields":
                check(isinstance(match,dict) and all(
                    isinstance(k,str) and isinstance(v,str) for k,v in match.items()
                ),"Invalid required property prerequisites.")
            else:
                check(isinstance(match,list) and all(
                    isinstance(g,dict) and len(g)==1 and
                    all(isinstance(k,str) and isinstance(v,str) for k,v in g.items())
                    for g in match),"Invalid alternative physical property prerequisites.")
    return pack


def validate_family_inputs(families,assessments,pack):
    allowed={x["id"] for x in pack["families"]}
    known_assessments={x["id"] for x in pack.get("assessments",[])}
    check(isinstance(families,list) and len(families)<=len(allowed) and
          all(isinstance(x,str) and x in allowed for x in families) and
          len(families)==len(set(families)),
          "Select only recognised, non-duplicated chemical families.")
    check(isinstance(assessments,dict) and
          set(assessments)<=known_assessments and
          all(v in ("yes","no","unknown") for v in assessments.values()),
          "Invalid family-specific process assessment.")


def _qualifies(rule,product):
    if rule["family"] not in product["chemical_families"]:
        return False
    prerequisite=rule.get("requires_hazard_any",[])
    if prerequisite and not set(prerequisite).intersection(product["hazards"]):
        return False
    if "assessment" in rule and product.get("family_assessments",{}).get(
        rule["assessment"],"unknown")!="yes":
        return False
    if any(product.get(key)!=value for key,value in rule.get("requires_fields",{}).items()):
        return False
    alternatives=rule.get("requires_any_fields",[])
    if alternatives and not any(
        all(product.get(key)==value for key,value in alt.items())
        for alt in alternatives
    ):
        return False
    return True


def family_candidates(db,product,pack=None):
    """Original source candidates only; no downstream legal applicability."""
    config=pack or load_family_pack()
    validate_family_inputs(product.get("chemical_families",[]),
                           product.get("family_assessments",{}),config)
    if not product.get("chemical_families"):
        return []
    enabled=[r for r in config["rules"] if _qualifies(r,product)]
    if not enabled:
        return []
    grouped={}
    for rule in enabled:
        grouped.setdefault(rule["structurecode"],[]).append(rule)
    codes=sorted(grouped)
    conn=connect(db)
    try:
        query=(
            "SELECT e.entry_key,e.catalogue_version,e.collection,e.source_file,"
            "e.excel_row,e.structurecode,e.esdscom_phrase_id,e.original_code,"
            "e.english,e.sds_section,e.jurisdiction_structure,e.grammar,"
            "i.wording_hash,i.quality_flags "
            "FROM entries e LEFT JOIN catalogue_index i ON i.entry_key=e.entry_key "
            "WHERE e.collection='Core' AND e.structurecode IN ("+
            ",".join("?" for _ in codes)+")"
        )
        records=[dict(r) for r in conn.execute(query,codes)]
    finally:
        conn.close()
    by_code={}
    for row in records:
        by_code.setdefault(row["structurecode"],[]).append(row)
    family_names={r["id"]:r["label"] for r in config["families"]}
    output=[]
    for code,rules in grouped.items():
        unique=by_code.get(code,[])
        row=unique[0] if len(unique)==1 else None
        # Same code can be associated with different families, but its exact
        # original text and source metadata must be unambiguous.
        grammar_set={r["expected_grammar"] for r in rules}
        digest_set={r["expected_english_sha256"] for r in rules}
        flags=None
        if row and isinstance(row.get("quality_flags"),str):
            try:
                flags=json.loads(row["quality_flags"])
            except json.JSONDecodeError:
                flags=None
        first=rules[0]
        integrity=bool(
            row and len(grammar_set)==1 and len(digest_set)==1 and
            row.get("catalogue_version")=="5.5" and
            row.get("collection")=="Core" and
            row.get("jurisdiction_structure")=="EU" and
            row.get("sds_section")==first["section"] and
            row.get("grammar")==first["expected_grammar"] and
            row.get("english") and isinstance(row.get("wording_hash"),str) and
            SHA.fullmatch(row["wording_hash"]) and flags==[] and
            hashlib.sha256(row["english"].encode("utf8")).hexdigest() ==
            first["expected_english_sha256"]
        )
        output.append({
            "rule_id":first["id"],
            "section":first["section"],"subsection":first["subsection"],
            "topic":first["topic"],"kind":first["kind"],"sort":55,
            "reason":"; ".join(dict.fromkeys(x["reason"] for x in rules)),
            "matched_inputs":[
                "user-declared chemical family: "+family_names[rule["family"]]
                for rule in rules
            ]+[
                "entered classification: "+code
                for code in sorted(set().union(*(set(r.get("requires_hazard_any",[])) for r in rules))
                                   .intersection(product["hazards"]))
            ],
            "family_ids":list(dict.fromkeys(r["family"] for r in rules)),
            "family_labels":list(dict.fromkeys(family_names[r["family"]] for r in rules)),
            "confirmation_required":list(dict.fromkeys(r["review_note"] for r in rules)),
            "source_integrity":"exact_source_match" if integrity else "blocked_catalogue_mismatch",
            "phrase":row["english"] if integrity else None,
            "source":{key:row[key] for key in SOURCE_FIELDS} if integrity else None,
            "text_sha256":hashlib.sha256(row["english"].encode("utf8")).hexdigest() if integrity else None,
            "is_fragment":any(r["expected_grammar"]!="Sentence" for r in rules),
            "legal_applicability_verified":False,
            "approved_for_sds":False,
            "review_status":"draft_family_candidate_unreviewed",
        })
    return output


def public_families(pack=None):
    p=pack or load_family_pack()
    return {
        "schema":SCHEMA,"jurisdiction":"EU",
        "families":p["families"],"assessments":p.get("assessments",[]),
        "mapped_source_codes":len({x["structurecode"] for x in p["rules"]}),
        "rule_count":len(p["rules"]),
        "notice":p["disclaimer"],
    }
