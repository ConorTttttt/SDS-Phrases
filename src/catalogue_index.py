"""Non-destructive catalogue browsing index; mappings are not legal requirements."""
from __future__ import annotations
import collections
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

INDEX_REVISION = "1"
SECTIONS = {
    1:"Identification",2:"Hazards identification",3:"Composition",4:"First-aid measures",
    5:"Firefighting measures",6:"Accidental release measures",7:"Handling and storage",
    8:"Exposure controls and personal protection",9:"Physical and chemical properties",
    10:"Stability and reactivity",11:"Toxicological information",12:"Ecological information",
    13:"Disposal considerations",14:"Transport information",15:"Regulatory information",16:"Other information",
}
# Browsing labels only, not legally verified subsection assignment for any jurisdiction.
SUBSECTIONS = {
    1:{1:"Product identifier",2:"Identified uses",3:"Supplier details",4:"Emergency telephone"},
    2:{1:"Classification",2:"Label elements",3:"Other hazards"},
    3:{1:"Substances",2:"Mixtures"},
    4:{1:"First-aid description",2:"Symptoms and effects",3:"Medical attention"},
    5:{1:"Extinguishing media",2:"Special hazards",3:"Advice for firefighters"},
    6:{1:"Personal precautions",2:"Environmental precautions",3:"Containment and cleaning",4:"Other sections"},
    7:{1:"Safe handling",2:"Safe storage",3:"Specific end use"},
    8:{1:"Control parameters",2:"Exposure controls"},
    9:{1:"Basic physical and chemical properties",2:"Other information"},
    10:{1:"Reactivity",2:"Chemical stability",3:"Hazardous reactions",4:"Conditions to avoid",5:"Incompatible materials",6:"Decomposition products"},
    11:{1:"Hazard-class information",2:"Other hazards"},
    12:{1:"Toxicity",2:"Persistence and degradability",3:"Bioaccumulative potential",4:"Mobility in soil",5:"PBT/vPvB assessment",6:"Endocrine disrupting properties",7:"Other adverse effects"},
    13:{1:"Waste treatment methods"},
    14:{1:"UN/ID number",2:"Proper shipping name",3:"Transport hazard class",4:"Packing group",5:"Environmental hazards",6:"Special precautions",7:"Maritime transport in bulk"},
    15:{1:"Specific legislation",2:"Chemical safety assessment"},
}
ROOTS = frozenset(("01","02","03","04","05","06","07","08"))

def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def duplicate_key(text: str) -> str:
    """For discovery only: never change the original wording or collapse source rows."""
    clean = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    return digest(clean) if clean else ""

def revision_date(raw: str) -> str:
    """Excel catalogue revision serial, not legal effective date."""
    if not raw:
        return ""
    try:
        serial = float(raw)
        if not 1 <= serial <= 100000 or not serial.is_integer():
            return ""
        return (datetime(1899,12,30)+timedelta(days=int(serial))).date().isoformat()
    except (TypeError,ValueError,OverflowError):
        return ""

def classify(record: sqlite3.Row) -> dict:
    code = record["structurecode"] or ""
    segments = code.rstrip(".").split(".")
    root = segments[0] if segments else ""
    subsection = ""
    topic = ""
    quality = []
    if record["collection"] == "ExpoScenario":
        category = "Exposure scenario (annex)"
    elif root not in ROOTS:
        category = "Special / non-SDS structure"
    else:
        category = "Catalogue header / unassigned"
        if len(segments) >= 2 and segments[1].isdigit():
            number = int(segments[1])
            if number in SECTIONS:
                category = SECTIONS[number]
                if len(segments) >= 3 and segments[2].isdigit():
                    sub = int(segments[2])
                    if sub in SUBSECTIONS.get(number, {}):
                        subsection = f"{number}.{sub}"
                        topic = SUBSECTIONS[number][sub]
                    elif sub != 0:
                        quality.append("unmapped_catalogue_subsection")
    if not code:
        quality.append("missing_structurecode")
    if root not in ROOTS:
        quality.append("non_sds_structure")
    phrase = record["english"] or ""
    if not phrase:
        quality.append("missing_english")
    if re.search(r"<\s*parm\s*/\s*>|\{[^{}]+\}|\[[^\[\]]+\]", phrase, re.I):
        quality.append("possible_parameter_or_placeholder")
    if record["grammar"] not in ("Sentence","List-Element","Header","List-Start","Data","Other","leer",""):
        quality.append("unfamiliar_grammar")
    kind = {"Sentence":"sentence","List-Element":"list_item","List-Start":"list_start","Header":"heading","Data":"data"}.get(record["grammar"],"other")
    return {
        "entry_key":record["entry_key"],"sds_subsection":subsection,"sds_topic":topic,
        "category":category,"phrase_kind":kind,"wording_hash":digest(json.dumps((
            phrase,code,record["catalogue_version"],record["revision_date_raw"],
            record["source_file"],record["excel_row"],record["original_code"],
            record["phrase_owner"],record["source"],record["info"],record["qualifier"]
        ),ensure_ascii=False)),
        "wording_group":duplicate_key(phrase),"revision_date_iso":revision_date(record["revision_date_raw"]),
        "quality_flags":json.dumps(quality,ensure_ascii=False),"flags_count":len(quality),
        "catalogue_version":record["catalogue_version"],
    }

