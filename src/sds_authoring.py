"""Local evidence-led authoring. Never equate a source match with adequacy."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import subprocess
import uuid
from contextlib import closing
from datetime import datetime, timezone, date
from pathlib import Path
from difflib import unified_diff

from catalogue_browser import connect, search
from profile_phrase_engine import recommend_profile
from section_recommendations import evaluate_sections
from sds_readiness import evaluate_readiness
from regulatory_engine import evaluate_regulations
from reach_annex2_audit import load_structure
from sds_assessment import assess, PASS, NA, FAIL, SUSPECT

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {
    "identity": "1", "supplier": "1", "market_language": "1", "uses": "1",
    "formulation": "3", "ingredient_classifications": "3", "mixture_classification": "2",
    "properties": "9", "toxicology": "11", "ecotoxicology": "12",
    "occupational_exposure": "8", "ppe": "8", "transport": "14", "regulatory": "15",
    "first_aid": "4", "fire": "5", "spill": "6", "handling_storage": "7",
    "reactivity": "10", "disposal": "13", "revision": "16",
}
KINDS = {"catalogue", "legal", "internal", "fact", "proposed"}
APPROVALS = {"pending", "approved", "rejected"}
def require(ok, message):
    if not ok:
        raise ValueError(message)

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def nonempty(x):
    return isinstance(x, str) and bool(x.strip())

def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))

def headings():
    return {h["code"]: h["heading"] for s in load_structure()["sections"]
            for h in [s, *s["subsections"]]}

def subsection_codes():
    return [c for c in headings() if "." in c]

def scopes(product):
    return [c for c in headings() if ("." in c or c == "16")
            and not (c == "3.1" and product.get("kind") == "mixture")
            and not (c == "3.2" and product.get("kind") == "substance")]

def catalogue_row(path, key):
    # The catalogue is opened read-only, including when approving a phrase.
    require(Path(path).is_file(), "Import/index the original catalogue first")
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("""SELECT e.entry_key,e.catalogue_version,e.collection,
            e.source_file,e.excel_row,e.structurecode,e.esdscom_phrase_id,
            e.original_code,e.english,e.jurisdiction_structure,e.sds_section,
            i.wording_hash,i.sds_subsection,i.phrase_kind
            FROM entries e JOIN catalogue_index i USING(entry_key)
            WHERE e.entry_key=?""", (key,)).fetchone()
    require(row is not None, "Unknown original catalogue entry")
    return dict(row)

class PhraseApprovals:
    """Append-only internal versions; source identity is copied, never generated."""
    def __init__(self, path, catalogue):
        self.path, self.catalogue = Path(path), Path(catalogue)
        require(self.path.resolve() != self.catalogue.resolve(), "Separate approval database required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS approvals (
                id TEXT, version INTEGER, record TEXT NOT NULL, PRIMARY KEY(id,version))""")

    def latest(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(r[0]) for r in db.execute("""SELECT record FROM approvals a
                WHERE version=(SELECT MAX(version) FROM approvals WHERE id=a.id)
                ORDER BY id""")]

    def save(self, record):
        require(isinstance(record, dict), "Approval object required")
        r = dict(record)
        require(r.get("status") in APPROVALS, "Invalid approval status")
        require(nonempty(r.get("reviewer")) and nonempty(r.get("reason")), "Reviewer and rationale required")
        require(r.get("jurisdiction") == "EU" and r.get("language") == "en",
                "Only EU English catalogue/wording verified by this workspace")
        require(r.get("subsection") in headings(), "Unknown subsection")
        conditions = r.get("conditions")
        require(isinstance(conditions, dict) and conditions and
                all(nonempty(k) and v is not None for k,v in conditions.items()),
                "Explicit applicability conditions required (dossier domain values)")
        require(set(conditions) <= set(DOMAINS), "Unknown applicability domain")
        require(nonempty(r.get("wording")), "Wording required")
        kind = r.get("kind")
        require(kind in {"catalogue", "internal"}, "Only catalogue/internal phrase approval")
        if r.get("entry_key"):
            source = catalogue_row(self.catalogue, r["entry_key"])
            require(source["jurisdiction_structure"] == "EU" and source["collection"] == "Core",
                    "Wrong source collection or jurisdiction")
            require(str(source["sds_section"]) == r["subsection"].split(".")[0], "Wrong source section")
            if kind == "catalogue":
                require(source["english"] == r["wording"], "Original wording must be exact")
            r["source"] = source
        else:
            require(kind == "internal", "Original entry key required")
            r["source"] = None
        r["text_sha256"] = text_hash(r["wording"])
        pid = r.get("id") or "INT-" + uuid.uuid4().hex
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT MAX(version) FROM approvals WHERE id=?", (pid,)).fetchone()[0]
            require((previous is None and not r.get("id")) or
                    (previous is not None and r.get("expected_version") == previous), "Stale or unknown approval ID")
            r.update(id=pid, version=(previous or 0)+1, timestamp=now())
            db.execute("INSERT INTO approvals VALUES (?,?,?)", (pid,r["version"],canonical(r)))
        return r

    def valid(self, phrase, product, code):
        if phrase.get("status") != "approved" or phrase.get("subsection") != code:
            return False
        if phrase.get("language") != product.get("language") or phrase.get("jurisdiction") != "EU":
            return False
        if not all(product.get("data", {}).get(k, {}).get("value") == v and
                   evidence(product, k) for k,v in phrase["conditions"].items()):
            return False
        if phrase.get("source"):
            try:
                if catalogue_row(self.catalogue, phrase["source"]["entry_key"]) != phrase["source"]:
                    return False
            except (ValueError, sqlite3.Error):
                return False
        return text_hash(phrase["wording"]) == phrase["text_sha256"]

