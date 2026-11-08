"""Draft-only evidence/readiness prompts mapped to ECHA SDS guidance.

These prompts do not determine which legal obligations apply. They document
which product-specific evidence is supplied, missing or claimed not relevant.
Always return sds_compliant=False and regulation_verified=False.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROMPTS=ROOT/"rules"/"eu_sds_guidance_readiness_pilot.json"
SCHEMA="sds-information-readiness-prompts/v0.1"
RESPONSES={"unknown","available","not_available","not_applicable"}
RECORD_ID=re.compile(r"ECHA2020-S(04|07|08)-\d{2,3}")


class ReadinessError(ValueError):
    pass


def require(predicate, message):
    if not predicate:
        raise ReadinessError(message)


def load_prompts():
    data=json.loads(PROMPTS.read_text(encoding="utf-8"))
    require(data.get("schema")==SCHEMA,"Unsupported ECHA readiness prompt format")
    require(data.get("jurisdiction")=="EU","Guidance pilot must be EU only")
    require(data.get("status")=="nonbinding_guidance_crosswalk_draft_not_legally_verified",
            "Invalid source review status")
    rows=data.get("prompts")
    require(isinstance(rows,list) and len(rows)>=10,"Missing source prompts")
    ids=set()
    for row in rows:
        require(isinstance(row,dict),"Invalid readiness prompt")
        rid=row.get("id")
        require(isinstance(rid,str) and RECORD_ID.fullmatch(rid) and rid not in ids,
                "Invalid or duplicated guidance prompt ID")
        ids.add(rid)
        require(row.get("section") in (4,7,8),"Unexpected SDS section")
        require(row.get("subsection","").startswith(str(row["section"]) + "."),
                "Invalid SDS subsection mapping")
        page_range=row.get("source",{}).get("guidance_pages")
        require(isinstance(page_range,list) and len(page_range)==2 and
                all(type(page) is int and 1<=page<=137 for page in page_range) and
                page_range[0]<=page_range[1],"Invalid guidance page range")
        require(row.get("legal_status")=="not_verified" and
                row.get("automation_status")=="evidence_request_only_not_regulatory_decision",
                "Source prompt cannot imply legal approval")
        require(isinstance(row.get("question"),str) and bool(row["question"].strip()),
                "Question missing")
    require({row["section"] for row in rows}=={4,7,8},
            "Pilot must include sections 4, 7 and 8")
    return data


def evaluate_readiness(product, pack=None):
    require(isinstance(product,dict),"Expected JSON object")
    require(product.get("jurisdiction")=="EU","Only EU SDS guidance is in this pilot")
    as_of=product.get("as_of")
    require(isinstance(as_of,str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}",as_of)),
            "as_of must be YYYY-MM-DD")
    try:
        date.fromisoformat(as_of)
    except ValueError as exc:
        raise ReadinessError("Invalid assessment date") from exc
    supplied=product.get("evidence",{})
    require(isinstance(supplied,dict) and len(supplied)<=200,"Evidence must be an object")
    config=pack or load_prompts()
    records=config["prompts"]
    known={item["id"] for item in records}
    require(not set(supplied)-known,
            "Unrecognised prompt ID: "+", ".join(sorted(set(supplied)-known)[:5]))
    output=[]
    for item in records:
        entry=supplied.get(item["id"],{"status":"unknown","reference":"","reason":""})
        require(isinstance(entry,dict),"Evidence entry must be an object")
        require(set(entry).issubset({"status","reference","reason"}),
                "Invalid evidence fields for "+item["id"])
        status=entry.get("status","unknown")
        reference=entry.get("reference","")
        reason=entry.get("reason","")
        require(status in RESPONSES,"Invalid evidence status for "+item["id"])
        require(isinstance(reference,str) and len(reference)<=1000 and
                isinstance(reason,str) and len(reason)<=1000,
                "Invalid evidence explanation for "+item["id"])
        if status=="available" and reference.strip():
            finding="evidence_submitted_for_review"
        elif status=="not_available" and reason.strip():
            finding="missing_data_reason_for_review"
        elif status=="not_applicable" and reason.strip():
            finding="non_applicability_claim_for_review"
        else:
            finding="information_needed"
        output.append({
            "id":item["id"],"section":item["section"],"subsection":item["subsection"],
            "topic":item["topic"],"question":item["question"],
            "source":item["source"],"potential_evidence":item["potential_evidence"],
            "cross_section_consistency_checks":item["cross_section_consistency_checks"],
            "applicability_review_class":item["applicability_review_class"],
            "finding":finding,
            "reported_status":status,
            "evidence_reference":reference.strip() if status=="available" else "",
            "review_reason":reason.strip() if status in ("not_available","not_applicable") else "",
            "requirement_legally_verified":False,"content_sufficient":False,
        })
    sections=[]
    possible=sorted({item["section"] for item in records})
    for section in possible:
        matching=[x for x in output if x["section"]==section]
        states=sorted({x["finding"] for x in matching})
        sections.append({"section":section,"prompts":matching,
                         "counts":{s:sum(x["finding"]==s for x in matching) for s in states},
                         "section_content_approved":False})
    totals={key:sum(item["finding"]==key for item in output) for key in sorted({x["finding"] for x in output})}
    return {
        "schema":SCHEMA,"source_id":config["id"],"assessment_date":as_of,
        "sections":sections,"counts":totals,"number_of_prompts":len(output),
        "sds_compliant":False,"content_verified":False,"legally_applicable_rules_verified":False,
        "warning":("A recorded answer is not proof that a legal obligation is satisfied. "
                   "No legal applicability, adequacy, exemption or phrase approval is "
                   "established. Expert review and applicable current legislation are required."),
    }
