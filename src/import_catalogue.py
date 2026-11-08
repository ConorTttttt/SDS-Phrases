"""Import original eSDScom 5.5 source ZIP into a local SQLite phrase database.

No adapted phrase catalogue is committed to GitHub. Requires Python 3.10+.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import hashlib
from catalogue_index import build_index

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RAW_COLUMNS = [
    "esdscom_structure_id", "structurecode", "esdscom_path_full", "region",
    "structure_info", "esdscom_phrase_id", "grammar", "original_code",
    "english", "german", "revision_date_raw", "phrase_owner", "source",
    "info", "qualifier", "value", "unit",
]
PREFIXES = {"01": "EU", "02": "GB", "03": "UN", "04": "US", "05": "MX",
            "06": "AR", "07": "BR", "08": "CN"}
TABLE_FIELDS = [
    "entry_key", "catalogue_version", "collection", "source_file", "excel_row",
    "structurecode", "esdscom_structure_id", "esdscom_phrase_id",
    "esdscom_path_full", "region", "jurisdiction_structure", "sds_section",
    "structure_info", "grammar", "original_code", "english",
    "revision_date_raw", "phrase_owner", "source", "info", "qualifier", "value", "unit",
]


def workbook_rows(source):
    with zipfile.ZipFile(source) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings = ["".join(node.text or "" for node in item.iter(NS + "t"))
                       for item in root.findall(NS + "si")]
        with z.open("xl/worksheets/sheet1.xml") as stream:
            for _, node in ET.iterparse(stream, events=("end",)):
                if node.tag != NS + "row":
                    continue
                vals = {}
                for cell in node.findall(NS + "c"):
                    address = cell.get("r", "")
                    match = re.match(r"([A-Z]+)", address)
                    if not match:
                        continue
                    val = cell.find(NS + "v")
                    value = val.text if val is not None and val.text else ""
                    if cell.get("t") == "s" and value:
                        value = strings[int(value)]
                    elif cell.get("t") == "inlineStr":
                        inline = cell.find(NS + "is")
                        value = "".join(n.text or "" for n in inline.iter(NS + "t")) if inline is not None else ""
                    vals[match.group(1)] = value
                yield int(node.get("r", "0")), vals
                node.clear()


def source_workbooks(path):
    """Accept original ZIP or extracted directory. Yield collection, name, bytes."""
    if path.is_dir():
        for kind in ("Core", "ExpoScenario"):
            matches = sorted(path.glob("*" + kind + "*.xlsx"))
            if len(matches) != 1:
                raise ValueError("Expected one " + kind + " .xlsx in directory.")
            yield kind, matches[0].name, matches[0].read_bytes()
    else:
        with zipfile.ZipFile(path) as archive:
            for kind in ("Core", "ExpoScenario"):
                matches = [name for name in archive.namelist()
                           if name.lower().endswith(".xlsx") and kind.lower() in name.lower()]
                if len(matches) != 1:
                    raise ValueError("Expected one " + kind + " .xlsx in the ZIP.")
                yield kind, Path(matches[0]).name, archive.read(matches[0])


def import_catalogue(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Build a temporary database: never overwrite working data after a partial failure.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        tmp = Path(temporary) / "catalogue.sqlite"
        conn = sqlite3.connect(tmp)
        conn.execute("""CREATE TABLE entries (
            entry_key TEXT PRIMARY KEY, catalogue_version TEXT NOT NULL,
            collection TEXT NOT NULL, source_file TEXT NOT NULL, excel_row INTEGER NOT NULL,
            structurecode TEXT NOT NULL, esdscom_structure_id TEXT, esdscom_phrase_id TEXT,
            esdscom_path_full TEXT, region TEXT, jurisdiction_structure TEXT,
            sds_section INTEGER, structure_info TEXT, grammar TEXT, original_code TEXT,
            english TEXT, revision_date_raw TEXT, phrase_owner TEXT, source TEXT,
            info TEXT, qualifier TEXT, value TEXT, unit TEXT
        )""")
        conn.execute("CREATE INDEX idx_section_region ON entries (jurisdiction_structure, sds_section)")
        conn.execute("CREATE INDEX idx_structure ON entries (structurecode)")
        counts = collections.Counter()
        insert = "INSERT INTO entries (" + ",".join(TABLE_FIELDS) + ") VALUES (" + ",".join("?" for _ in TABLE_FIELDS) + ")"
        for kind, source_name, data in source_workbooks(source):
            from io import BytesIO
            iterator = workbook_rows(BytesIO(data))
            header_row, header = next(iterator)
            if header_row != 1 or header.get("I", "").lower() != "english":
                raise ValueError("Unexpected workbook columns; refusing to guess mappings for " + source_name)
            batch = []
            for excel_row, cells in iterator:
                raw = dict(zip(RAW_COLUMNS, (cells.get(c, "") for c in "ABCDEFGHIJKLMNOPQ")))
                code = raw["structurecode"]
                parts = code.split(".")
                prefix = parts[0] if parts else ""
                section = (int(parts[1]) if prefix in PREFIXES and
                           len(parts) > 1 and parts[1].isdigit() and
                           1 <= int(parts[1]) <= 16 else None)
                row = {
                    "entry_key": f"esdscom55-{kind}-r{excel_row:06d}",
                    "catalogue_version": "5.5", "collection": kind,
                    "source_file": source_name, "excel_row": excel_row,
                    "jurisdiction_structure": PREFIXES.get(prefix, ""),
                    "sds_section": section,
                }
                for k in TABLE_FIELDS:
                    if k in raw:
                        row[k] = raw[k]
                batch.append(tuple(row.get(k) for k in TABLE_FIELDS))
                counts[kind + "_rows"] += 1
                if raw["english"]:
                    counts["english_entries"] += 1
                else:
                    counts["blank_english"] += 1
                if len(batch) >= 1000:
                    conn.executemany(insert, batch)
                    batch = []
            if batch:
                conn.executemany(insert, batch)
        try:
            conn.execute("CREATE VIRTUAL TABLE entries_fts USING fts5(english, original_code, structurecode, content='entries', content_rowid='rowid')")
            conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
            counts["fts5"] = True
        except sqlite3.OperationalError:
            counts["fts5"] = False
        conn.commit()
        if source.is_file():
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
        else:
            sha = "directory_input_no_archive_digest"
        counts.update(build_index(conn, source_sha256=sha))
        counts["total_rows"] = sum(counts[k] for k in ("Core_rows", "ExpoScenario_rows"))
        conn.close()
        tmp.replace(destination)
    return dict(counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Original eSDScom 5.5 ZIP or directory of original XLSX files")
    parser.add_argument("--db", default="data/catalogue.sqlite")
    args = parser.parse_args()
    result = import_catalogue(args.source, args.db)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
