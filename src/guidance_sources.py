"""Local, read-only source index for ECHA SDS guidance v4.0 (Dec 2020).

This package imports historical, NON-BINDING guidance for evidence retrieval.
It cannot create regulatory obligations or approve SDS phrase wording.
Uses only Python's standard library; no upstream source text in GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

GUIDANCE_ID = "ECHA-SDS-2020-V4"
REFERENCE = "ECHA-20-H-25-EN"
STANDARD = "nonbinding_historical_guidance"
SECTION_RE = re.compile(r"(?:^|/)SDS_Section_(\d{2})\.md$")
ANCHOR_RE = re.compile(r'<a id="echa-sds-(\d{1,2})-(\d{1,2})"></a>')
HEADING_RE = re.compile(r"(?m)^#{2,5}\s+(\d{1,2})\.(\d{1,2})\.?\s+(.+?)\s*$")
PAGE_RE = re.compile(r"\*\*ECHA printed page (\d+)\*\*")
META_RE = re.compile(r'^([a-z0-9_]+):\s*"([^"\r\n]*)"\s*$', re.M)
MAX_UNCOMPRESSED = 6_000_000


class GuidanceError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise GuidanceError(message)


def _parse_text(text, number):
    front = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    _require(front is not None, f"Section {number}: YAML source front matter missing")
    metadata = dict(META_RE.findall(front.group(1)))
    _require(metadata.get("document_id") == f"echa-sds-guidance-v4-2020-s{number}",
             f"Section {number}: unexpected document identifier")
    _require(metadata.get("source_reference") == REFERENCE,
             f"Section {number}: wrong ECHA document reference")
    _require(metadata.get("source_version") == "4.0 — December 2020",
             f"Section {number}: unexpected ECHA guidance edition")
    _require("NOT authoritative legislation" in metadata.get("authority", ""),
             f"Section {number}: nonbinding status must be explicit")
    _require(bool(re.fullmatch(r"[a-f0-9]{64}", metadata.get("source_sha256", ""))),
             f"Section {number}: missing declared original PDF fingerprint")
    pages = [int(x) for x in PAGE_RE.findall(text)]
    _require(bool(pages) and len(pages) == len(set(pages)) and pages == sorted(pages),
             f"Section {number}: missing, duplicated or unordered page references")
    span = metadata.get("page_span", "")
    _require(bool(span) and str(pages[0]) in span and str(pages[-1]) in span,
             f"Section {number}: page span is inconsistent with source anchors")
    title = next((x[2:].strip() for x in text[front.end():].splitlines()
                  if x.startswith("# ")), f"SDS section {number}")
    return metadata, pages, title


def _passages(text, section):
    """Extract exact Markdown spans and source page labels; no rewriting or inference."""
    anchors = []
    for match in ANCHOR_RE.finditer(text):
        if int(match.group(1)) != section:
            continue
        next_heading = HEADING_RE.search(text, match.end(), min(len(text), match.end() + 260))
        if next_heading is None:
            continue
        n, sub, title = next_heading.groups()
        if int(n) != section or int(sub) != int(match.group(2)):
            continue
        if re.search(r"\bSDS\s+SECTION\b", title, re.I):
            # ECHA chapter 3.3 is NOT the SDS subsection 3.3.
            continue
        anchors.append((match.start(), f"{section}.{int(sub)}", title.strip()))
    cuts = anchors + [(len(text), "", "")]
    chunks = []
    beginning = text.find("**ECHA printed page ")
    if beginning < 0:
        beginning = 0
    if anchors:
        overview = text[beginning:anchors[0][0]].strip()
        if overview:
            page = PAGE_RE.findall(text[:anchors[0][0]])
            chunks.append((str(section), "Section overview", int(page[-1]) if page else 0, overview))
    else:
        chunks.append((str(section), "Section guidance", int(PAGE_RE.findall(text)[0]), text[beginning:].strip()))
    for idx, (start, key, title) in enumerate(anchors):
        end = cuts[idx + 1][0]
        snippet = text[start:end].strip()
        prior = PAGE_RE.findall(text[:start])
        first_page = int(prior[-1]) if prior else 0
        chunks.append((key, title, first_page, snippet))
    return chunks


def _source_members(archive):
    mapping = {}
    for member in archive.infolist():
        found = SECTION_RE.search(member.filename)
        if not found or member.is_dir():
            continue
        section = int(found.group(1))
        if not 1 <= section <= 16:
            continue
        # Prefer top-level section files; a nested separate ZIP is not extracted.
        _require(section not in mapping, f"Duplicate SDS Section {section:02d} file")
        _require(member.file_size <= 150_000, f"Section {section} exceeds file size guard")
        mapping[section] = member
    _require(set(mapping) == set(range(1, 17)), "Expected exactly SDS_Section_01.md through SDS_Section_16.md")
    return mapping


def import_guidance(source_archive, destination):
    source_archive, destination = Path(source_archive), Path(destination)
    _require(source_archive.is_file(), "Guidance ZIP not found")
    _require(zipfile.is_zipfile(source_archive), "Expected a ZIP archive")
    archive_digest = hashlib.sha256(source_archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(source_archive) as archive:
        mapping = _source_members(archive)
        sections = []
        passages = []
        pdf_ids = set()
        for section, item in sorted(mapping.items()):
            _require(item.file_size <= MAX_UNCOMPRESSED, "Extracted section exceeds size limit")
            raw = archive.read(item)
            text = raw.decode("utf-8-sig")
            meta, pages, title = _parse_text(text, section)
            pdf_ids.add(meta["source_sha256"])
            sections.append((section, title, meta["source_version"], meta["source_reference"],
                             meta["source_sha256"], meta["authority"], pages[0], pages[-1],
                             item.filename, hashlib.sha256(raw).hexdigest(), text))
            for key, heading, page, content in _passages(text, section):
                passages.append((key, section, heading, page, content))
        _require(len(pdf_ids) == 1, "Sections disagree about original ECHA PDF SHA-256")
        # No original ECHA PDF is included in this lightweight upload.
        pdf_present = any(x.filename.lower().endswith(".pdf") for x in archive.infolist())
        _require(sum(x.file_size for x in mapping.values()) <= MAX_UNCOMPRESSED,
                 "Guidance source material exceeds import size limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        tempdb = Path(work) / "guidance.sqlite"
        with closing(sqlite3.connect(tempdb)) as conn, conn:
            conn.executescript("""
                CREATE TABLE guidance_sections (
                    section INTEGER PRIMARY KEY,
                    title TEXT NOT NULL, source_version TEXT NOT NULL, reference TEXT NOT NULL,
                    declared_pdf_sha256 TEXT NOT NULL, authority TEXT NOT NULL,
                    page_first INTEGER NOT NULL, page_last INTEGER NOT NULL,
                    original_entry TEXT NOT NULL, content_sha256 TEXT NOT NULL,
                    markdown TEXT NOT NULL
                );
                CREATE TABLE guidance_passages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL,
                    section INTEGER NOT NULL, title TEXT NOT NULL, source_page INTEGER NOT NULL,
                    markdown TEXT NOT NULL,
                    FOREIGN KEY(section) REFERENCES guidance_sections(section)
                );
                CREATE INDEX guidance_by_section ON guidance_passages(section, source_key);
                CREATE TABLE guidance_metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            conn.executemany("INSERT INTO guidance_sections VALUES (?,?,?,?,?,?,?,?,?,?,?)", sections)
            conn.executemany("INSERT INTO guidance_passages(source_key,section,title,source_page,markdown) VALUES (?,?,?,?,?)", passages)
            entries = {
                "source_id": GUIDANCE_ID, "source_reference": REFERENCE,
                "source_type": STANDARD,
                "source_version": "4.0 — December 2020",
                "archive_sha256": archive_digest,
                "declared_original_pdf_sha256": next(iter(pdf_ids)),
                "original_pdf_in_package": "yes" if pdf_present else "no",
                "original_pdf_sha256_verified": "no",
                "legally_binding": "no",
                "current_legal_requirements_verified": "no",
                "source_text_regulatory_verification": "not_performed",
            }
            conn.executemany("INSERT INTO guidance_metadata VALUES (?,?)", entries.items())
        os.replace(tempdb, destination)
    return {
        "source_id": GUIDANCE_ID, "sections": len(sections),
        "passages": len(passages),
        "subsection_passages": sum(bool(re.fullmatch(r"\d{1,2}\.\d{1,2}", k)) for k, *_ in passages),
        "original_pdf_in_package": pdf_present,
        "current_legal_requirements_verified": False,
        "source_archive_sha256": archive_digest,
        "notice": "Imported only as historical nonbinding guidance. No legal requirements created."
    }