def evidence(product, domain):
    fact = product.get("data", {}).get(domain, {})
    refs = fact.get("sources", [])
    return bool(fact.get("value") is not None and fact.get("value") != "" and
                fact.get("value") != [] and fact.get("value") != {} and refs and
                all(r in product.get("sources", {}) for r in refs))

def validate_dossier(d):
    require(isinstance(d,dict) and isinstance(d.get("products"),list) and d["products"], "Products required")
    ids = set()
    for p in d["products"]:
        require(isinstance(p,dict) and nonempty(p.get("id")) and p["id"] not in ids, "Distinct product IDs required")
        ids.add(p["id"])
        require(p.get("kind") in {"substance","mixture","unknown"}, "Explicit product kind required")
        require(p.get("jurisdiction") == "EU" and nonempty(p.get("language")), "EU jurisdiction and language required")
        date.fromisoformat(p["as_of"])
        require(isinstance(p.get("sources"),dict), "Source register required")
        for k,s in p["sources"].items():
            require(nonempty(k) and isinstance(s,dict) and nonempty(s.get("reference")) and
                    nonempty(s.get("locator")) and nonempty(s.get("version")), "Source reference, locator and version required")
        require(isinstance(p.get("data"),dict) and set(p["data"]) <= set(DOMAINS), "Unknown dossier data domain")
        for k,f in p["data"].items():
            require(isinstance(f,dict) and "value" in f and isinstance(f.get("sources"),list) and
                    all(isinstance(r,str) and r in p["sources"] for r in f["sources"]), "Unknown evidence reference: "+k)
        if evidence(p,"formulation"):
            items = p["data"]["formulation"]["value"]
            require(isinstance(items,list) and all(isinstance(i,dict) and nonempty(i.get("identity")) and
                    type(i.get("mass_percent")) in (float,int) and 0 < i["mass_percent"] <= 100 for i in items),
                    "Formulation requires identities and exact mass percentages")
            require(abs(sum(i["mass_percent"] for i in items)-100) <= 0.0001, "Full formulation must total 100 mass %")
        require(isinstance(p.get("profile",{}),dict) and isinstance(p.get("regulatory_input",{}),dict)
                and isinstance(p.get("readiness",{}),dict), "Engine inputs must be objects")
    require(isinstance(d.get("content",[]),list), "Content must be an array")
    seen = set()
    for r in d.get("content",[]):
        require(isinstance(r,dict) and nonempty(r.get("id")) and r["id"] not in seen, "Distinct draft block IDs required")
        seen.add(r["id"])
        require(r.get("code") in headings() and r.get("kind") in KINDS and nonempty(r.get("wording")), "Invalid draft block")
        require(isinstance(r.get("products"),list) and r["products"] and set(r["products"]) <= ids, "Explicit product coverage required")
        require(r.get("status","pending") in APPROVALS, "Invalid draft status")
        require(all(r["code"] in scopes(p) for p in d["products"] if p["id"] in r["products"]), "Use an applicable subsection for every target product")
        require(isinstance(r.get("domains",[]),list) and all(k in DOMAINS for k in r.get("domains",[])), "Unknown evidence domain")
    return d

