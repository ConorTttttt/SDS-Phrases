"""Offline evidence-led EU SDS assessment and report generation."""
import argparse
import csv
import hashlib
import subprocess
import json
import re
import shutil
from pathlib import Path

from reach_annex2_audit import load_structure
from toolkit import article31
from sds_intake import blocks, extract
from canonical_requirements import load as load_canonical, evaluate_requirement, coverage as canonical_coverage, inspection_link

ROOT = Path(__file__).resolve().parents[1]
PASS, FAIL, SUSPECT, UNKNOWN, NA, SKIP, REVIEW = STATUSES = (
    "Compliant against assessed requirement", "Non-compliant", "Potential non-compliance",
    "Insufficient evidence", "Not applicable", "Not assessed", "Requires competent-person review")
LAW = "REACH 02006R1907-20260622 Annex II"
CROSS = [
    ("2.1 3.2", "Check product classification against ingredient identities, concentrations and classification calculations."),
    ("2.1 4.1", "Check first aid for each classified route and effect."),
    ("2.1 5.1 7.1 9.1 10.1", "Reconcile physical hazards with extinguishing media, handling, measurements and reactivity."),
    ("2.1 11.1", "Reconcile health classification with route-specific toxicology."),
    ("2.1 12.1", "Reconcile environmental classification with ecological endpoints."),
    ("3.2 8.1", "Check disclosed identities against occupational limits for the market."),
    ("7.2 9.1 10.5", "Compare storage conditions, measured properties and incompatible materials."),
    ("1.2 8.2", "Verify that exposure estimates and controls cover identified uses."),
    ("9.1 14.3", "Verify physical properties against the assigned transport hazard class."),
    ("1.2 15.1", "Compare uses and conditions against applicable restrictions."),
    ("2.1 3.2 16", "Check full wording of abbreviated hazard statements."),
    ("1.2 7.1 8.2", "Compare attached exposure scenarios with uses, handling and exposure controls."),
]