def build_index(conn: sqlite3.Connection, source_sha256: str = "") -> dict:
    """Atomically rebuild browse metadata, leaving original rows untouched."""
    conn.row_factory = sqlite3.Row
    if not source_sha256 and conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_metadata'").fetchone():
        old = conn.execute("SELECT value FROM catalogue_metadata WHERE name='source_archive_sha256'").fetchone()
        source_sha256 = old[0] if old else ""
    source = conn.execute("""SELECT entry_key,collection,structurecode,english,grammar,
        revision_date_raw,catalogue_version,source_file,excel_row,original_code,phrase_owner,
        source,info,qualifier FROM entries""").fetchall()
    computed = [classify(row) for row in source]
    group_counts = collections.Counter(item["wording_group"] for item in computed if item["wording_group"])
    group_contexts = collections.defaultdict(set)
    for row,item in zip(source,computed):
        if item["wording_group"]:
            group_contexts[item["wording_group"]].add((row["collection"],row["structurecode"]))
    # Explicit transaction makes DDL replacement atomic.
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        conn.execute("DROP TABLE IF EXISTS catalogue_index")
        conn.execute("DROP TABLE IF EXISTS catalogue_metadata")
        conn.execute("""CREATE TABLE catalogue_index (
            entry_key TEXT PRIMARY KEY,sds_subsection TEXT NOT NULL,
            sds_topic TEXT NOT NULL,category TEXT NOT NULL,phrase_kind TEXT NOT NULL,
            wording_hash TEXT NOT NULL,wording_group TEXT NOT NULL,
            duplicate_count INTEGER NOT NULL,duplicate_contexts INTEGER NOT NULL,
            revision_date_iso TEXT NOT NULL,quality_flags TEXT NOT NULL,flags_count INTEGER NOT NULL
        )""")
        conn.executemany("INSERT INTO catalogue_index VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",[(
            item["entry_key"],item["sds_subsection"],item["sds_topic"],item["category"],
            item["phrase_kind"],item["wording_hash"],item["wording_group"],
            group_counts.get(item["wording_group"],0),len(group_contexts.get(item["wording_group"],())),
            item["revision_date_iso"],item["quality_flags"],item["flags_count"],
        ) for item in computed])
        for name,field in (("subsection","sds_subsection"),("category","category"),
                           ("kind","phrase_kind"),("duplicate","duplicate_count"),("quality","flags_count")):
            conn.execute(f"CREATE INDEX idx_cix_{name} ON catalogue_index({field})")
        conn.execute("CREATE TABLE catalogue_metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL)")
        metadata = {
            "index_revision":INDEX_REVISION,
            "source_archive_sha256":source_sha256 or "not_recorded",
            "indexed_at_utc":datetime.now(timezone.utc).isoformat(),
            "catalogue_versions":json.dumps(sorted(set(x["catalogue_version"] for x in computed))),
            "subsection_mapping_status":"catalogue_path_heuristic_not_regulatory_validation",
        }
        conn.executemany("INSERT INTO catalogue_metadata VALUES (?,?)",metadata.items())
    return {
        "indexed_rows":len(computed),"wording_groups":len(group_counts),
        "duplicate_rows":sum(1 for item in computed if group_counts.get(item["wording_group"],0)>1),
        "flagged_rows":sum(1 for item in computed if item["flags_count"]),
        "subsection_mapped":sum(1 for item in computed if item["sds_subsection"]),
        "special_structures":sum(1 for item in computed if "non_sds_structure" in item["quality_flags"]),
    }

def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: python3 src/catalogue_index.py data/catalogue.sqlite")
    path=Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Catalogue not found: {path}")
    conn=sqlite3.connect(path)
    try:
        print(json.dumps(build_index(conn),indent=2))
    finally:
        conn.close()

if __name__=="__main__":
    main()
