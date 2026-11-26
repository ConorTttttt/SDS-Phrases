"""Local authoring endpoints. All writes require loopback and a custom header."""
import base64
import json
from pathlib import Path
from urllib.parse import urlparse
from sds_authoring import PhraseApprovals, Workspace, evaluate, export_draft, headings, DOMAINS
from catalogue_browser import search

def dispatch(handler,catalogue):
    if handler.client_address[0] not in ("127.0.0.1","::1") or handler.server.server_address[0] not in ("127.0.0.1","::1"):
        return handler.json_reply(403,{"error":"Local workspace only"})
    if handler.headers.get("X-SDS-Local-Review")!="1" or not handler.headers.get("Content-Type","").startswith("application/json"):
        return handler.json_reply(403,{"error":"Local JSON request required"})
    try:
        n=int(handler.headers.get("Content-Length","0"))
        if not 0<n<=2000000:
            return handler.json_reply(413,{"error":"Invalid request size"})
        p=json.loads(handler.rfile.read(n))
        directory=Path(catalogue).resolve().parent
        a=PhraseApprovals(directory/"phrase_approvals.sqlite",catalogue)
        w=Workspace(directory/"authoring_workspace.sqlite",a)
        action=urlparse(handler.path).path.rsplit("/",1)[-1]
        if action=="schema":
            result={"headings":headings(),"domains":DOMAINS}
        elif action=="evaluate":
            result=evaluate(p["dossier"],a)
        elif action=="approve-phrase":
            result=a.save(p["phrase"])
        elif action=="phrases":
            result=a.latest()
        elif action=="catalogue":
            result=search(catalogue,query=p.get("query",""),section=p.get("section",""),limit=40)
        elif action=="save":
            result=w.save(p["case_id"],p["dossier"],p.get("expected_version",0),p.get("reviews"))
        elif action=="history":
            result=w.history(p["case_id"])
        elif action=="compare":
            result={"diff":w.compare(p["case_id"],p["left"],p["right"])}
        elif action=="export":
            history=w.history(p["case_id"])
            record=next((r for r in history if r["version"]==p["version"]),None)
            if record is None:
                raise ValueError("Unknown revision")
            result={"format":p["format"],"base64":base64.b64encode(export_draft(record,p["format"])).decode()}
        else:
            return handler.json_reply(404,{"error":"Unknown authoring action"})
        return handler.json_reply(200,result)
    except (ValueError,TypeError,KeyError,OSError,ImportError) as exc:
        return handler.json_reply(400,{"error":str(exc)})
