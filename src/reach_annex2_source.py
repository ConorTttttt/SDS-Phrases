"""Local, non-destructive REACH Annex II PDF source index.

Input is the pinned complete PDF or the legacy 36-page excerpt of the
2026-06-22 EU consolidated text. Extraction artefacts may retain stale headers.
Do not treat the consolidated document as the authentic Official Journal act.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing
import subprocess
import tempfile
from pathlib import Path

SOURCE_SHA256="3e6304eb92c7ffb0b82fc7d634ac825f0bc8849195c81ac5d7efa4b16ead66fb"
FULL_SOURCE_SHA256="04e3d65150eeed337e09f2a6d4a6cb6dae47a0bda488bebcef44972092147572"
CELEX="02006R1907-20260622"
OFFICIAL="https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX%3A"+CELEX

class ReachSourceError(ValueError):
    pass

def _pages(text):
    pages=text.split("\f")
    if pages and pages[-1].strip()=="":
        pages.pop()
    if len(pages)!=36:
        raise ReachSourceError(f"Expected exactly 36 Annex II pages; got {len(pages)}")
    if "ANNEX II" not in pages[0] or "PART A" not in pages[0]:
        raise ReachSourceError("Expected Annex II Part A on first PDF page")
    if "PART B" not in pages[33] or "SECTION 16:" not in pages[35]:
        raise ReachSourceError("Expected Annex II Part B on pages 34–36")
    if "Table 1.1" not in pages[7]:
        raise ReachSourceError("Expected the ingredient-disclosure Table 1.1 on PDF page 8")
    return pages

def import_pdf(path, db):
    path,db=Path(path),Path(db)
    if not path.is_file():raise FileNotFoundError(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest not in (SOURCE_SHA256,FULL_SOURCE_SHA256):
        raise ReachSourceError("PDF fingerprint does not match either pinned REACH source (complete or excerpt).")
    page_args=["-f","117","-l","152"] if digest==FULL_SOURCE_SHA256 else []
    if not shutil.which("pdftotext"):
        raise ReachSourceError("Missing pdftotext. On Ubuntu: sudo apt install poppler-utils")
    result=subprocess.run(["pdftotext",*page_args,"-layout","-enc","UTF-8",str(path),"-"],
                          capture_output=True,text=True,timeout=45,check=False)
    if result.returncode!=0:
        raise ReachSourceError("PDF text extraction failed: "+result.stderr[-400:])
    pages=_pages(result.stdout)
    prior_headers=sum("11.05.2026" in x and "068.001" in x for x in pages)
    current_headers=sum("22.06.2026" in x and "069.001" in x for x in pages)
    # Preserve raw pages exactly as extracted, including superseded overlaid
    # header layers; do not infer a legal effective date from any PDF header.
    db.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=db.parent) as folder:
        tmp=Path(folder)/"reach.sqlite"
        with closing(sqlite3.connect(tmp)) as conn, conn:
            conn.execute("""CREATE TABLE reference_pages(
                pdf_page INTEGER PRIMARY KEY, printed_page INTEGER NOT NULL,
                text TEXT NOT NULL, text_sha256 TEXT NOT NULL
            )""")
            conn.executemany("INSERT INTO reference_pages VALUES (?,?,?,?)",[
              (i+1, i+117, body, hashlib.sha256(body.encode("utf-8")).hexdigest())
              for i,body in enumerate(pages)])
            conn.execute("CREATE TABLE source_metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL)")
            meta={
              "celex":CELEX,"consolidated_edition":"2026-06-22","official_reference_url":OFFICIAL,
              "source_sha256":digest,"pdf_pages":"36",
              "visible_edition":"069.001 / 22.06.2026",
              "extracted_old_header_pages":str(prior_headers),
              "extracted_new_header_pages":str(current_headers),
              "consolidated_text_is_authentic_oj":"no",
              "source_status":"document_index_only_not_rule_verification",
              "rendered_visual_sample_checked":"legacy excerpt sample only; complete PDF extraction not independently visually reviewed",
              "source_pdf_first_page":"117" if digest==FULL_SOURCE_SHA256 else "1",
              "warning":"PDF has layered old and new headers in text extraction. Use PDF page/printed page and EUR-Lex source, not raw header text."
            }
            conn.executemany("INSERT INTO source_metadata VALUES (?,?)",meta.items())
        tmp.replace(db)
    return {"pages":len(pages),"source_sha256":digest,
            "legacy_header_pages":prior_headers,"visible_current_header_pages":current_headers,
            "legally_verified_rules_created":0,
            "warning":"Source indexed, not legal rule-verified; extracted version headers conflict."}

def _connect(db):
    db=Path(db)
    if not db.is_file():raise FileNotFoundError("Import pinned Full REACH.pdf or legacy Full REACH_removed.pdf before searching this local reference")
    conn=sqlite3.connect(db)
    conn.row_factory=sqlite3.Row
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='source_metadata'").fetchone():
        conn.close()
        raise ReachSourceError("Not a REACH Annex II source database")
    return conn

def summary(db):
    with closing(_connect(db)) as conn:
        metadata=dict(conn.execute("SELECT name,value FROM source_metadata"))
        return {"metadata":metadata,"page_count":conn.execute("SELECT COUNT(*) FROM reference_pages").fetchone()[0],
            "warning":"Reference content only; no regulatory requirement has been legally verified by source ingestion."}

def search(db, *, query="", page="", limit=12, offset=0):
    if not isinstance(query,str) or len(query)>200:raise ReachSourceError("Invalid query")
    if page and (not isinstance(page,str) or not page.isdecimal() or not 1<=int(page)<=36):
        raise ReachSourceError("page must be 1–36")
    try:limit,offset=int(limit),int(offset)
    except (ValueError,TypeError):raise ReachSourceError("Invalid pagination") from None
    if not 1<=limit<=36 or not 0<=offset<=100000:raise ReachSourceError("Invalid pagination")
    clauses,params=[],[]
    if page:
        clauses.append("pdf_page=?");params.append(int(page))
    if query.strip():
        text=query.strip().lower().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        clauses.append("LOWER(text) LIKE ? ESCAPE '\\'");params.append("%"+text+"%")
    where=" WHERE "+" AND ".join(clauses) if clauses else ""
    with closing(_connect(db)) as conn:
        count=conn.execute("SELECT COUNT(*) FROM reference_pages"+where,params).fetchone()[0]
        rows=conn.execute("SELECT pdf_page,printed_page,text_sha256,text FROM reference_pages"+where+
                          " ORDER BY pdf_page LIMIT ? OFFSET ?",params+[limit,offset]).fetchall()
        return {"total":count,"results":[{
            "pdf_page":r["pdf_page"],"printed_page":r["printed_page"],
            "text_sha256":r["text_sha256"],
            "text_preview":r["text"][:2500],
            "source_celex":CELEX,
        } for r in rows],"limit":limit,"offset":offset,
        "notice":"PDF text may contain stale overlaid headers. Read rendered page for authoritative typography."}

def main():
    p=argparse.ArgumentParser(description="Index Annex II from the pinned full REACH PDF or legacy excerpt")
    p.add_argument("pdf");p.add_argument("--db",default="data/reach_annex2_2026.sqlite")
    args=p.parse_args()
    print(json.dumps(import_pdf(args.pdf,args.db),indent=2))

if __name__=="__main__":main()
