"""Canonical requirement registry; offline, stdlib only. No legal certification."""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "regulatory/canonical/requirements.json"
METHODS = frozenset(("structural_presence", "conditional_applicability", "numeric_threshold",
    "required_factual_information", "required_wording", "scientific_adequacy",
    "cross_section_consistency", "external_supply_chain", "competent_person_judgement"))

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()

def load(root=ROOT):
    pack = read(root / "regulatory/canonical/requirements.json")
    raw = read(root / "regulatory/assessment/annex_ii.json")
    sources = {s["id"]:s for s in read(root / "regulatory/source_manifest.json")["sources"]}
    if pack["schema"] != "sds-canonical-requirements/v1" or len(raw) != pack["legacy_snapshot"]["records"]:
        raise ValueError("Canonical schema or legacy inventory changed")
    # Git blob hash pins the exact historical ordering; no silent rebasing.
    b = (root / pack["legacy_snapshot"]["path"]).read_bytes()
    if hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() != pack["legacy_snapshot"]["blob"]:
        raise ValueError("Legacy inventory differs from pinned snapshot")
    rows = pack["requirements"]
    ids = {r["id"] for r in rows}
    if len(ids) != len(rows):
        raise ValueError("Duplicate requirement IDs")
    migration = {m["legacy_id"]:m for m in pack["migration"]}
    if len(migration) != len(pack["migration"]) or set(migration) != {"annex/"+str(i) for i in range(len(raw))}:
        raise ValueError("Incomplete legacy mapping")
    for m in migration.values():
        if not set(m["requirement_ids"]) <= ids:
            raise ValueError("Unknown migration target")
    required = set(("id source_id source_version legal_authority_type clause table_references printed_pages pdf_pages wording applicability_conditions exceptions required_product_evidence required_sds_content assessment_methodology related_requirements effective_date transition_rules verification_status implementation_status test_ids legacy_ids").split())
    for r in rows:
        if not required <= set(r) or not r["id"].startswith("EU-REACH-AII-") or r["assessment_methodology"] not in METHODS:
            raise ValueError("Invalid requirement")
        source = sources[r["source_id"]]
        if source["version"] != r["source_version"] or any(not 1 <= p <= source["pages"] for p in r["pdf_pages"]):
            raise ValueError("Source version or page mismatch")
        if not r["legacy_ids"] or not all(r["id"] in migration[k]["requirement_ids"] for k in r["legacy_ids"]):
            raise ValueError("Broken reverse mapping")
        joined = " ".join(raw[int(k.split("/")[1])]["text"] for k in r["legacy_ids"])
        if r["wording"] not in joined or not set(r["related_requirements"]) <= ids:
            raise ValueError("Untraceable wording or related requirement")
        if r["implementation_status"] != "manual_review_only":
            raise ValueError("No canonical deterministic legal rules approved")
    for old in pack.get("historical_versions", []):
        historical = old["record"]
        if historical["id"] not in ids or not old.get("reason"):
            raise ValueError("Invalid historical requirement")
        if any(digest(historical) == digest(r) for r in rows):
            raise ValueError("Historical version duplicates active record")
    inspection_ids = set()
    for link in pack.get("enforcement_crosswalk", []):
        if link["id"] in inspection_ids or link["source_id"] != "ref11" or link["legal_authority_type"] != "enforcement_report":
            raise ValueError("Invalid inspection reference")
        inspection_ids.add(link["id"])
        if not set(link["requirement_ids"]) <= ids:
            raise ValueError("Unknown inspection crosswalk target")
    return pack, raw, sources

def jsonl(rows):
    """Canonical JSONL: one record per line, sorted keys, compact separators, UTF-8, LF."""
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for r in rows)

def json_text(value):
    """Canonical pretty JSON used for committed generated snapshots."""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"

MATRIX_WARNING = "Candidate target coverage only. No independent legal verification or exhaustive atomisation."

def coverage_matrix(pack, raw):
    """Committed per-section snapshot derived solely from coverage(); never hand-edited."""
    sections = {}
    for section, entry in sorted(coverage(pack, raw).items(), key=lambda item: int(item[0])):
        sections[section] = {"source_records": entry["source_records"],
            "mapped_source_records": entry["linked_source_records"],
            "unmapped_source_records": entry["unmapped_source_records"],
            "unresolved_source_records": entry["unresolved_source_records"],
            "reference_only_records": entry["reference_only_records"],
            "assessment_targets": [{k: r[k] for k in ("id", "verification_status", "implementation_status")}
                                   for r in entry["requirements"]],
            "verification": entry["coverage"]}
    return {"release": pack["release"], "warning": MATRIX_WARNING, "sections": sections}