def assess(document, corrections=None):
    pages = document["pages"]
    effective = [dict(p) for p in pages]
    for pos, value in (corrections or {}).items():
        if not str(pos).isdecimal() or int(pos)>=len(pages) or not isinstance(value,str):
            raise ValueError("Invalid corrected page index or text")
        effective[int(pos)]["text"] = value
    headings = [h for s in load_structure()["sections"] for h in [s,*s["subsections"]]]
    valid = {h["code"] for h in headings}
    groups = blocks(effective, valid)
    rows = []
    def finding(key, codes, issue, citation, status, evidence_needed):
        lines = [entry for code in codes.split() for entry in groups.get(code, [])]
        indices = list(dict.fromkeys(i for i,_ in lines))
        wording = "\n".join(t for _,t in lines)
        original = "\n".join(pages[i]["text"] for i in indices) if any(
            effective[i]["text"] != pages[i]["text"] for i in indices) else wording
        rows.append(dict(id=key, section=codes, page=", ".join(str(pages[i].get("page") or "unpaginated") for i in indices),
                         original_wording=original, product_evidence=wording, document_sha256=document["sha256"],
                         issue=issue, legal_requirement=citation, source_citation=citation,
                         status=status, applicability="requires confirmation", presence=("heading located" if key.startswith("heading/") else "section text located; requirement presence unverified") if lines else "unknown",
                         completeness=SKIP, regulatory_adequacy=SKIP, scientific_plausibility=SKIP,
                         internal_consistency=SKIP, expert_judgement="required", severity="review",
                         explanation=issue, recommended_correction=evidence_needed, missing_information=evidence_needed,
                         review_status="open"))
    for h in headings:
        code=h["code"]
        conditional=code in ("3.1","3.2")
        located=code in groups
        status=REVIEW if conditional and located else PASS if located else UNKNOWN
        finding("heading/"+code,code,"Heading located" if located else "Heading could not be established",
                f"{LAW} Part B {code}, p. {h['source_page']}",status,
                "Verify product type and applicable heading." if conditional else "Compare with original page." if not located else "")
    # A verified heading inventory is separate from extraction coverage.
    inventory = document.get("context", {}).get("verified_structure")
    if inventory:
        from reach_annex2_audit import audit_structure
        verified = audit_structure(inventory)
        structural = {r["section"]: r for r in rows}
        outcomes = {"reported_missing": FAIL, "reported_blank": FAIL, "reported_present": PASS,
                    "unexpected_heading_present": SUSPECT, "not_expected_for_product_type": NA}
        for item in verified["outcomes"]:
            row = structural[item["code"]]
            decision = item["decision"]
            outcome = outcomes.get(decision, UNKNOWN)
            if verified["source_edition_warning"] or inventory["as_of"] != "2026-06-22":
                outcome = REVIEW
            # A conflict between observed and attested headings needs reconciliation.
            if decision == "reported_missing" and item["code"] in groups:
                outcome = REVIEW
            row.update(status=outcome, explanation=item["explanation"], issue=item["explanation"],
                       product_evidence=json.dumps(inventory, ensure_ascii=False),
                       severity="major" if outcome == FAIL else "review",
                       applicability="inapplicable" if outcome == NA else "see reviewed inventory",
                       recommended_correction="Restore the required heading or complete the blank subsection." if outcome == FAIL else "",
                       missing_information="", review_status="reviewed inventory")
    pack, raw, _ = load_canonical(ROOT)
    for item in pack["requirements"]:
        clause = item["clause"].split()[-1]
        code = ".".join(clause.split("(")[0].split(".")[:2])
        result = evaluate_requirement(item, groups.get(code))
        finding(item["id"], code, item["required_sds_content"],
                f"{LAW} {item['clause']}, PDF pp. {item['pdf_pages']}", result["status"],
                result["missing_information"])
        rows[-1].update(rule_version=result["rule_version"], canonical_release=pack["release"],
                        assessment_method=item["assessment_methodology"], legacy_ids=item["legacy_ids"],
                        verification_status=item["verification_status"])
    for section, summary in canonical_coverage(pack, raw).items():
        finding("coverage/annex-ii/"+section, section,
                "Canonical legal decomposition and independent verification incomplete",
                LAW, UNKNOWN, "Review remaining source records, qualifications and current legal version.")
        rows[-1].update(canonical_release=pack["release"], coverage_gap=summary)
    for i,(codes,issue) in enumerate(CROSS):
        finding(f"consistency/{i}",codes,issue,f"{LAW} Part A "+", ".join(codes.split()),
                REVIEW if all(c in groups for c in codes.split()) else UNKNOWN,"Compare cited sections and supporting product data.")
    text=lambda c: "\n".join(t for _,t in groups.get(c,[]))
    if re.search(r"\bH22[456]\b",text("2.1")) and re.search(r"(?im)^\s*(?:flammability\s*:\s*)?non[- ]flammable\s*\.?$",text("9.1")):
        finding("conflict/flammability","2.1 9.1","Flammable-liquid classification conflicts with a non-flammable declaration.",
                LAW+" Part A 2.1 and 9.1(f)",SUSPECT,"Verify product identity, flash point, method and classification record.")
        rows[-1].update(internal_consistency=SUSPECT,severity="major")
    # Each trigger requires affirmative wording on both sides. The reviewer
    # checks context (including mixture vs ingredient and exposure route).
    conflicts = [
        ("first-aid","2.1",r"\bH(?:314|318)\b","4.1",r"(?im)^\s*Eye contact:\s*no (?:action|treatment) (?:needed|required)","Eye damage classification and eye-contact advice"),
        ("fire","2.1",r"\bH22[456]\b","5.2",r"(?im)^\s*(?:fire hazards?:\s*)?non[- ]flammable","Flammable liquid classification and firefighting description"),
        ("storage","7.2",r"(?im)^\s*(?:storage:\s*)?store in water","10.5",r"(?im)^\s*(?:incompatible materials?:\s*)water\b","Storage medium listed as incompatible"),
        ("health","2.1",r"\bH(?:300|301|302)\b","11.1",r"(?im)^\s*(?:oral|acute oral toxicity):\s*not classified","Oral toxicity classification discrepancy"),
        ("aquatic","2.1",r"\bH4(?:00|10|11|12|13)\b","12.1",r"(?im)^\s*(?:aquatic hazards?:\s*)?not hazardous to the aquatic environment","Aquatic classification discrepancy"),
        ("transport","9.1",r"(?im)^\s*(?:physical state:\s*)solid\s*$","14.2",r"(?im)flammable liquid,? n\.?o\.?s","Physical state and transport description discrepancy"),
    ]
    for key,left,lp,right,rp,title in conflicts:
        if re.search(lp,text(left)) and re.search(rp,text(right)):
            finding("conflict/"+key,left+" "+right,title,LAW+" Part A "+left+" and "+right,SUSPECT,
                    "Verify the identity, conditions and supporting data for both statements.")
            rows[-1].update(internal_consistency=SUSPECT,severity="major")
    # Use the Annex II disclosure test only as a review cue: constituent
    # hazard codes alone cannot establish classification of a mixture.
    checks = [
        ("composition", "2.1", r"(?im)^\s*(?:classification:\s*)?not classified\b",
         "3.2", r"\bH(?:3|4)\d{2}\b", "Review disclosed hazardous ingredients against mixture classification thresholds."),
        ("limits", "3.2", r"\b\d{2,7}-\d{2}-\d\b", "8.1",
         r"(?im)^\s*(?:OELs?|occupational exposure limits?):\s*(?:none|not applicable)\b",
         "Verify the no-limit assertion against ingredient identities and the market's limits."),
        ("use-controls", "1.2", r"(?i)\bspray(?:ing)?\b", "8.2",
         r"(?im)^\s*(?:intended use|exposure assessment):\s*(?:closed system only|no spraying)\b",
         "Spraying appears in the use description but the Section 8 assessment excludes it."),
        ("restriction", "1.2", r"(?im)^\s*identified use:\s*consumer use\b", "15.1",
         r"(?im)\brestricted to professional users\b", "Check consumer use against the stated professional-use restriction."),
    ]
    for key,left,lp,right,rp,topic in checks:
        if re.search(lp,text(left)) and re.search(rp,text(right)):
            status=REVIEW if key in ("composition","limits") else SUSPECT
            finding("compare/"+key,left+" "+right,topic,LAW+" Part A "+left+" and "+right,status,
                    "Obtain dated supporting records and resolve the identified comparison.")
            rows[-1]["internal_consistency"]=status
    for label,number,unit in re.findall(
            r"(?im)^\s*(density|vapour pressure|kinematic viscosity|flash point)\s*:\s*(-?\d+(?:[.,]\d+)?)\s*(kg/m³|g/cm³|kPa|Pa|mm²/s|°C|K)\s*$",text("9.1")):
        value=float(number.replace(",","."))
        prop=label.lower()
        incompatible=(prop=="density" and unit.lower() in ("kg/m³","g/cm³") and value<=0 or
                      prop=="vapour pressure" and unit.lower() in ("pa","kpa") and value<0 or
                      prop=="kinematic viscosity" and unit.lower()=="mm²/s" and value<0 or
                      prop=="flash point" and ((unit=="K" and value<0) or (unit=="°C" and value < -273.15)))
        if incompatible:
            basis={"density":"p","vapour pressure":"o","kinematic viscosity":"l","flash point":"h"}[prop]
            finding(f"property/{prop}/{len(rows)}","9.1",f"Implausible {label}: {number} {unit}.",f"{LAW} Part A 9.1({basis})",
                    SUSPECT,"Check the original test result, decimal sign, unit and applicable test conditions.")
            rows[-1].update(scientific_plausibility=SUSPECT,severity="major")
    hazard_codes=set(re.findall(r"\b(?:EUH|H)\d{3}[a-zA-Z]*\b",text("2.1")+" "+text("3.2")))
    statements=json.loads((ROOT/"regulatory/assessment/clp_english.json").read_text(encoding="utf-8"))
    normalize=lambda s: " ".join(s.casefold().split()).strip(" .")
    relevant_text=normalize(" ".join(text(c) for c in ("2.1","2.2","3.2","16")))
    for code in sorted(hazard_codes):
        reference=statements.get(code)
        located=reference is not None and normalize(reference["wording"]) in relevant_text
        finding("wording/"+code,"2.1 2.2 3.2 16","Check full English wording for "+code,
                LAW+" Part A Section 16(e)",REVIEW if located else UNKNOWN,
                "Check the source language, exact wording and association with the product or ingredient.")
        if reference:
            rows[-1]["source_citation"]+=f"; CLP 02008R1272-20260701 Annex III, {code}, p. {reference['page']}"
            rows[-1]["presence"]="reference wording located" if located else "full wording unconfirmed"
            rows[-1]["explanation"]="Expected English text: "+reference["wording"]
    context=document.get("context", {})
    scenario=context.get("exposure_scenario")
    if scenario and isinstance(scenario.get("text"),str):
        finding("scenario/controls","1.2 7.1 8.2","Compare main SDS use and controls with the supplied scenario.",
                "REACH Article 31(7); "+LAW+" Part A 0.1.2",REVIEW,"Verify scenario coverage, operational conditions and risk management measures.")
        rows[-1]["product_evidence"]+="\nSupplied exposure scenario: "+scenario["text"]
        if re.search(r"(?im)^identified use:\s*spraying\b",text("1.2")) and re.search(r"(?im)^excluded use:\s*spraying\b",scenario["text"]):
            rows[-1].update(status=SUSPECT,internal_consistency=SUSPECT,issue="Spraying is both identified in the SDS and excluded by the scenario.")
    if "reach" in context:
        result=article31(context["reach"])
        finding("supply/article31","",result["explanation"],result["source"],
                {"insufficient_evidence": UNKNOWN, "not_assessed": SKIP}.get(result["status"], REVIEW),
                "Check dated evidence of recipient, product status and supply.")
        rows[-1]["product_evidence"]=json.dumps(context["reach"],ensure_ascii=False)
    if "section9" in context:
        profile=context["section9"]
        if (profile.get("state") not in ("solid","liquid","gas") or
            profile.get("kind") not in ("substance","mixture") or type(profile.get("aerosol")) is not bool):
            raise ValueError("Section 9 requires state, product kind and boolean aerosol evidence")
        program="import {evaluate} from './modules/section9/rules.mjs'; console.log(JSON.stringify(evaluate(JSON.parse(process.argv[1]))))"
        try:
            executable = shutil.which("node")
            if not executable:
                raise FileNotFoundError("Node.js not on PATH")
            run=subprocess.run([executable,"--input-type=module","-e",program,json.dumps(profile)],cwd=ROOT,
                               capture_output=True,text=True,encoding="utf-8",check=True,timeout=60)
            results=json.loads(run.stdout)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            finding("section9/unavailable","9.1","Section 9 calculator could not execute",LAW,SKIP,
                    "Install Node.js 22+ on PATH and retry; check calculator inputs and installation: "+str(exc))
        else:
            for i,result in enumerate(results):
                finding(f"section9/{i}","9.1",result["name"]+" — "+result["reason"], LAW+" "+result["basis"],
                        REVIEW,result["guidance"])
                rows[-1]["applicability"]=result["status"]
    for question in json.loads((ROOT/"regulatory/assessment/ref11.json").read_text(encoding="utf-8")):
        key,topic,codes,law,page=question
        finding("REF11/"+key,codes,topic,law or "Administrative inspection record",SKIP if not law else UNKNOWN,
                "Record inspection response and the evidence for it.")
        rows[-1]["source_citation"]=f"ECHA-24-R-13-EN, Annex I, {key}, printed p. {page}"
        link = inspection_link(pack, "REF11/"+key)
        if link:
            rows[-1].update(related_requirement_ids=link["requirement_ids"],
                            enforcement_link_status=link["link_status"],
                            enforcement_limitations=link["limitations"])
    return rows

