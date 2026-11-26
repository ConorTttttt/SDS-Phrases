"""Selective local exchange for sds_assessment findings.json. Writes only new files."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ["Compliant against assessed requirement", "Non-compliant", "Potential non-compliance",
          "Insufficient evidence", "Not applicable", "Not assessed", "Requires competent-person review"]
DIMENSIONS = "applicability presence completeness regulatory_adequacy scientific_plausibility internal_consistency expert_judgement".split()
FIELDS = ["original_wording", "product_evidence", "page", "section", "calculation"]
DETERMINATIVE = STATUS[:2]
STRING = {"type": "string", "minLength": 1}


def obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def versions(rows=()):
    result = {s["id"]: s["version"] + "/" + s["sha256"] for s in read(ROOT/"regulatory/source_manifest.json")["sources"]}
    pinned = {r["id"]:r["rule_version"] for r in rows if r.get("rule_version")}
    if pinned:
        result["canonical_rule_snapshot"] = digest(pinned)
    traces = {r["id"]: r["evaluator_trace"]["trace_digest"] for r in rows if isinstance(r.get("evaluator_trace"), dict)}
    if traces:
        result["evaluator_trace_snapshot"] = digest(traces)
    return result


HEADER = {"product_id": STRING, "document_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
          "sources": {"type": "object", "additionalProperties": STRING}}
RECORD = obj({"id": STRING, "field": {"enum": FIELDS}, "value": STRING, "requirement_id": STRING})
INTAKE = obj({**HEADER, "evidence": array(RECORD), "export_id": STRING})
FINDING = obj({"requirement_id": STRING, "evidence_ids": array(STRING), "source_id": STRING,
               "citation": STRING, "status": {"enum": STATUS}, "interpretation": STRING,
               "requested_action": STRING, **dict.fromkeys(DIMENSIONS, STRING)})
OUTPUT = obj({**HEADER, "export_id": STRING, "findings": array(FINDING)})


def prepare(rows, product, selections):
    docs = {r["document_sha256"] for r in rows}
    if len(docs) != 1 or not product.strip():
        raise ValueError("Select a single identified product and document")
    indexed = {r["id"]: r for r in rows}
    evidence = []
    for selection in sorted(set(selections)):
        key, field = selection.rsplit(":", 1)
        if field not in FIELDS or not indexed[key][field]:
            raise ValueError("Unavailable evidence field: " + selection)
        evidence.append(dict(id=selection, field=field, value=indexed[key][field], requirement_id=key))
    data = dict(product_id=product, document_sha256=docs.pop(), sources=versions(rows), evidence=evidence)
    return dict(data, export_id=digest(data))


def validate(rows, bundle, response, product):
    trusted = prepare(rows, product, [e["id"] for e in bundle["evidence"]])
    if trusted != bundle or set(response) != set(OUTPUT["required"]):
        raise ValueError("Export changed or unexpected response shape")
    if any(response[k] != trusted[k] for k in (*HEADER, "export_id")):
        raise ValueError("Mismatched product, document, export or source snapshot")
    known = {r["id"] for r in rows}
    indexed_rows = {r["id"]: r for r in rows}
    selected = {e["id"] for e in trusted["evidence"]}
    if not isinstance(response["findings"], list):
        raise ValueError("Expected findings array")
    for f in response["findings"]:
        if set(f) != set(FINDING["required"]) or f["requirement_id"] not in known:
            raise ValueError("Unknown finding shape or requirement")
        if f["status"] not in STATUS or f["source_id"] not in trusted["sources"]:
            raise ValueError("Unknown status or source")
        for k in ["citation", "interpretation", "requested_action", *DIMENSIONS]:
            if not isinstance(f[k], str) or not f[k].strip():
                raise ValueError("Missing " + k)
        trace = indexed_rows[f["requirement_id"]].get("evaluator_trace")
        if isinstance(trace, dict) and not trace["verification"]["promotion_gate"]["open"] and f["status"] in DETERMINATIVE:
            raise ValueError("Review gate closed for " + f["requirement_id"] + ": model cannot return a compliance conclusion")
        ids = f["evidence_ids"]
        if not isinstance(ids, list) or any(i not in selected for i in ids):
            raise ValueError("Unknown evidence")
        if not ids and f["status"] not in STATUS[3:4] + STATUS[5:]:
            raise ValueError("Conclusion requires evidence")
    return {"review_status": "pending human review", "model_response": response}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["export", "import"])
    p.add_argument("rows", type=Path)
    p.add_argument("product")
    p.add_argument("output", type=Path)
    p.add_argument("--select", action="append", default=[])
    p.add_argument("--bundle", type=Path)
    p.add_argument("--response", type=Path)
    a = p.parse_args()
    rows = read(a.rows)
    if a.action == "export":
        result = prepare(rows, a.product, a.select)
    else:
        if not a.bundle or not a.response:
            p.error("import requires --bundle and --response")
        result = validate(rows, read(a.bundle), read(a.response), a.product)
    with a.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
