"""Canonical requirement registry; offline, stdlib only. No legal certification."""
import argparse
import hashlib
import json
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
    return pack, raw, sources

def requirement_version(row):
    return digest(row)

def coverage(pack, raw):
    result = {}
    for i, m in enumerate(pack["migration"]):
        section = raw[int(m["legacy_id"].split("/")[1])]["clause"].split(".")[0]
        entry = result.setdefault(section, {"source_records":0,"linked_source_records":0,
             "unmapped_source_records":0,"requirements":[], "coverage":"incomplete"})
        entry["source_records"] += 1
        entry["linked_source_records" if m["requirement_ids"] else "unmapped_source_records"] += 1
    for r in pack["requirements"]:
        section = r["clause"].split()[-1].split(".")[0]
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

def build(out, root=ROOT, source_dir=None):
    pack, raw, sources = load(root)
    out.mkdir(parents=True, exist_ok=True)
    rows = pack["requirements"]
    (out/"requirements.json").write_text(json.dumps(pack,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"requirements.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in rows),encoding="utf-8")
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
        CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, authority UNINDEXED, clause, body);""")
        for source in sources.values():
            db.execute("INSERT INTO source_manifest VALUES (?,?)",(source["id"],json.dumps(source,ensure_ascii=False)))
        for r in rows:
            db.execute("INSERT INTO requirement VALUES (?,?,?,?)",(r["id"],requirement_version(r),r["clause"],json.dumps(r,ensure_ascii=False)))
            db.execute("INSERT INTO search VALUES (?,?,?,?)",(r["id"],r["legal_authority_type"],r["clause"],r["wording"]))
        for i,r in enumerate(raw):
            key="source/reach/"+digest(r)
            if db.execute("INSERT OR IGNORE INTO source_record VALUES (?,?,?,?,?)",(key,"legislation_consolidation",r["clause"],r["page"],json.dumps(r,ensure_ascii=False))).rowcount:
                db.execute("INSERT INTO search VALUES (?,?,?,?)",(key,"legislation_consolidation",r["clause"],r["text"]))
        for m in pack["migration"]:
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
    p.add_argument("out",type=Path)
    p.add_argument("--sources",type=Path,help="Optional verified five-PDF directory; requires pdftotext")
    args=p.parse_args()
    print(build(args.out, source_dir=args.sources))
