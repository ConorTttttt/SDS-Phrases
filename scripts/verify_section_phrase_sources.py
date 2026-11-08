"""Verify that each curated SDS phrase mapping still matches local eSDScom 5.5.

No phrase text is written to stdout, files or Git. No legal applicability is
assessed. Run: python3 scripts/verify_section_phrase_sources.py [db path]
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from section_recommendations import load_candidates, _matching_catalogue_record


def main():
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "catalogue.sqlite"
    if not db.is_file():
        print(json.dumps({"status": "missing_local_catalogue", "path": str(db)}))
        raise SystemExit(2)
    pack = load_candidates()
    with sqlite3.connect(db) as conn:
        failures = []
        successes = []
        for rule in pack["rules"]:
            row, reason = _matching_catalogue_record(conn, rule)
            if reason:
                failures.append({"rule_id": rule["id"], "code": rule["structurecode"], "error": reason})
            else:
                successes.append({"rule_id": rule["id"], "entry_key": row["entry_key"]})
    print(json.dumps({
        "pack": pack["id"], "expected_rules": len(pack["rules"]),
        "exact_matches": len(successes), "blocked_matches": len(failures),
        "matching_rule_ids": [s["rule_id"] for s in successes],
        "failures": failures,
        "notice": "Exact source matching only, not independent legal verification.",
    }, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