def export(directory, document, rows):
    def write(name, value):
        (directory/name).write_text(value,encoding="utf-8")
    write("findings.json",json.dumps(rows,ensure_ascii=False,indent=2))
    with (directory/"findings.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        for row in rows:
            values = {k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for k,v in row.items()}
            writer.writerow({k: ("'"+v if v.lstrip().startswith(("=","+","-","@")) else v) for k,v in values.items()})
    actions=[r for r in rows if r["status"] in (SUSPECT,FAIL)]
    write("corrective-actions.txt","\n".join(r["id"]+" — "+r["recommended_correction"] for r in actions))
    requests = []
    for row in rows:
        if row["id"].startswith("heading/") and row["status"]==UNKNOWN:
            requests.append("Section "+row["section"]+" — Please identify the page or supply a legible current copy.")
        elif row["status"] in (SUSPECT,FAIL) or row["id"]=="supply/article31":
            requests.append(row["section"]+" — "+row["issue"]+" "+row["recommended_correction"])
    write("supplier-request.txt","Supplier information request for "+document["name"]+"\n"+
          "\n".join(dict.fromkeys(requests)))
    template=(ROOT/"web/assessment-report.html").read_text(encoding="utf-8")
    payload=json.dumps(dict(document=document,rows=rows,statuses=STATUSES),ensure_ascii=False).replace("<","\\u003c")
    write("report.html",template.replace("CASE_PAYLOAD",payload))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files",type=Path,nargs="+")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--ref11", type=Path, help="Original REF-11 PDF for full questionnaire, instructions and answer branches")
    parser.add_argument("--ocr",action="store_true")
    parser.add_argument("--review",type=Path,help="Review JSON saved from the workspace")
    args=parser.parse_args()
    review=json.loads(args.review.read_text(encoding="utf-8")) if args.review else {}
    if review and len(args.files)!=1:
        parser.error("--review applies to one original document per invocation")
    for file in args.files:
        document=extract(file,args.ocr)
        case=args.out/document["sha256"]
        case.mkdir(parents=True,exist_ok=True)
        original=case/("original"+file.suffix.lower())
        if not original.exists():
            shutil.copyfile(file,original)
        if hashlib.sha256(original.read_bytes()).hexdigest()!=document["sha256"]:
            raise ValueError("Case archive does not match source evidence")
        if review and review["sha256"]!=document["sha256"]:
            raise ValueError("Review belongs to a different document")
        if args.ref11:
            digest=hashlib.sha256(args.ref11.read_bytes()).hexdigest()
            if digest != "2514559e63f7348e001d8b3578d264144fcd70bac317ad218de0183971a132a0":
                raise ValueError("REF-11 PDF differs from the registered source")
            shutil.copyfile(args.ref11,case/"ref11.pdf")
            document["ref11"]=True
        rows=assess(document,review.get("corrections"))
        for row in rows:
            decision=review.get("decisions",{}).get(row["id"])
            if decision:
                if decision["status"] not in STATUSES or not decision["reason"].strip():
                    raise ValueError("Review requires status and evidence rationale")
                row.update(status=decision["status"],review_status="manually reviewed",explanation=decision["reason"])
                if decision.get("source_pages"):
                    row["page"]=str(decision["source_pages"])
                if decision.get("source_quote"):
                    row["original_wording"]=str(decision["source_quote"])
                for dimension in ("applicability","presence","completeness","regulatory_adequacy",
                                  "scientific_plausibility","internal_consistency","expert_judgement"):
                    if decision.get(dimension):
                        row[dimension]=str(decision[dimension])
        document["review"]=review
        export(case,document,rows)
        print(case/"report.html")

if __name__=="__main__":
    main()
