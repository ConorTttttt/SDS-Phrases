"""Verify the original ECHA SDS Guidance v4 PDF and Markdown source page anchors.

Requires poppler-utils (pdftotext). No original source text is committed to
Git, and this audit does NOT certify full transcription fidelity, legal
applicability, or correctness of any table/equation/footnote.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
import subprocess
import zipfile
from pathlib import Path

SHA256="2a4ac00f87544ebc6397e208e13da331a5ebabd6c5ceb5f149e84cb138501c28"
REFERENCE="ECHA-20-H-25-EN"
PAGES=137
SECTION_MEMBER="SDS_Section_{:02d}.md"
SECTION_START={1:33,2:41,3:46,4:57,5:59,6:61,7:63,8:68,9:77,10:93,11:97,12:103,13:109,14:111,15:115,16:118}
MARKER=re.compile(r"\*\*ECHA printed page (\d+)\*\*")
MEMBER=re.compile(r"(?:^|/)SDS_Section_(\d{2})\.md$")


class OriginalPDFError(ValueError):
    pass


def _check(condition,message):
    if not condition:
        raise OriginalPDFError(message)


def _text_pages(pdf):
    try:
        proc=subprocess.run(["pdftotext","-layout","-enc","UTF-8",str(pdf),"-"],
                            capture_output=True,text=True,check=False,timeout=60)
    except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
        raise OriginalPDFError("pdftotext unavailable/timeout; install poppler-utils") from exc
    _check(proc.returncode==0,"Could not extract text from original guidance PDF")
    pages=proc.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    _check(len(pages)==PAGES,f"Expected 137 pages, got {len(pages)}")
    _check("Guidance on the" in pages[0] and "Version 4.0" in pages[0],
           "Wrong ECHA guidance edition")
    _check(REFERENCE in pages[1],"Unexpected ECHA guidance source reference")
    return pages


def _page_anchor_audit(pages, archive):
    with zipfile.ZipFile(archive) as z:
        matching={}
        for member in z.namelist():
            match=MEMBER.search(member)
            if match:
                sec=int(match.group(1))
                _check(sec not in matching,"Duplicate SDS section source files")
                matching[sec]=member
        _check(set(matching)==set(range(1,17)),
               "Expected exactly 16 SDS_Section Markdown files in the source ZIP")
        checked=[]
        for sec in range(1,17):
            text=z.read(matching[sec]).decode("utf-8-sig")
            _check(f'document_id: "echa-sds-guidance-v4-2020-s{sec}"' in text,
                   f"Wrong document ID in section {sec}")
            _check(f'source_reference: "{REFERENCE}"' in text,
                   f"Wrong reference in section {sec}")
            _check(f'source_sha256: "{SHA256}"' in text,
                   f"Section {sec} declares a different original PDF")
            _check('NOT authoritative legislation' in text,
                   f"Section {sec} lost its non-binding status")
            page_numbers=[int(num) for num in MARKER.findall(text)]
            _check(page_numbers and page_numbers==sorted(set(page_numbers)),
                   f"Missing/duplicate/out-of-order source page references in section {sec}")
            _check(all(1<=num<=PAGES for num in page_numbers),
                   f"Section {sec} has out-of-range PDF page references")
            start=SECTION_START[sec]
            _check(page_numbers[0]==start,
                   f"Section {sec} starts on the wrong source page")
            for page in page_numbers:
                header=" ".join(pages[page-1].split()[:25])
                _check(bool(re.search(r"\b"+str(page)+r"\b",header)),
                       f"Printed page {page} could not be matched to PDF page {page}")
            chapter=f"3.{sec} SDS SECTION {sec}".casefold()
            first_text=" ".join(pages[start-1].split()).casefold()
            _check(chapter in first_text,
                   f"ECHA chapter {sec} heading missing from original PDF page {start}")
            checked.append({"section":sec,"chapter":f"3.{sec}","printed_start_page":start,
                            "page_refs":len(page_numbers),"last_page":page_numbers[-1],
                            "chapter_first_page_matched":True})
        return checked


def verify_original(pdf_path, archive_path=None, db_path=None):
    pdf=Path(pdf_path)
    _check(pdf.is_file(),"Original ECHA PDF not found")
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    _check(digest==SHA256,"Original ECHA PDF SHA-256 mismatch; expected v4.0 reference PDF")
    pages=_text_pages(pdf)
    chapters=[]
    if archive_path is not None:
        archive=Path(archive_path)
        _check(archive.is_file() and zipfile.is_zipfile(archive),
               "Expected original Markdown extraction ZIP")
        chapters=_page_anchor_audit(pages,archive)
    result={
        "guidance_reference":REFERENCE,"version":"4.0 (December 2020)",
        "sha256":digest,"pdf_pages":len(pages),
        "pdf_sha256_verified":True,
        "source_zip_16_chapter_anchors_verified":len(chapters)==16,
        "chapters":chapters,
        "original_text_full_fidelity_verified":False,
        "tables_figures_footnotes_verified":False,
        "legal_rules_verified":False,
        "source_class":"historical_nonbinding_echa_guidance",
        "warning":"Verifies original file fingerprint, PDF page count, chapter entry points and source-page markers only. Requires independent passage/table audit; ECHA guidance is not primary legislation."
    }
    if db_path is not None:
        _check(len(chapters)==16,"Database update requires verified ZIP/page crosscheck")
        db=Path(db_path)
        _check(db.is_file(),"Imported guidance.sqlite missing. Import Markdown ZIP first.")
        with closing(sqlite3.connect(db)) as conn, conn:
            expected=dict(conn.execute("SELECT name,value FROM guidance_metadata"))
            _check(expected.get("declared_original_pdf_sha256")==digest,
                   "Local guidance index declares a different original PDF")
            vals={
                "original_pdf_sha256_verified":"yes",
                "original_pdf_page_count":str(PAGES),
                "source_zip_chapter_anchors_verified":"yes",
                "original_pdf_external_verified":"yes",
                "full_markdown_text_fidelity_verified":"no",
                "tables_figures_footnotes_verified":"no",
                "source_text_regulatory_verification":"not_performed",
                "legally_binding":"no",
            }
            conn.executemany("INSERT OR REPLACE INTO guidance_metadata(name,value) VALUES (?,?)",vals.items())
            result["local_guidance_metadata_updated"]=True
    return result


def main():
    ap=argparse.ArgumentParser(description="Check original ECHA guidance PDF against Markdown source archive")
    ap.add_argument("pdf",help="Original 137-page ECHA guidance v4.0 PDF")
    ap.add_argument("--archive",help="Optional CLP_A_I-main.zip to cross-check all 16 sections")
    ap.add_argument("--db",help="Optional existing data/echa_guidance_2020.sqlite (requires --archive)")
    args=ap.parse_args()
    try:
        print(json.dumps(verify_original(args.pdf,args.archive,args.db),indent=2))
    except (OriginalPDFError,zipfile.BadZipFile,sqlite3.Error,UnicodeError) as exc:
        ap.error(str(exc))


if __name__=="__main__":
    main()
