"""Draft-only REACH Annex II Part B heading inventory checker.

Only the section/subsection *structure* is checked. Its result is never a
declaration of SDS compliance or evidence that section content is adequate.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STRUCTURE_PATH=ROOT/"rules"/"eu_reach_annex2_partb_2026.json"
HEADING_RE=re.compile(r"^(?:[1-9]|1[0-6])(?:\.[1-9][0-9]?)?$")

class ReachAuditError(ValueError):
    pass

def require(condition,message):
    if not condition:raise ReachAuditError(message)

def load_structure():
    data=json.loads(STRUCTURE_PATH.read_text(encoding="utf-8"))
    require(data.get("schema")=="reach-annex2-part-b-structure/v0.1","Unknown REACH structure schema")
    sections=data.get("sections",[])
    require(len(sections)==16,"Expected 16 SDS sections")
    require([x["code"] for x in sections]==[str(x) for x in range(1,17)],"Sections out of order")
    seen=set()
    for sec in sections:
        for item in [sec,*sec["subsections"]]:
            code=item["code"]
            require(code not in seen,"Duplicate heading code")
            seen.add(code)
            if item is not sec: require(code.startswith(sec["code"]+"."),"Subsection in wrong section")
    require(len(seen)==67,"Expected 16 headings and 51 subheadings")
    return data

def validate_profile(data):
    require(isinstance(data,dict),"Profile must be a JSON object")
    require(data.get("jurisdiction")=="EU","This structural draft is EU REACH Annex II only")
    as_of=data.get("as_of")
    require(isinstance(as_of,str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}",as_of)),
            "as_of must be YYYY-MM-DD")
    try:date.fromisoformat(as_of)
    except ValueError as exc:raise ReachAuditError("Invalid calendar date") from exc
    h=data.get("headings",[])
    require(isinstance(h,list) and len(h)<=200,"headings must be an array (max 200)")
    require(all(isinstance(x,str) and HEADING_RE.fullmatch(x) for x in h),"Invalid heading code")
    require(len(set(h))==len(h),"Duplicate heading codes")
    inv=data.get("inventory_complete",{})
    require(isinstance(inv,dict) and set(inv)=={"value","evidence"},"inventory_complete needs value and evidence")
    require(inv["value"] in ("yes","no","unknown"),"Inventory completeness must be yes, no, unknown")
    require(isinstance(inv["evidence"],str) and len(inv["evidence"])<=1000,"Invalid inventory evidence")
    product=data.get("product_type",{})
    require(isinstance(product,dict) and set(product)=={"value","evidence"},"product_type needs value and evidence")
    require(product["value"] in ("mixture","substance","unknown"),"Product type must be mixture, substance, unknown")
    require(isinstance(product["evidence"],str) and len(product["evidence"])<=1000,"Invalid product type evidence")
    blanks=data.get("blank_subsections",[])
    require(isinstance(blanks,list) and len(blanks)<=200 and
            all(isinstance(x,str) and HEADING_RE.fullmatch(x) and "." in x for x in blanks),
            "blank_subsections must be an array of subsection codes")
    require(len(set(blanks))==len(blanks),"Duplicate blank subsection codes")
    return data

def audit_structure(profile, structure=None):
    profile=validate_profile(profile)
    rules=structure or load_structure()
    require(rules.get("schema")=="reach-annex2-part-b-structure/v0.1","Wrong source structure")
    by_code={item["code"]:item for sec in rules["sections"] for item in [sec,*sec["subsections"]]}
    provided=set(profile["headings"])
    unrecognised=sorted(provided-set(by_code))
    blanks=set(profile.get("blank_subsections",[]))
    inventory=profile["inventory_complete"]
    complete=inventory["value"]=="yes" and bool(inventory["evidence"].strip())
    product=profile["product_type"]
    kind=product["value"] if product["evidence"].strip() else "unknown"
    outcomes=[]
    for sec in rules["sections"]:
        for node in [sec,*sec["subsections"]]:
            code=node["code"]
            result={"code":code,"heading":node["heading"],"printed_source_page":node["source_page"],
                    "source_location":"REACH Annex II Part B","decision":"","evidence":inventory["evidence"] if complete else "",
                    "explanation":"","is_legal_compliance_approval":False}
            if code in ("3.1","3.2"):
                if kind=="unknown":
                    result["decision"]="product_type_required"
                    result["explanation"]="Section 3 requires only 3.1 or 3.2 as appropriate, but the evidenced product type is unknown."
                    outcomes.append(result)
                    continue
                expected="3.1" if kind=="substance" else "3.2"
                if code!=expected:
                    result["decision"]="not_expected_for_product_type"
                    result["explanation"]="Only the other Section 3 subsection is expected for this evidenced product type."
                    if code in provided:
                        result["decision"]="unexpected_heading_present"
                        result["explanation"]="The inapplicable Section 3 alternative was also reported. Check intended SDS structure."
                    outcomes.append(result)
                    continue
            if code in provided and code in blanks:
                result["decision"]="reported_blank"
                result["explanation"]="Subsection reported as blank; Annex II Part A 0.4 prohibits blank subsections."
            elif code in provided:
                result["decision"]="reported_present"
                result["explanation"]="Heading included in submitted inventory; content, placement and legal adequacy not assessed."
            elif complete:
                result["decision"]="reported_missing"
                result["explanation"]="Evidenced complete heading inventory omitted this expected heading."
            else:
                result["decision"]="information_required"
                result["explanation"]="No heading reported; the inventory is incomplete or lacks evidence."
            outcomes.append(result)
    source=rules["source"]
    age_warning=None
    if profile["as_of"]<source["consolidated_edition"]:
        age_warning="Selected date predates this 2026 consolidation; older applicable text and transition rules require separate review."
    counts={key:sum(x["decision"]==key for x in outcomes) for key in sorted({x["decision"] for x in outcomes})}
    return {
        "document_id":source["celex"],"structure_schema":rules["schema"],
        "selected_as_of":profile["as_of"],"jurisdiction":"EU",
        "review_status":source["source_status"],
        "product_type_evidenced":kind,"inventory_complete_evidenced":complete,
        "outcomes":outcomes,"counts":counts,"unrecognised_heading_codes":unrecognised,
        "blank_subsections_not_in_inventory":sorted(blanks-provided),
        "source_edition_warning":age_warning,
        "sds_compliant":False,"subsection_content_validated":False,
        "warning":"Part B headings only. Missing, present or non-applicable outcomes do not establish content sufficiency, product hazard evaluation or legally compliant SDS drafting."
    }