COMMITTED_EXPORTS = ("regulatory/canonical/requirements.jsonl", "regulatory/canonical/coverage_matrix.json")

def committed_exports(root=ROOT):
    """Generated files that are committed for review; regenerate, do not edit by hand."""
    pack, raw, _ = load(root)
    return {COMMITTED_EXPORTS[0]: jsonl(pack["requirements"]),
            COMMITTED_EXPORTS[1]: json_text(coverage_matrix(pack, raw))}

def sync_committed(root=ROOT, check=False):
    """Write (or, with check=True, only compare) committed exports. Returns stale paths."""
    stale = []
    for name, text in committed_exports(root).items():
        path = Path(root) / name
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            stale.append(name)
            if not check:
                path.write_bytes(text.encode("utf-8"))
    return stale

def knowledge_base_markdown(root=ROOT):
    """Render every canonical record with its source identity and limitations for a single-file LLM package."""
    pack, raw, sources = load(root)
    title = load_title_iv(root, pack)
    clp = load_clp(root, pack, title)
    out = ["# Canonical regulatory requirement registry",
           "All records below are candidate assessment targets for manual review. None is an independently "
           "verified legal obligation or an executable rule. Consolidated texts are documentation snapshots, "
           "not the authentic Official Journal text, and their currentness after the snapshot date is not verified. "
           "Missing or unextracted information is never evidence of absence of a hazard or of compliance.",
           "## Source versions", "| id | version | authority | pages | sha256 | currentness |", "|---|---|---|---|---|---|"]
    out += [f"| {s['id']} | {s['version']} | {s['authority']} | {s['pages']} | {s['sha256']} | {s['currentness']} |"
            for s in sources.values()]
    components = ((pack, "REACH Annex II", [pack["scope"]]),
                  (title, "REACH Title IV", [title["scope"]]),
                  (clp, "CLP label and PCN", [clp["scope"]] + ["Coverage gap: " + g for g in clp.get("coverage_gaps", [])]))
    for component, label, limits in components:
        rows = component["requirements"]
        statuses = sorted({(r["verification_status"], r["implementation_status"]) for r in rows})
        out += [f"## {label} — {component['schema']} release {component['release']}",
                f"Records: {len(rows)}. Status: " + "; ".join(f"{v} / {i}" for v, i in statuses) + ".",
                "Limitations:"] + ["- " + text for text in limits]
        for r in rows:
            out.append(f"### {r['id']}\n\n- Clause: {r['clause']}\n- Source: {r['source_id']} {r['source_version']}; "
                       f"PDF pages {r['pdf_pages']}; printed pages {r['printed_pages']}\n"
                       f"- Authority: {r['legal_authority_type']}; modality: {r.get('modality', '')}\n"
                       f"- Verification: {r['verification_status']}; implementation: {r['implementation_status']}\n"
                       f"- Rule version: {requirement_version(r)}\n- Effective date: {r['effective_date']}; "
                       f"transition: {r['transition_rules']}\n- Applicability: {r['applicability_conditions']}\n"
                       f"- Exceptions: {r['exceptions']}\n- Required product evidence: {r['required_product_evidence']}\n"
                       f"- Assessment method: {r['assessment_methodology']}\n\nWording: {r['wording']}")
    return "\n\n".join(out) + "\n"

def requirement_version(row):
    return digest(row)

def resolve_requirement_version(pack, identifier, version):
    """Resolve active or archived exact requirement, never substitute a newer version."""
    candidates = pack["requirements"] + [h["record"] for h in pack.get("historical_versions", [])]
    return next((r for r in candidates if r["id"] == identifier and requirement_version(r) == version), None)

def inspection_link(pack, identifier):
    return next((r for r in pack.get("enforcement_crosswalk", []) if r["id"] == identifier), None)

