"""Offline HTTP server for SDS phrase drafting, stdlib only."""
from __future__ import annotations
import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from engine import SelectionError, JURISDICTION_PREFIX, evaluate

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
RULES = ROOT / "rules" / "pilot-eu-gb-v1.json"
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}

def load_rules():
    return json.loads(RULES.read_text(encoding="utf-8"))

def search_catalogue(db_path, query="", jurisdiction="EU", section="", collection="Core", limit=40):
    if not Path(db_path).is_file():
        raise FileNotFoundError("Catalogue not installed.")
    if jurisdiction not in (*JURISDICTION_PREFIX, "ALL"):
        raise SelectionError("Invalid jurisdiction filter.")
    if collection not in ("Core", "ExpoScenario", "ALL"):
        raise SelectionError("Invalid collection filter.")
    limit = max(1, min(int(limit), 100))
    where, args = ["english IS NOT NULL", "english<>''"], []
    if jurisdiction != "ALL":
        where.append("jurisdiction_structure=?")
        args.append(jurisdiction)
    if collection != "ALL":
        where.append("collection=?")
        args.append(collection)
    if section:
        if not section.isdigit() or not 1 <= int(section) <= 16:
            raise SelectionError("Invalid SDS section filter.")
        where.append("sds_section=?")
        args.append(int(section))
    if query.strip():
        esc = query.strip()[:160].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("(LOWER(english) LIKE ? ESCAPE '\\' OR LOWER(original_code) LIKE ? ESCAPE '\\' OR LOWER(structurecode) LIKE ? ESCAPE '\\')")
        args.extend(["%" + esc + "%"] * 3)
    sql = """SELECT entry_key, collection, structurecode, esdscom_phrase_id, original_code,
                    english, sds_section, region, jurisdiction_structure, source,
                    phrase_owner, grammar, revision_date_raw
             FROM entries WHERE """ + " AND ".join(where) + " ORDER BY excel_row LIMIT ?"
    args.append(limit)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(x) for x in conn.execute(sql, args).fetchall()]
    return {"results": rows, "limit": limit}

def create_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def json_reply(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.startswith("/api/"):
                try:
                    if url.path == "/api/info":
                        rules = load_rules()
                        info = {"catalogue_installed": Path(db_path).is_file(),
                                "ruleset": rules["id"], "review_status": rules["review_status"],
                                "supported_jurisdictions": list(JURISDICTION_PREFIX),
                                "phrase_catalogue_version": "5.5"}
                        if info["catalogue_installed"]:
                            with sqlite3.connect(str(db_path)) as conn:
                                info["entries"] = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                                info["english_entries"] = conn.execute("SELECT COUNT(*) FROM entries WHERE english<>''").fetchone()[0]
                        return self.json_reply(200, info)
                    if url.path == "/api/rules":
                        return self.json_reply(200, load_rules())
                    if url.path == "/api/search":
                        args = parse_qs(url.query, keep_blank_values=True)
                        one = lambda key, default: args.get(key, [default])[0]
                        return self.json_reply(200, search_catalogue(
                            db_path, one("query", ""), one("jurisdiction", "EU"),
                            one("section", ""), one("collection", "Core"), one("limit", "40")))
                    return self.json_reply(404, {"error": "Unknown API endpoint."})
                except SelectionError as exc:
                    return self.json_reply(400, {"error": str(exc)})
                except (FileNotFoundError, sqlite3.Error) as exc:
                    return self.json_reply(503, {"error": "Catalogue unavailable: " + str(exc)})
                except (TypeError, ValueError) as exc:
                    return self.json_reply(400, {"error": str(exc)})
            filename = STATIC.get(url.path)
            if not filename:
                return self.send_error(404)
            filepath = WEB / filename
            try:
                data = filepath.read_bytes()
            except FileNotFoundError:
                return self.send_error(404)
            mime = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[filename.rsplit(".", 1)[1]]
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if urlparse(self.path).path != "/api/evaluate":
                return self.json_reply(404, {"error": "Unknown API endpoint."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100000:
                    return self.json_reply(413, {"error": "Invalid request size."})
                payload = json.loads(self.rfile.read(length))
                result = evaluate(db_path, load_rules(), payload)
                return self.json_reply(200, result)
            except (SelectionError, ValueError, TypeError, json.JSONDecodeError) as exc:
                return self.json_reply(400, {"error": str(exc)})
            except (FileNotFoundError, sqlite3.Error) as exc:
                return self.json_reply(503, {"error": "Catalogue unavailable: " + str(exc)})
    return Handler

def main():
    parser = argparse.ArgumentParser(description="SDS phrase drafting engine; local offline service")
    parser.add_argument("--db", default=str(ROOT / "data" / "catalogue.sqlite"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), create_handler(Path(args.db)))
    print(f"SDS Phrase Engine: http://{args.host}:{args.port}/")
    print("Draft suggestions only. No authentication; avoid exposing on public networks.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == "__main__":
    main()