def profile_inputs(p):
    # Derive hazards and core properties from the same dossier, not independent stale copies.
    profile = dict(p.get("profile",{}))
    profile.update(jurisdiction="EU", as_of=p["as_of"], product_type=p["kind"])
    cls = p["data"].get("mixture_classification",{})
    value = cls.get("value")
    profile["hazards"] = value.get("hazards",[]) if evidence(p,"mixture_classification") and isinstance(value,dict) else []
    profile["classification_reference"] = ", ".join(cls.get("sources",[]))[:400] if profile["hazards"] else ""
    props = p["data"].get("properties",{}).get("value")
    for k in ("physical_state","ph","flash_point_c"):
        profile.pop(k,None)
        if evidence(p,"properties") and isinstance(props,dict) and k in props:
            profile[k] = props[k]
    regulatory = dict(p.get("regulatory_input",{}))
    regulatory.update(jurisdiction="EU", as_of=p["as_of"], hazards=profile["hazards"])
    regulatory["classification_complete"] = {"value":"yes" if isinstance(value,dict) and value.get("complete") is True and evidence(p,"mixture_classification") else "unknown",
                                              "evidence":profile["classification_reference"] or ", ".join(cls.get("sources",[]))}
    return profile, regulatory

def draft_text(d, product=None, group=False, draft=True):
    lines = []
    for code, title in headings().items():
        if code in {"3.1","3.2"} and not any(code in scopes(p) for p in ([product] if product else d["products"])):
            continue
        lines.append(("SECTION " if "." not in code else "")+code+" "+title)
        blocks = [r for r in d.get("content",[]) if r["code"] == code and r.get("status") != "rejected"
                  and (product is None or product["id"] in r["products"])]
        for r in blocks:
            prefix = ("["+ ", ".join(r["products"])+"] ") if group else ""
            lines.append(prefix+r["wording"])
        if draft and not blocks and ("." in code or code == "16"):
            lines.append("[INFORMATION GAP — author review required]")
    return "\n".join(lines)

def block_valid(r,p):
    if r.get("status") != "approved" or not nonempty(r.get("reviewer")) or not nonempty(r.get("reason")):
        return False
    if r["kind"] in {"catalogue","internal"}:
        return False  # Checked separately against current controlled approval.
    if r["kind"] == "legal":
        entry = read("regulatory/assessment/clp_english.json").get(r.get("legal_code"))
        return bool(p["language"]=="en" and entry and entry["wording"]==r["wording"])
    return bool(r.get("domains") and all(k in DOMAINS and evidence(p,k) for k in r["domains"]))