def coverage(pack, raw):
    result = {}
    for i, m in enumerate(pack["migration"]):
        section = raw[int(m["legacy_id"].split("/")[1])]["clause"].split(".")[0]
        entry = result.setdefault(section, {"source_records":0,"linked_source_records":0,
             "unmapped_source_records":0,"unresolved_source_records":0,"reference_only_records":0,"requirements":[], "coverage":"incomplete"})
        entry["source_records"] += 1
        if m["disposition"] == "pending_decomposition":
            entry["unresolved_source_records"] += 1
        if "reference_not_standalone" in m["disposition"]:
            entry["reference_only_records"] += 1
        entry["linked_source_records" if m["requirement_ids"] else "unmapped_source_records"] += 1
    for r in pack["requirements"]:
        section = re.split(r"[.(]",r["clause"].split()[-1])[0]
        result[section]["requirements"].append({"id":r["id"],"version":requirement_version(r),
            "verification_status":r["verification_status"],"implementation_status":r["implementation_status"]})
    return result

def evaluate_requirement(row, evidence=None):
    """Manual dispatcher. Evidence is not itself a legal outcome."""
    method = row["assessment_methodology"]
    if method not in METHODS:
        raise ValueError("Unknown assessment method")
    return {"requirement_id":row["id"],"rule_version":requirement_version(row),
            "method":method,"status":"Requires competent-person review" if evidence else "Insufficient evidence",
            "missing_information":row["required_product_evidence"],
            "deterministic":False}


def load_title_iv(root=ROOT, annex_pack=None):
    """Load the Title IV component of the same canonical registry."""
    pack = read(root / "regulatory/canonical/title_iv.json")
    source = next(s for s in read(root/"regulatory/source_manifest.json")["sources"] if s["id"]=="reach")
    if (pack["schema"]!="sds-canonical-title-iv/v1" or pack["source_version"]!=source["version"]
            or pack["source_sha256"]!=source["sha256"]):
        raise ValueError("Title IV source identity mismatch")
    records = {r["id"]:r for r in pack["source_records"]}
    rows = {r["id"]:r for r in pack["requirements"]}
    if len(records)!=len(pack["source_records"]) or len(rows)!=len(pack["requirements"]):
        raise ValueError("Duplicate Title IV identifiers")
    if annex_pack is None:
        annex_pack, _, _ = load(root)
    known = set(rows) | {r["id"] for r in annex_pack["requirements"]}
    if len(known)!=len(rows)+len(annex_pack["requirements"]):
        raise ValueError("Duplicate cross-component requirement identifiers")
    required = {"id","source_id","source_version","legal_authority_type","clause",
        "table_references","printed_pages","pdf_pages","source_record_ids","wording",
        "applicability_conditions","exceptions","required_product_evidence","required_sds_content",
        "assessment_methodology","related_requirements","effective_date","transition_rules",
        "verification_status","implementation_status","test_ids","modality"}
    for record in records.values():
        if (not record["wording"].strip() or not record["pdf_pages"]
                or any(not 1<=n<=source["pages"] for n in record["pdf_pages"])):
            raise ValueError("Invalid Title IV source record "+record["id"])
    for row in rows.values():
        if not required<=set(row) or not row["id"].startswith("EU-REACH-A"):
            raise ValueError("Invalid Title IV schema")
        refs = [records[k] for k in row["source_record_ids"]]
        if (not refs or row["wording"]!=" ".join(r["wording"] for r in refs)
                or row["source_id"]!="reach" or row["source_version"]!=source["version"]
                or row["pdf_pages"]!=list(dict.fromkeys(n for r in refs for n in r["pdf_pages"]))
                or row["printed_pages"]!=list(dict.fromkeys(n for r in refs for n in r["printed_pages"]))
                or row["assessment_methodology"] not in METHODS
                or row["implementation_status"]!="manual_review_only"
                or not set(row["related_requirements"])<=known
                or any(not 1<=n<=source["pages"] for n in row["pdf_pages"])):
            raise ValueError("Invalid Title IV requirement "+row["id"])
    for entry in pack["legacy_author_index_mapping"]:
        if not set(entry["requirement_ids"])<=set(rows):
            raise ValueError("Unknown Title IV migration target")
    return pack

