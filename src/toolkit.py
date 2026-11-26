"""Partial, offline EU SDS evidence review; never a legal compliance certificate."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from reach_annex2_audit import audit_structure

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def evidenced(record, key, allowed):
    v=record.get(key)
    if not isinstance(v,dict) or not isinstance(v.get("evidence"),str) or not v["evidence"].strip():
        return "unknown"
    return v.get("value") if v.get("value") in allowed else "unknown"

def fact(record, key):
    return evidenced(record,key,("yes","no"))

def article31(record):
    if record.get("jurisdiction") != "EU":
        raise ValueError("Only EU review supported")
    selected=date.fromisoformat(record["as_of"])
    kind=evidenced(record,"product_type",("substance","mixture"))
    hazardous=fact(record,"hazardous")
    pbt=fact(record,"pbt_vpvb")
    candidate=fact(record,"candidate_list_other_reason")
    scope=fact(record,"title_iv_in_scope")
    public=fact(record,"offered_or_sold_to_general_public")
    sufficient=fact(record,"public_safety_information_sufficient")
    request=fact(record,"downstream_user_or_distributor_request")
    status="insufficient_evidence"
    explanation="Scope, product type, or trigger evidence incomplete; never infer no SDS obligation."
    if scope == "yes" and kind in ("substance","mixture"):
        trigger=hazardous=="yes" or (kind=="substance" and (pbt=="yes" or candidate=="yes"))
        if trigger:
            status="requires_competent_person_review"
            explanation="Article 31(1) trigger indicated by submitted facts; check applicable law and Article 31(4)."
            if public=="yes" and hazardous=="yes" and sufficient=="yes" and request=="no":
                explanation="Possible Article 31(4) public supply exception; competent-person verification required."
            elif public=="no" or request=="yes":
                explanation="Article 31(1) supply trigger indicated; confirm date-specific law and scope."
        elif kind=="mixture" and hazardous=="no":
            status="not_assessed"
            explanation="Nonclassified mixture: Article 31(3), special CLP triggers and Article 32 require separate assessment."
        elif kind=="substance" and hazardous==pbt==candidate=="no":
            status="requires_competent_person_review"
            explanation="No Article 31(1) trigger reported; Article 32 and scope/date verification still required."
    if selected!=date(2026,6,22):
        explanation+=" Assessment date differs from supplied REACH snapshot; applicable law must be verified."
    return {"rule_id":"RCH-002","related_rule_ids":["RCH-003","RCH-004","RCH-010"],
            "source":"REACH consolidated 2026-06-22, Articles 31(1), 31(4), PDF pp.39–40",
            "status":status,"explanation":explanation,"assessment_date":record["as_of"],
            "evidence_status":"user_submitted_not_independently_verified",
            "applicability": "requires_review", "presence":"not_assessed","adequacy":"not_assessed",
            "legal_compliance_determined":False,"requires_expert_review":True}

def assess(record):
    if not isinstance(record,dict): raise ValueError("Object required")
    output={"schema":"sds-toolkit-assessment/v1","legal_compliance_determined":False,
            "coverage":read(ROOT/"regulatory/coverage.json"),
            "product_sha256":hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
            "article31":article31(record)}
    if "structure" in record:
        profile=dict(record["structure"])
        profile["jurisdiction"]=record["jurisdiction"]
        profile["as_of"]=record["as_of"]
        profile["product_type"]=record.get("product_type",{"value":"unknown","evidence":""})
        output["structure"]=audit_structure(profile)
    else:
        output["structure"]={"status":"not_assessed","reason":"No reviewed heading inventory provided."}
    return output

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("input",type=Path)
    args=p.parse_args()
    print(json.dumps(assess(read(args.input)),ensure_ascii=False,indent=2,allow_nan=False))
if __name__=="__main__": main()