def _connect(db):
    db = Path(db)
    if not db.is_file():
        raise FileNotFoundError("Guidance database missing: import CLP_A_I-main.zip locally first")
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='guidance_metadata'").fetchone():
        conn.close()
        raise FileNotFoundError("File does not contain the ECHA guidance source index")
    return conn


def summary(db):
    with closing(_connect(db)) as conn:
        metadata = dict(conn.execute("SELECT name,value FROM guidance_metadata"))
        rows = [dict(row) for row in conn.execute(
            "SELECT section,title,page_first,page_last,source_version,reference FROM guidance_sections ORDER BY section")]
        return {"metadata": metadata, "sections": rows, "section_count": len(rows),
                "passage_count": conn.execute("SELECT COUNT(*) FROM guidance_passages").fetchone()[0],
                "warning": "ECHA 2020 guidance is secondary; verify against current REACH Annex II."}


def search(db, query="", section="", limit=30, offset=0):
    if not isinstance(query, str):
        raise GuidanceError("Search term must be text")
    query = query.strip()[:150]
    if section:
        if not isinstance(section, str) or not section.isdecimal() or not 1 <= int(section) <= 16:
            raise GuidanceError("Invalid SDS section")
    try:
        limit, offset = int(limit), int(offset)
    except (ValueError, TypeError):
        raise GuidanceError("Invalid pagination") from None
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
        raise GuidanceError("Invalid pagination range")
    conditions, params = [], []
    if section:
        conditions.append("section=?")
        params.append(int(section))
    if query:
        q = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("(LOWER(title) LIKE ? ESCAPE '\\' OR LOWER(markdown) LIKE ? ESCAPE '\\' OR LOWER(source_key) LIKE ? ESCAPE '\\')")
        params.extend(["%" + q + "%"] * 3)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with closing(_connect(db)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM guidance_passages" + where, params).fetchone()[0]
        rows = conn.execute("""SELECT source_key,section,title,source_page,markdown
            FROM guidance_passages""" + where + " ORDER BY section,id LIMIT ? OFFSET ?", params + [limit,offset])
        items = [{
            "source_key":row["source_key"],"section":row["section"],"title":row["title"],
            "source_page":row["source_page"],
            "text_preview":row["markdown"][:800],
            "reference":REFERENCE,
            "source_type":STANDARD,
            "legal_status":"not_legally_verified",
        } for row in rows]
        return {"total":count, "limit":limit,"offset":offset,"results":items,
                "warning":"Historical nonbinding guidance; not an SDS legal requirement."}


def main():
    p = argparse.ArgumentParser(description="Index ECHA 2020 SDS guidance ZIP locally as non-binding reference")
    p.add_argument("archive", help="Uploaded CLP_A_I-main.zip (16 SDS Section Markdown files)")
    p.add_argument("--db", default="data/echa_guidance_2020.sqlite")
    args = p.parse_args()
    print(json.dumps(import_guidance(args.archive,args.db),indent=2))


if __name__=="__main__":
    main()