def load_clp(root=ROOT, annex_pack=None, title_pack=None):
    """Load CLP candidates with immutable IDs; no date-specific compliance conclusion."""
    pack = read(root / "regulatory/canonical/clp.json")
    source = next(s for s in read(root/"regulatory/source_manifest.json")["sources"] if s["id"]=="clp")
    if pack["schema"]!="sds-canonical-clp/v1" or pack["source_id"]!="clp" or pack["source_version"]!=source["version"] or pack["source_sha256"]!=source["sha256"]:
        raise ValueError("CLP source identity mismatch")
    records = {r["id"]:r for r in pack["source_records"]}
    rows = {r["id"]:r for r in pack["requirements"]}
    if len(records)!=len(pack["source_records"]) or len(rows)!=len(pack["requirements"]):
        raise ValueError("Duplicate CLP identifiers")
    if annex_pack is None:
        annex_pack, _, _ = load(root)
    if title_pack is None:
        title_pack = load_title_iv(root,annex_pack)
    previous = {r["id"] for p in (annex_pack,title_pack) for r in p["requirements"]}
    if previous & set(rows):
        raise ValueError("Duplicate cross-component CLP identifiers")
    known = previous | set(rows)
    required = set("id source_id source_version legal_authority_type clause table_references printed_pages pdf_pages source_record_ids context_record_ids wording applicability_conditions exceptions required_product_evidence required_sds_content assessment_methodology related_requirements sds_section effective_date transition_rules verification_status implementation_status test_ids modality".split())
    for record in records.values():
        if not record["wording"].strip() or not record["pdf_pages"] or any(type(n) is not int or not 1<=n<=source["pages"] for n in record["pdf_pages"]):
            raise ValueError("Invalid CLP source record "+record["id"])
    for row in rows.values():
        if not required <= set(row) or not row["id"].startswith("EU-CLP-"):
            raise ValueError("Invalid CLP requirement schema")
        refs = [records[k] for k in row["source_record_ids"]]
        if (not refs or row["wording"]!=" ".join(r["wording"] for r in refs)
                or row["source_id"]!="clp" or row["source_version"]!=source["version"]
                or row["legal_authority_type"]!="binding_law_via_consolidation"
                or row["pdf_pages"]!=list(dict.fromkeys(n for r in refs for n in r["pdf_pages"]))
                or row["printed_pages"]!=list(dict.fromkeys(n for r in refs for n in r["printed_pages"]))
                or not set(row["context_record_ids"])<=set(records)
                or not set(row["related_requirements"])<=known
                or row["assessment_methodology"] not in METHODS
                or row["implementation_status"]!="manual_review_only"):
            raise ValueError("Invalid CLP requirement "+row["id"])
    for old in pack.get("historical_versions", []):
        row = old["record"]
        if row["id"] not in rows or not old.get("reason") or digest(row)==digest(rows[row["id"]]):
            raise ValueError("Invalid historical CLP requirement")
        if row["wording"]!=" ".join(r["wording"] for r in old["source_records"]):
            raise ValueError("Invalid archived CLP source trace")
    for table in pack["reference_tables"]:
        if table["id"] not in records or table["execution"]!="reference_only" or not set(table["related_requirements"])<=set(rows):
            raise ValueError("Invalid CLP reference table")
    return pack

def clp_coverage(pack):
    return {"release":pack["release"],"coverage":"candidate_partial",
            "gaps":pack["coverage_gaps"],
            "requirements":[{"id":r["id"],"clause":r["clause"],"version":requirement_version(r),
                "verification_status":r["verification_status"],"implementation_status":r["implementation_status"]}
                for r in pack["requirements"]]}

def verify_clp_pdf(pack, source_pdf):
    """Check supplied PDF identity and normalized text spans; this does not verify layout or legal applicability."""
    source_pdf = Path(source_pdf)
    if hashlib.sha256(source_pdf.read_bytes()).hexdigest()!=pack["source_sha256"]:
        raise ValueError("Changed CLP source PDF")
    pages = subprocess.check_output(["pdftotext","-layout",str(source_pdf),"-"]).decode("utf-8").split("\f")
    def normalize(text):
        text = re.sub(r"(?m)^.*02008R1272.*031\.001.*$", "", text)
        text = re.sub(r"[▼►](?:[MBC]\d*)|◄", "", text)
        text = re.sub(r"\u00ad\s*", "", text)
        return re.sub(r"\s+", "", text).replace("’","'").replace("‘","'").replace("“",'"').replace("”",'"')
    missing=[]
    for row in pack["source_records"]:
        source = normalize(" ".join(pages[n-1] for n in row["pdf_pages"]))
        needle = normalize(row["wording"])
        if needle not in source:
            missing.append(row["id"])
    return {"checked":len(pack["source_records"]),"unmatched":missing,
            "status":"text_match_only" if not missing else "manual_reconciliation_required"}

