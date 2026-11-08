"""Search actual locally licensed eSDScom phrases and build an authoring shortlist.

This is text retrieval, not automated legal applicability. Two discovery modes:
  curated:   source-integrity checked against the 105 *unverified* authoring paths;
  catalogue: browse all imported Core 5.5 source texts in an SDS section.

Never synthesise, paraphrase, translate or alter any source phrase.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from catalogue_browser import connect, CatalogueQueryError, KINDS, STRUCTURES
from catalogue_index import SECTIONS, SUBSECTIONS
from section_recommendations import load_candidates


class PhraseFinderError(ValueError):
    pass


def _valid_params(*, jurisdiction, section, subsection, query, mode, kind, include_flagged, limit, offset):
    if jurisdiction not in STRUCTURES or jurisdiction == "ALL":
        raise PhraseFinderError("Select a specific eSDScom catalogue jurisdiction structure.")
    if str(section) not in {str(i) for i in range(1, 17)}:
        raise PhraseFinderError("Select an SDS section from 1 to 16.")
    number = int(section)
    if subsection:
        if not isinstance(subsection, str) or subsection not in {
                f"{number}.{k}" for k in SUBSECTIONS.get(number, {})}:
            raise PhraseFinderError("Choose a recognised subsection within the selected section.")
    if mode not in ("curated", "catalogue"):
        raise PhraseFinderError("Unknown phrase discovery mode.")
    if mode == "curated" and jurisdiction != "EU":
        raise PhraseFinderError("The 105 curated authoring mappings are EU only. Use full catalogue mode for other structures.")
    if kind not in KINDS:
        raise PhraseFinderError("Unknown source phrase grammar filter.")
    if include_flagged not in ("0", "1"):
        raise PhraseFinderError("include_flagged must be 0 or 1.")
    if not isinstance(query, str) or len(query) > 160 or "\x00" in query:
        raise PhraseFinderError("Query must be text up to 160 characters.")
    try:
        limit, offset = int(limit), int(offset)
    except (ValueError, TypeError) as exc:
        raise PhraseFinderError("Invalid pagination values.") from exc
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
        raise PhraseFinderError("Limit must be 1–100 and offset 0–100000.")
    return number, limit, offset


def _escape_like(word):
    return word.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _curated_rules(pack, section, subsection):
    def hinted(rule):
        if rule.get("subsection_hint"):
            return rule["subsection_hint"]
        reference = rule.get("reference", {}).get("sds_content_context", "")
        matched = re.search(r"\bPart A (\d{1,2}\.\d{1,2})\b", reference)
        return matched.group(1) if matched else ""
    rows = [r for r in pack["rules"] if r["section"] == section and
            (not subsection or hinted(r) == subsection)]
    return {r["structurecode"]: r for r in rows}


def _source_check(row, rule, count):
    if not rule:
        return "not_in_curated_pack", "Not part of the 105 curated mappings."
    if count != 1:
        return "blocked_source_mismatch", "Structure code is not unique in the local Core catalogue."
    text = row["english"]
    if (row["catalogue_version"] != "5.5" or row["collection"] != "Core" or
        row["jurisdiction_structure"] != "EU" or
        row["sds_section"] != rule["section"] or
        not text or hashlib.sha256(text.encode("utf-8")).hexdigest() !=
        rule["expected_english_sha256"] or
        (rule.get("expected_grammar") is not None and
         row["grammar"] != rule["expected_grammar"])):
        return "blocked_source_mismatch", "The exact Core 5.5 wording, grammar, section or source identity does not match the curated rule."
    return "exact_source_match", "Exact source code, wording fingerprint, grammar and version matched; applicability is unassessed."


def find_phrases(path, *, jurisdiction="EU", section="4", subsection="", query="",
                 mode="curated", kind="ALL", include_flagged="0",
                 limit=30, offset=0, pack=None):
    section, limit, offset = _valid_params(
        jurisdiction=jurisdiction, section=section, subsection=subsection,
        query=query, mode=mode, kind=kind, include_flagged=include_flagged,
        limit=limit, offset=offset)
    pack = pack or load_candidates()
    candidates = _curated_rules(pack, section, subsection)
    terms = [word for word in re.split(r"\s+", query.strip()) if word]
    # A bounded search on a local SQLite catalogue; every token must be present
    # in the original text, source code or phrase ID (case-insensitive).
    if len(terms) > 12:
        raise PhraseFinderError("Use 12 or fewer search terms.")
    where = ["e.collection='Core'", "e.jurisdiction_structure=?", "e.sds_section=?",
             "e.english IS NOT NULL", "e.english<>''"]
    params = [jurisdiction, section]
    if mode == "curated":
        if not candidates:
            return {
                "section":section, "subsection":subsection, "mode":mode,
                "jurisdiction_structure":jurisdiction, "results":[],
                "total":0, "limit":limit, "offset":offset,
                "warning":"No curated source codes are assigned to this selection. Try full catalogue mode.",
                "catalogue_rule_count":0
            }
        where.append("e.structurecode IN (" + ",".join("?" for _ in candidates) + ")")
        params.extend(candidates)
    elif subsection:
        where.append("i.sds_subsection=?")
        params.append(subsection)
    if kind != "ALL":
        where.append("i.phrase_kind=?")
        params.append(kind)
    if include_flagged == "0":
        where.append("i.flags_count=0")
    for term in terms:
        pattern = "%" + _escape_like(term) + "%"
        where.append("(LOWER(e.english) LIKE ? ESCAPE '\\' OR "
                     "LOWER(e.structurecode) LIKE ? ESCAPE '\\' OR "
                     "LOWER(COALESCE(e.esdscom_phrase_id,'')) LIKE ? ESCAPE '\\' OR "
                     "LOWER(COALESCE(e.original_code,'')) LIKE ? ESCAPE '\\')")
        params.extend([pattern] * 4)
    table = " FROM entries e JOIN catalogue_index i ON i.entry_key=e.entry_key"
    where_sql = " WHERE " + " AND ".join(where)
    # Ranking is purely a search-quality ordering, NOT an applicability score.
    # Alphabetic, deterministic ordering for snippets and phrase type
    # preferences; when searching, exact/early textual hits appear first.
    order_params = []
    priority = "0"
    if query.strip():
        full = "%" + _escape_like(query.strip()) + "%"
        priority = ("CASE WHEN LOWER(e.english) LIKE ? ESCAPE '\\' THEN 0 "
                    "WHEN LOWER(e.structurecode) LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END")
        order_params = [full, full]
    order_sql = (f" ORDER BY {priority}, i.flags_count, "
                 "CASE WHEN i.phrase_kind='sentence' THEN 0 ELSE 1 END, "
                 "e.excel_row, e.entry_key")
    conn = connect(path)
    try:
        total = conn.execute("SELECT COUNT(*)" + table + where_sql, params).fetchone()[0]
        sql = ("""SELECT e.entry_key,e.catalogue_version,e.collection,e.source_file,e.excel_row,
                         e.structurecode,e.esdscom_phrase_id,e.original_code,e.english,e.region,
                         e.jurisdiction_structure,e.sds_section,e.source,e.info,e.grammar,
                         e.phrase_owner,i.sds_subsection,i.sds_topic,i.phrase_kind,i.wording_hash,
                         i.duplicate_count,i.quality_flags,i.flags_count
                  """ + table + where_sql + order_sql + " LIMIT ? OFFSET ?")
        rows = [dict(x) for x in conn.execute(sql, params + order_params + [limit, offset])]
        # Validate uniqueness across *all* local Core mappings, not only
        # filtered/search-result rows; otherwise duplicate sources can pass.
        codes = sorted({r["structurecode"] for r in rows if r["structurecode"] in candidates})
        counts = {}
        if codes:
            counts = dict(conn.execute(
                "SELECT structurecode,COUNT(*) FROM entries WHERE collection='Core' "
                "AND structurecode IN (" + ",".join("?" for _ in codes) + ") "
                "GROUP BY structurecode", codes))
    finally:
        conn.close()
    results = []
    for row in rows:
        rule = candidates.get(row["structurecode"]) if mode == "curated" else None
        status, rationale = _source_check(row, rule, counts.get(row["structurecode"], 0)) \
            if mode == "curated" else ("catalogue_discovery_only", "Original source wording found by catalogue browsing; suitability not established.")
        flags = json.loads(row.pop("quality_flags"))
        flags_count = row.pop("flags_count")
        is_fragment = row["phrase_kind"] != "sentence"
        selectable = status != "blocked_source_mismatch" and not flags_count or (
            status != "blocked_source_mismatch" and
            "missing_english" not in flags and
            "non_sds_structure" not in flags and
            "unmapped_catalogue_subsection" not in flags
        )
        row.update({
            "source_integrity": status, "source_check_explanation": rationale,
            "curated_rule_id": rule["id"] if rule else None,
            "curated_review_note": rule["review_note"] if rule else None,
            "curated_subsection_hint": (
                rule.get("subsection_hint") or
                (re.search(r"\bPart A (\d{1,2}\.\d{1,2})\b",
                           rule.get("reference", {}).get("sds_content_context", "")) or [None, ""])[1]
            ) if rule else None,
            "source_flags": flags,
            "text_sha256": hashlib.sha256(row["english"].encode("utf-8")).hexdigest(),
            "is_fragment": is_fragment,
            "requires_manual_completion": is_fragment or "possible_parameter_or_placeholder" in flags,
            "selectable_for_draft": bool(selectable),
            "legal_applicability_verified": False,
            "sds_phrase_approved": False,
        })
        results.append(row)
    return {
        "section":section,"subsection":subsection,"mode":mode,
        "jurisdiction_structure":jurisdiction, "results":results,"total":total,
        "limit":limit,"offset":offset,"catalogue_rule_count":len(candidates) if mode=="curated" else None,
        "sort_basis":"keyword_text_match_then_source_quality_then_source_order_not_regulatory_ranking",
        "warning":("Original local eSDScom phrase wording. A source match, including a curated one, "
                   "does not establish legal applicability or SDS adequacy. "
                   "Subsection assignments outside curated mappings are catalogue heuristics. "
                   "Review placeholders, table fragments, current law and product-specific suitability before use.")
    }


def finder_sections(path):
    """Return 16 section labels, catalogue record counts and curated code counts."""
    from catalogue_index import SECTIONS
    pack = load_candidates()
    conn = connect(path)
    try:
        rows = dict(conn.execute(
            "SELECT sds_section,COUNT(*) FROM entries WHERE collection='Core' "
            "AND jurisdiction_structure='EU' AND sds_section BETWEEN 1 AND 16 "
            "AND english IS NOT NULL AND english<>'' GROUP BY sds_section"))
    finally:
        conn.close()
    counts = {}
    for rule in pack["rules"]:
        counts[rule["section"]] = counts.get(rule["section"], 0) + 1
    return {
        "catalogue_version":"5.5",
        "jurisdiction_structure":"EU",
        "sections":[{"section":s,"title":name,"total_source_phrases":rows.get(s,0),
                     "curated_candidate_codes":counts.get(s,0),
                     "subsections":[{"code":f"{s}.{sub}","title":title}
                                    for sub,title in SUBSECTIONS.get(s,{}).items()]}
                    for s,name in SECTIONS.items()],
        "notice":"Counts are original source entries, not legally suitable phrases or verified SDS coverage."
    }


def validate_draft(path, items):
    """Read-only freshness check for locally retained draft source references.

    Fail closed on a missing, modified, repeated or stale catalogue row. This
    does not approve text or confirm its regulatory applicability.
    """
    if not isinstance(items, list) or len(items) > 200:
        raise PhraseFinderError("Draft validation requires an array of at most 200 entries.")
    seen = set()
    valid = []
    for row in items:
        if not isinstance(row, dict) or set(row) != {
            "entry_key", "structurecode", "sds_section",
            "wording_hash", "text_sha256", "catalogue_version"
        }:
            raise PhraseFinderError("Invalid draft source snapshot fields.")
        key = row["entry_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key) or key in seen:
            raise PhraseFinderError("Invalid or duplicated draft source entry.")
        seen.add(key)
        if not isinstance(row["structurecode"], str) or not 2 <= len(row["structurecode"]) <= 100:
            raise PhraseFinderError("Invalid draft source code.")
        if type(row["sds_section"]) is not int or row["sds_section"] not in range(1,17):
            raise PhraseFinderError("Invalid draft SDS section.")
        if any(not isinstance(row[x], str) or not re.fullmatch(r"[0-9a-f]{64}", row[x])
               for x in ("wording_hash", "text_sha256")):
            raise PhraseFinderError("Invalid draft wording hashes.")
        if row["catalogue_version"] != "5.5":
            raise PhraseFinderError("Draft uses an unsupported source catalogue version.")
        valid.append(row)
    if not valid:
        return {"results": [], "all_current": True, "reviewed_for_regulatory_applicability": False}
    conn = connect(path)
    try:
        keys = [x["entry_key"] for x in valid]
        query = ("SELECT e.entry_key,e.structurecode,e.sds_section,e.catalogue_version,"
                 "e.collection,e.english,i.wording_hash FROM entries e "
                 "JOIN catalogue_index i ON i.entry_key=e.entry_key "
                 "WHERE e.entry_key IN (" + ",".join("?" for _ in keys) + ")")
        found = {row["entry_key"]:dict(row) for row in conn.execute(query, keys)}
    finally:
        conn.close()
    findings = []
    for record in valid:
        actual = found.get(record["entry_key"])
        current = bool(actual and
            actual["collection"] == "Core" and
            actual["catalogue_version"] == record["catalogue_version"] and
            actual["structurecode"] == record["structurecode"] and
            actual["sds_section"] == record["sds_section"] and
            actual["wording_hash"] == record["wording_hash"] and
            actual["english"] is not None and
            hashlib.sha256(actual["english"].encode("utf-8")).hexdigest() ==
            record["text_sha256"])
        findings.append({"entry_key":record["entry_key"],
                         "status":"source_unchanged" if current else "source_changed_or_missing"})
    return {"results": findings, "all_current":all(x["status"]=="source_unchanged" for x in findings),
            "reviewed_for_regulatory_applicability": False,
            "notice":"Matching source hashes only confirms unchanged local text, never legally suitable wording."}
