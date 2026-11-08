"""Local catalogue metadata notes. No regulatory approval is granted by a status."""
from __future__ import annotations
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

STATUSES=("unreviewed","metadata_checked","needs_attention")

class ReviewError(ValueError):
    pass

def lookup(path,records):
    """Attach notes to result records; a changed wording hash invalidates an old review."""
    for item in records:
        item["review_status"]="unreviewed"
        item["review_note"]=""
        item["review_stale"]=False
    if not records or not Path(path).exists():
        return records
    with closing(sqlite3.connect(path)) as conn, conn:
        keys=[item["entry_key"] for item in records]
        sql="SELECT entry_key,wording_hash,status,note FROM reviews WHERE entry_key IN ("+",".join("?" for _ in keys)+")"
        prior={x[0]:x for x in conn.execute(sql,keys)}
        for item in records:
            row=prior.get(item["entry_key"])
            if not row:continue
            if row[1]!=item["wording_hash"]:
                item["review_stale"]=True
                continue
            item["review_status"]=row[2]
            item["review_note"]=row[3]
    return records

def set_review(catalogue,path,*,entry_key,wording_hash,status,note=""):
    if status not in STATUSES:
        raise ReviewError("Unknown metadata review status.")
    if not isinstance(note,str) or len(note)>1000:
        raise ReviewError("Note must be at most 1,000 characters.")
    if not isinstance(entry_key,str) or not 1<=len(entry_key)<=100:
        raise ReviewError("Invalid catalogue entry key.")
    if not isinstance(wording_hash,str) or len(wording_hash)!=64:
        raise ReviewError("Missing wording fingerprint; reload the catalogue.")
    from catalogue_browser import connect
    conn=connect(catalogue)
    try:
        row=conn.execute("SELECT wording_hash FROM catalogue_index WHERE entry_key=?",(entry_key,)).fetchone()
    finally:
        conn.close()
    if not row or row[0]!=wording_hash:
        raise ReviewError("Phrase changed or entry not found. Reload before reviewing.")
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
            entry_key TEXT PRIMARY KEY,wording_hash TEXT NOT NULL,
            status TEXT NOT NULL,note TEXT NOT NULL,reviewed_at_utc TEXT NOT NULL
        )""")
        if status=="unreviewed":
            conn.execute("DELETE FROM reviews WHERE entry_key=?",(entry_key,))
        else:
            conn.execute("""INSERT INTO reviews VALUES (?,?,?,?,?)
                 ON CONFLICT(entry_key) DO UPDATE SET wording_hash=excluded.wording_hash,
                 status=excluded.status,note=excluded.note,reviewed_at_utc=excluded.reviewed_at_utc""",
                 (entry_key,wording_hash,status,note,datetime.now(timezone.utc).isoformat()))
    return {"entry_key":entry_key,"review_status":status,"review_note":note,
            "review_stale":False,"notice":"Catalogue metadata review only; not regulatory or SDS approval."}