def all_requirements(root=ROOT):
    annex, _, _ = load(root)
    title = load_title_iv(root,annex)
    return annex["requirements"] + title["requirements"] + load_clp(root,annex,title)["requirements"]

def resolve_any_requirement_version(identifier, version, root=ROOT):
    annex, _, _ = load(root)
    title = load_title_iv(root,annex)
    return (resolve_requirement_version(annex,identifier,version)
            or resolve_requirement_version(title,identifier,version)
            or resolve_requirement_version(load_clp(root,annex,title),identifier,version))

def title_iv_coverage(pack):
    return {str(n): {"requirements":[{"id":r["id"],"version":requirement_version(r),
        "verification_status":r["verification_status"],"implementation_status":r["implementation_status"]}
        for r in pack["requirements"] if r["clause"].startswith("Article "+str(n))],
        "coverage":"candidate_pending_independent_verification"} for n in range(31,37)}

def build(out, root=ROOT, source_dir=None):
    pack, raw, sources = load(root)
    out.mkdir(parents=True, exist_ok=True)
    rows = pack["requirements"]
    title = load_title_iv(root,pack)
    clp = load_clp(root,pack,title)
    all_rows = rows + title["requirements"] + clp["requirements"]
    (out/"clp.json").write_text(json.dumps(clp,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"clp_coverage.json").write_text(json.dumps(clp_coverage(clp),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"all_requirements.json").write_text(json.dumps({"schema":"sds-canonical-combined/v1",
        "releases":{"annex_ii":pack["release"],"title_iv":title["release"],"clp":clp["release"]},
        "requirements":all_rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"title_iv.json").write_text(json.dumps(title,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"all_requirements.jsonl").write_bytes(jsonl(all_rows).encode("utf-8"))
    (out/"title_iv_coverage.json").write_text(json.dumps(title_iv_coverage(title),ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"requirements.json").write_text(json.dumps(pack,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"requirements.jsonl").write_bytes(jsonl(rows).encode("utf-8"))
    (out/"coverage_matrix.json").write_bytes(json_text(coverage_matrix(pack,raw)).encode("utf-8"))
    (out/"coverage.json").write_text(json.dumps(coverage(pack,raw),ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"migration.json").write_text(json.dumps(pack["migration"],ensure_ascii=False,indent=2),encoding="utf-8")
    path = out/"requirements.sqlite"
    if path.exists():
        raise FileExistsError("Use an empty output directory for SQLite generation")
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""CREATE TABLE requirement(id TEXT PRIMARY KEY, version TEXT, clause TEXT, payload TEXT);
        CREATE TABLE source_record(id TEXT PRIMARY KEY, authority TEXT, clause TEXT, page INTEGER, payload TEXT);
        CREATE TABLE migration(legacy_id TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE source_manifest(id TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE historical_requirement(id TEXT, version TEXT, payload TEXT, PRIMARY KEY(id,version));
        CREATE TABLE enforcement_crosswalk(id TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE reference_table(id TEXT PRIMARY KEY, payload TEXT);
        CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, authority UNINDEXED, clause, body);""")
        for source in sources.values():
            db.execute("INSERT INTO source_manifest VALUES (?,?)",(source["id"],json.dumps(source,ensure_ascii=False)))
        for r in all_rows:
            db.execute("INSERT INTO requirement VALUES (?,?,?,?)",(r["id"],requirement_version(r),r["clause"],json.dumps(r,ensure_ascii=False)))
            db.execute("INSERT INTO search VALUES (?,?,?,?)",(r["id"],r["legal_authority_type"],r["clause"],r["wording"]))
        for table in clp["reference_tables"]:
            db.execute("INSERT INTO reference_table VALUES (?,?)",(table["id"],json.dumps(table,ensure_ascii=False)))
        for old in pack.get("historical_versions", []) + clp.get("historical_versions", []):
            r = old["record"]
            db.execute("INSERT INTO historical_requirement VALUES (?,?,?)",(r["id"],requirement_version(r),json.dumps(old,ensure_ascii=False)))
        for link in pack.get("enforcement_crosswalk", []):
            db.execute("INSERT INTO enforcement_crosswalk VALUES (?,?)",(link["id"],json.dumps(link,ensure_ascii=False)))
        for r in title["source_records"] + clp["source_records"]:
            db.execute("INSERT INTO source_record VALUES (?,?,?,?,?)",(r["id"],"legislation_consolidation",r["clause"],r["pdf_pages"][0],json.dumps(r,ensure_ascii=False)))
            db.execute("INSERT INTO search VALUES (?,?,?,?)",(r["id"],"legislation_consolidation",r["clause"],r["wording"]))
        for i,r in enumerate(raw):
            r = dict(r, legacy_id="annex/"+str(i), annotation=pack.get("source_annotations",{}).get("annex/"+str(i),{}))
            key="source/reach/"+digest(raw[i])
            if db.execute("INSERT OR IGNORE INTO source_record VALUES (?,?,?,?,?)",(key,"legislation_consolidation",r["annotation"].get("corrected_clause",r["clause"]),r["page"],json.dumps(r,ensure_ascii=False))).rowcount:
                db.execute("INSERT INTO search VALUES (?,?,?,?)",(key,"legislation_consolidation",r["annotation"].get("corrected_clause",r["clause"]),r["text"]))
        for m in pack["migration"] + title["legacy_author_index_mapping"]:
            db.execute("INSERT INTO migration VALUES (?,?)",(m["legacy_id"],json.dumps(m,ensure_ascii=False)))
        for key,r in read(root/"regulatory/assessment/clp_english.json").items():
            db.execute("INSERT INTO search VALUES (?,?,?,?)",("wording/"+key,"legislation_consolidation","CLP statement reference",r["wording"]))
        for q in read(root/"regulatory/assessment/ref11.json"):
            db.execute("INSERT INTO search VALUES (?,?,?,?)",("REF11/"+q[0],"enforcement_report",q[0]," ".join(map(str,q[1:4]))))
        if source_dir is not None:
            for source in sources.values():
                pdf = Path(source_dir) / source["filename"]
                if hashlib.sha256(pdf.read_bytes()).hexdigest() != source["sha256"]:
                    raise ValueError("Changed PDF: " + source["id"])
                pages = subprocess.check_output(["pdftotext","-layout",str(pdf),"-"]).decode("utf-8").split("\f")
                if len(pages) != source["pages"] + 1 or pages[-1].strip():
                    raise ValueError("Unexpected PDF page boundaries: " + source["id"])
                for page, body in enumerate(pages[:-1], 1):
                    key = "pdf/" + source["id"] + "/" + source["sha256"] + "/" + str(page)
                    payload = {"source_id":source["id"],"version":source["version"],"pdf_page":page,
                               "printed_page":None,"text":body,"extraction_status":"unverified_layout"}
                    db.execute("INSERT INTO source_record VALUES (?,?,?,?,?)",(key,source["authority"],"",page,json.dumps(payload,ensure_ascii=False)))
                    db.execute("INSERT INTO search VALUES (?,?,?,?)",(key,source["authority"],"",body))
    return path

def search(path, query, limit=30):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT id,authority,clause,body FROM search WHERE search MATCH ? LIMIT ?",(query,limit)).fetchall()

def retrieve_clause(path, clause):
    """Exact clause matches, including original extraction records."""
    with closing(sqlite3.connect(path)) as db:
        return {
            "requirements":[json.loads(x[0]) for x in db.execute("SELECT payload FROM requirement WHERE clause = ? ORDER BY id",(clause,))],
            "source_records":[json.loads(x[0]) for x in db.execute("SELECT payload FROM source_record WHERE clause = ? ORDER BY page,id",(clause,))],
        }

def resolve_legacy(pack, legacy_id):
    """Return migration disposition; never auto-approve a replacement."""
    return next((m for m in pack["migration"] if m["legacy_id"] == legacy_id), None)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path,nargs="?",help="Empty output directory for generated exports and SQLite")
    p.add_argument("--sources",type=Path,help="Optional verified five-PDF directory; requires pdftotext")
    p.add_argument("--sync-committed",action="store_true",help="Regenerate committed requirements.jsonl and coverage_matrix.json")
    p.add_argument("--check-committed",action="store_true",help="Exit 1 if committed generated exports are stale")
    args=p.parse_args()
    if args.check_committed or args.sync_committed:
        stale=sync_committed(check=args.check_committed)
        print(json.dumps({"stale" if args.check_committed else "regenerated":stale}))
        raise SystemExit(1 if args.check_committed and stale else 0)
    if args.out is None:
        p.error("Provide an output directory, --sync-committed or --check-committed")
    print(build(args.out, source_dir=args.sources))
