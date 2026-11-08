"""Check exact original licensed eSDScom 5.5 Core wording for family mappings.

Prints source code identifiers and SHA validation status only; original
licensed English text is never copied into Git or printed to stdout.

Run:
    python3 scripts/verify_family_phrase_sources.py [data/catalogue.sqlite]
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from catalogue_browser import connect
from chemical_families import load_family_pack


def verify(db_path):
    pack=load_family_pack()
    try:
        connection=connect(db_path)
    except (FileNotFoundError,sqlite3.Error) as exc:
        return {"status":"missing_or_unindexed_local_catalogue",
                "error":str(exc),"exact_matches":0,"blocked_mappings":len(pack["rules"])}
    results=[]
    try:
        for rule in pack["rules"]:
            matches=[dict(r) for r in connection.execute(
                """SELECT e.collection,e.catalogue_version,e.structurecode,e.english,
                          e.sds_section,e.jurisdiction_structure,e.grammar,
                          i.wording_hash,i.quality_flags
                   FROM entries e LEFT JOIN catalogue_index i
                   ON i.entry_key=e.entry_key
                   WHERE e.collection='Core' AND e.structurecode=?""",
                (rule["structurecode"],))]
            status="source_changed_or_missing"
            if len(matches)==1:
                actual=matches[0]
                try:flags=json.loads(actual["quality_flags"]) if actual["quality_flags"] else None
                except (ValueError,TypeError):flags=None
                if (actual["catalogue_version"]=="5.5" and
                    actual["jurisdiction_structure"]=="EU" and
                    actual["sds_section"]==rule["section"] and
                    actual["grammar"]==rule["expected_grammar"] and
                    isinstance(actual["wording_hash"],str) and
                    len(actual["wording_hash"])==64 and flags==[] and
                    actual["english"] and
                    hashlib.sha256(actual["english"].encode("utf8")).hexdigest() ==
                        rule["expected_english_sha256"]):
                    status="exact_original_source_match"
            results.append({
                "rule_id":rule["id"],"family":rule["family"],
                "structurecode":rule["structurecode"],"status":status,
            })
    finally:
        connection.close()
    matched=sum(x["status"]=="exact_original_source_match" for x in results)
    return {
        "status":"passed" if matched==len(results) else "failed",
        "family_count":len(pack["families"]),
        "mappings":len(results),"unique_source_codes":len({r["structurecode"] for r in pack["rules"]}),
        "exact_matches":matched,"blocked_mappings":len(results)-matched,
        "failures":[x for x in results if x["status"]!="exact_original_source_match"],
        "notice":"Exact source identity only. This does NOT verify chemical-family applicability, legal label conditions, safe handling or SDS completeness.",
    }


if __name__=="__main__":
    db=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/"data"/"catalogue.sqlite"
    data=verify(db)
    print(json.dumps(data,indent=2))
    if data["status"]!="passed":
        raise SystemExit(1)
