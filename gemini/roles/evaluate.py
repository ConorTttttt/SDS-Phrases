"""Display a blind prompt or its expected outcome from a generated role package."""
import argparse
import json
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("case")
    parser.add_argument("--expected", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.suite.read_text(encoding="utf-8"))
    item = next((r for r in cases if r["id"] == args.case), None)
    if item is None:
        parser.error("Unknown case. Available IDs: " + ", ".join(r["id"] for r in cases))
    print(item["expected"] if args.expected else item["prompt"])