def evaluate(d, approvals):
    validate_dossier(d)
    hs = headings()
    approved = approvals.latest()
    # Revision fingerprint includes active approval versions and canonical regulatory inputs.
    source_hashes = {f:text_hash((ROOT/f).read_text(encoding="utf-8")) for f in (
        "regulatory/canonical/requirements.json","regulatory/assessment/annex_ii.json","regulatory/assessment/clp_english.json",
        "regulatory/assessment/ref11.json","rules/eu_reach_annex2_partb_2026.json",
        "rules/regulatory-demo-v0.2.json","rules/eu_profile_phrase_relevance_v01.json",
        "rules/section_phrase_candidates_v0.1.json","rules/eu_sds_guidance_readiness_pilot.json")}
    live_sources = {}
    for phrase in approved:
        if phrase.get("source"):
            key = phrase["source"]["entry_key"]
            try:
                live_sources[key] = catalogue_row(approvals.catalogue,key)
            except (ValueError,sqlite3.Error):
                live_sources[key] = None
    fingerprint = digest([d, approved, source_hashes, live_sources])
    reports = []
    for p in d["products"]:
        profile, reg = profile_inputs(p)
        engines, errors = {}, []
        def run(name, fn):
            try:
                engines[name] = fn()
            except (ValueError, TypeError, KeyError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
                errors.append(name+": "+str(exc))
        run("profile", lambda: recommend_profile(approvals.catalogue,profile))
        run("section", lambda: evaluate_sections(approvals.catalogue,reg))
        run("readiness", lambda: evaluate_readiness({"jurisdiction":"EU","as_of":p["as_of"],"evidence":p.get("readiness",{})}))
        run("regulatory", lambda: evaluate_regulations(read("rules/regulatory-demo-v0.2.json"),reg))
        draft = draft_text(d,p,draft=False)
        context = p.get("assessment_context",{})
        require(isinstance(context,dict),"Assessment context must be an object")
        # Never let a user-supplied structural attestation override draft extraction.
        context = {k:v for k,v in context.items() if k != "verified_structure"}
        props = p["data"].get("properties",{}).get("value")
        if evidence(p,"properties") and isinstance(props,dict) and props.get("physical_state") in {"solid","liquid","gas"} and type(props.get("aerosol")) is bool and p["kind"]!="unknown":
            context["section9"]={"state":props["physical_state"],"kind":p["kind"],"aerosol":props["aerosol"]}
        else:
            context.pop("section9",None)
        run("assessment", lambda: assess({"name":p["id"],"sha256":text_hash(draft),
            "pages":[{"page":1,"text":draft}],"context":context}))
        conflicts = list(engines.get("profile",{}).get("profile_conflicts",[]))
        findings = engines.get("assessment",[])
        conflicts += [r["issue"] for r in findings if r["status"] in (FAIL,SUSPECT)]
        state = profile.get("physical_state")
        if state and state!="unknown" and any(h in profile["hazards"] for h in ("H224","H225","H226")) and state!="liquid":
            conflicts.append("Flammable-liquid classification conflicts with physical state")
        if isinstance(props,dict) and props.get("flammable") is False and set(profile["hazards"]) & {"H224","H225","H226"}:
            conflicts.append("Flammable-liquid classification conflicts with non-flammable property")
        missing = [k for k in DOMAINS if not evidence(p,k)]
        if p["kind"] == "unknown":
            errors.append("Product type unknown")
        if p["language"] != "en":
            errors.append("Localized headings and legal wording not verified")
        if not isinstance(p["data"].get("mixture_classification",{}).get("value"),dict) or reg["classification_complete"]["value"] != "yes":
            errors.append("Classification completeness not evidenced")
        rows = []
        for c,title in hs.items():
            if c not in scopes(p):
                continue
            required = [k for k,s in DOMAINS.items() if c.split(".")[0] == s]
            relevant = [r for r in findings if any(x==c or x.startswith(c+"(") or x.startswith(c+".") for x in r["section"].split())]
            if c=="16":
                relevant += [r for r in findings if r["section"] == "" or r["section"].startswith("0.")]
            blocks = [r for r in d.get("content",[]) if c==r["code"] and p["id"] in r["products"] and r.get("status")!="rejected"]
            candidates = []
            for s in engines.get("profile",{}).get("sections",[]):
                candidates += [x for x in s["candidates"] if x.get("subsection")==c]
            for s in engines.get("section",{}).get("sections",[]):
                candidates += [x for x in s["recommendations"] if x.get("subsection_hint")==c]
            suitable = [a for a in approved if approvals.valid(a,p,c)]
            invalid = []
            for r in blocks:
                if r["kind"] in {"catalogue","internal"}:
                    a=next((a for a in suitable if a["id"]==r.get("approval_id")),None)
                    valid=bool(a and a["version"]==r.get("approval_version") and a["wording"]==r["wording"] and a["kind"]==r["kind"]
                               and r.get("status")=="approved" and nonempty(r.get("reviewer")) and nonempty(r.get("reason")))
                else:
                    valid=block_valid(r,p)
                if not valid:
                    invalid.append(r["id"])
            rows.append({"code":c,"heading":title,"requirements":relevant,
                "required_domains":required,"evidence":{k:p["data"].get(k) for k in required if evidence(p,k)},
                "missing_domains":[k for k in required if k in missing],"candidates":candidates,
                "approved_candidates":suitable,"draft":blocks,"invalid_blocks":invalid,
                "coverage":"INSUFFICIENT_INFORMATION" if not blocks or invalid or any(k in missing for k in required) else "REVIEW_NEEDED",
                "adequacy":"Not assessed: every applicable requirement needs product-specific review"})
        reports.append({"product":p["id"],"rows":rows,"findings":findings,"engines":engines,
                        "errors":errors,"conflicts":conflicts,"missing_domains":missing})
    return {"fingerprint":fingerprint,"source_hashes":source_hashes,"products":reports,
            "grouping_basis":"REACH Annex II 1.1; SDS_Author references/REACH_MULTI_PRODUCT_SDS_COVERAGE.md @ 2c6cc785f218b0a1fb6f3f24260cc9b75026be8d",
            "grouping":"MUST_KEEP_SEPARATE_UNTIL_RESOLVED" if any(p["errors"] or p["conflicts"] or any(r["coverage"]=="INSUFFICIENT_INFORMATION" for r in p["rows"]) for p in reports) else "REVIEW_NEEDED"}

def gates(report, reviews):
    """Conservative release controls. A reviewed decision must bind to the exact snapshot."""
    blockers = []
    if reviews.get("fingerprint") != report["fingerprint"]:
        return ["Review missing or stale for this dossier/catalogue/rule snapshot"]
    for p in report["products"]:
        pid = p["product"]
        blockers += [pid+": "+e for e in p["errors"]+p["conflicts"]]
        for row in p["rows"]:
            code = row["code"]
            if row["coverage"] == "INSUFFICIENT_INFORMATION":
                blockers.append(pid+" "+code+": content/evidence incomplete or unapproved")
            review=reviews.get("coverage",{}).get(pid,{}).get(code,{})
            if review.get("status")!="PASS" or not nonempty(review.get("reason")) or not nonempty(review.get("reviewer")):
                blockers.append(pid+" "+code+": coverage/phrase adequacy not reviewed")
        for finding in p["findings"]:
            # Administrative REF-11 and supply-chain checks are kept in the report;
            # mandatory requirements must be individually dispositioned.
            r=reviews.get("findings",{}).get(pid,{}).get(finding["id"],{})
            if r.get("status") not in (PASS,NA) or not nonempty(r.get("reason")) or not nonempty(r.get("reviewer")):
                blockers.append(pid+" "+finding["id"]+": assessment unresolved")
    for key in ("applicable_law","classification","market_language","external_obligations","group_coverage","competent_person"):
        r=reviews.get("signoff",{}).get(key,{})
        if not (r.get("approved") is True and nonempty(r.get("reviewer")) and nonempty(r.get("reason"))):
            blockers.append(key+": mandatory review unresolved")
    # Canonical repository rule packs are explicitly unverified/pilot. No automatic
    # release based on manually ticked boxes until independently validated coverage
    # and authenticated release authority are implemented.
    blockers.append("Production release disabled: canonical rule coverage and reviewer authentication not independently validated")
    return blockers

class Workspace:
    def __init__(self,path,approvals):
        self.path=Path(path)
        require(self.path.resolve() not in {approvals.path.resolve(),approvals.catalogue.resolve()}, "Separate workspace required")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.approvals=approvals
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS revisions (
                case_id TEXT, version INTEGER, record TEXT NOT NULL, PRIMARY KEY(case_id,version))""")

    def save(self, case_id, dossier, expected_version=0, reviews=None):
        require(nonempty(case_id),"Case ID required")
        report=evaluate(dossier,self.approvals)
        reviews=reviews or {}
        blockers=gates(report,reviews)
        record={"case_id":case_id,"version":expected_version+1,"saved_at":now(),"dossier":dossier,
                "report":report,"reviews":reviews,"blockers":blockers,"status":"draft"}
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("BEGIN IMMEDIATE")
            prior=db.execute("SELECT MAX(version) FROM revisions WHERE case_id=?",(case_id,)).fetchone()[0] or 0
            require(prior==expected_version,"Stale workspace revision")
            db.execute("INSERT INTO revisions VALUES (?,?,?)",(case_id,record["version"],canonical(record)))
        return record

    def history(self,case_id):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(r[0]) for r in db.execute("SELECT record FROM revisions WHERE case_id=? ORDER BY version",(case_id,))]

    def compare(self,case_id,left,right):
        versions={r["version"]:r for r in self.history(case_id)}
        require(left in versions and right in versions,"Unknown revision")
        def lines(n):
            return json.dumps({"dossier":versions[n]["dossier"],"reviews":versions[n]["reviews"]},sort_keys=True,ensure_ascii=False,indent=2).splitlines()
        return "\n".join(unified_diff(lines(left),lines(right),fromfile=str(left),tofile=str(right)))

def export_draft(record, fmt):
    """Returns bytes; public-facing draft excludes confidential raw dossier by default."""
    from io import BytesIO
    d=record["dossier"]
    title="DRAFT — NOT FOR SUPPLY"
    body=title+"\n"+draft_text(d,group=len(d["products"])>1)
    if fmt=="json":
        return json.dumps({"schema":"sds-authoring-draft/v1","status":"draft","document":body,"revision":record["version"],
                           "products":[p["id"] for p in d["products"]],"blocks":d.get("content",[]),
                           "review_blockers":record["blockers"]},ensure_ascii=False,indent=2).encode()
    out=BytesIO()
    if fmt=="docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("DOCX export requires python-docx; install requirements-documents.txt or export JSON") from exc
        doc=Document()
        doc.add_heading(title,0)
        doc.sections[0].header.paragraphs[0].text=title
        for line in body.splitlines()[1:]:
            if line.startswith("SECTION "):
                doc.add_heading(line,1)
            elif line.split(" ",1)[0] in headings():
                doc.add_heading(line,2)
            else:
                doc.add_paragraph(line)
        doc.save(out)
    elif fmt=="pdf":
        try:
            from reportlab.platypus import SimpleDocTemplate, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
        except ImportError as exc:
            raise ValueError("PDF export requires ReportLab; install requirements-documents.txt or export JSON") from exc
        from xml.sax.saxutils import escape
        styles=getSampleStyleSheet()
        flow=[Paragraph(escape(line),styles["Heading2" if line.startswith("SECTION ") else "BodyText"])
              for line in body.splitlines()]
        def footer(canvas,doc):
            canvas.setFont("Helvetica",9)
            canvas.drawString(36,28,"DRAFT - NOT FOR SUPPLY")
            canvas.drawRightString(doc.pagesize[0]-36,28,str(doc.page))
        SimpleDocTemplate(out).build(flow,onFirstPage=footer,onLaterPages=footer)
    else:
        raise ValueError("Unknown export format")
    return out.getvalue()
