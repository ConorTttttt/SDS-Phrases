"""Read-only catalogue search, provenance and quality reporting."""
from __future__ import annotations
import collections
import json
import sqlite3
from pathlib import Path
from catalogue_index import SECTIONS

COLLECTIONS=("Core","ExpoScenario","ALL")
STRUCTURES=("EU","GB","UN","US","MX","AR","BR","CN","ALL")
KINDS=("sentence","list_item","list_start","heading","data","other","ALL")

class CatalogueQueryError(ValueError):
    pass

def connect(path):
    if not Path(path).is_file():
        raise FileNotFoundError("Import your original eSDScom ZIP to populate the local catalogue.")
    conn=sqlite3.connect(path)
    conn.row_factory=sqlite3.Row
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_index'").fetchone():
        conn.close()
        raise FileNotFoundError("Catalogue indexing required: python3 src/catalogue_index.py data/catalogue.sqlite")
    return conn

def search(path, *, query="", jurisdiction="EU", collection="Core", section="",
           subsection="", kind="ALL", duplicates="all", quality="all", limit=40, offset=0):
    if jurisdiction not in STRUCTURES:
        raise CatalogueQueryError("Unknown catalogue structure.")
    if collection not in COLLECTIONS or kind not in KINDS:
        raise CatalogueQueryError("Unknown collection or phrase kind.")
    if duplicates not in ("all","repeated","unique") or quality not in ("all","flagged","clear"):
        raise CatalogueQueryError("Unknown duplicate or quality filter.")
    if section and (not str(section).isdigit() or not 1<=int(section)<=16):
        raise CatalogueQueryError("Section must be between 1 and 16.")
    if subsection and (not isinstance(subsection,str) or subsection.count(".")!=1 or
        not all(x.isdigit() for x in subsection.split(".")) or
        not 1<=int(subsection.split(".")[0])<=16):
        raise CatalogueQueryError("Invalid subsection.")
    if section and subsection and int(subsection.split(".")[0])!=int(section):
        raise CatalogueQueryError("Subsection does not belong to the selected section.")
    try:
        limit,offset=int(limit),int(offset)
    except (ValueError,TypeError):
        raise CatalogueQueryError("Invalid page parameters.") from None
    if limit<1 or limit>100 or offset<0 or offset>100000:
        raise CatalogueQueryError("Limit must be 1–100 and offset 0–100000.")
    query=str(query).strip()[:160]
    filters,params=[],[]
    if jurisdiction!="ALL":
        filters.append("e.jurisdiction_structure=?");params.append(jurisdiction)
    if collection!="ALL":
        filters.append("e.collection=?");params.append(collection)
    if section:
        filters.append("e.sds_section=?");params.append(int(section))
    if subsection:
        filters.append("i.sds_subsection=?");params.append(subsection)
    if kind!="ALL":
        filters.append("i.phrase_kind=?");params.append(kind)
    if duplicates=="repeated":filters.append("i.duplicate_count>1")
    if duplicates=="unique":filters.append("i.duplicate_count=1")
    if quality=="flagged":filters.append("i.flags_count>0")
    if quality=="clear":filters.append("i.flags_count=0")
    if query:
        literal=query.casefold().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        filters.append("(LOWER(e.english) LIKE ? ESCAPE '\\' OR LOWER(e.original_code) LIKE ? ESCAPE '\\' OR LOWER(e.structurecode) LIKE ? ESCAPE '\\' OR LOWER(e.esdscom_phrase_id) LIKE ? ESCAPE '\\')")
        params.extend(["%"+literal+"%"]*4)
    where=" WHERE "+" AND ".join(filters) if filters else ""
    table=" FROM entries e JOIN catalogue_index i ON i.entry_key=e.entry_key"
    conn=connect(path)
    try:
        total=conn.execute("SELECT COUNT(*)"+table+where,params).fetchone()[0]
        sql="""SELECT e.entry_key,e.catalogue_version,e.collection,e.source_file,e.excel_row,
                       e.structurecode,e.esdscom_phrase_id,e.original_code,e.english,e.region,
                       e.sds_section,e.jurisdiction_structure,e.source,e.info,e.qualifier,
                       e.grammar,e.phrase_owner,e.revision_date_raw,
                       i.sds_subsection,i.sds_topic,i.category,i.phrase_kind,
                       i.wording_hash,i.duplicate_count,i.duplicate_contexts,
                       i.revision_date_iso,i.quality_flags
               """+table+where+" ORDER BY e.collection,e.excel_row LIMIT ? OFFSET ?"
        results=[dict(row) for row in conn.execute(sql,params+[limit,offset])]
        for record in results:record["quality_flags"]=json.loads(record["quality_flags"])
        return {"total":total,"limit":limit,"offset":offset,"results":results,
                "subsection_basis":"derived_catalogue_path_not_legal_requirement"}
    finally:
        conn.close()

def summary(path):
    conn=connect(path)
    try:
        n=conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        indexed=conn.execute("SELECT COUNT(*) FROM catalogue_index").fetchone()[0]
        if n!=indexed:
            raise FileNotFoundError("Catalogue metadata is out of date. Re-run the indexer.")
        counts=dict(conn.execute("SELECT name,value FROM catalogue_metadata"))
        flags=collections.Counter()
        for row in conn.execute("SELECT quality_flags FROM catalogue_index"):
            flags.update(json.loads(row[0]))
        versions=[dict(row) for row in conn.execute("SELECT catalogue_version,collection,COUNT(*) AS records FROM entries GROUP BY catalogue_version,collection ORDER BY catalogue_version,collection")]
        sections=[dict(row) for row in conn.execute("SELECT sds_section,COUNT(*) AS records FROM entries WHERE sds_section BETWEEN 1 AND 16 GROUP BY sds_section ORDER BY sds_section")]
        return {
            "records":n,"index_revision":counts.get("index_revision"),
            "source_archive_sha256":counts.get("source_archive_sha256","not_recorded"),
            "indexed_at_utc":counts.get("indexed_at_utc"),
            "subsection_mapping_status":counts.get("subsection_mapping_status"),
            "wording_groups":conn.execute("SELECT COUNT(DISTINCT wording_group) FROM catalogue_index WHERE wording_group<>''").fetchone()[0],
            "repeated_rows":conn.execute("SELECT COUNT(*) FROM catalogue_index WHERE duplicate_count>1").fetchone()[0],
            "subsection_mapped":conn.execute("SELECT COUNT(*) FROM catalogue_index WHERE sds_subsection<>''").fetchone()[0],
            "quality_flag_counts":dict(sorted(flags.items())),
            "sections":[{**item,"title":SECTIONS[item["sds_section"]]} for item in sections],
            "source_versions":versions,
        }
    finally:
        conn.close()
