"""Execute original JavaScript tests and write a commit-linked TAP summary."""
import argparse
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    args=parser.parse_args()
    command=["node","--test","modules/section9/tests/rules.test.mjs"]
    try:
        commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        dirty=bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip())
    except (OSError,subprocess.SubprocessError):
        commit=dirty=None
    record=dict(schema="sds-validation/v1",suite="original_EU_SDS_JS",environment={"platform":platform.platform()},
                command=command,commit=commit,dirty=dirty,passed=None,failed=None,skipped=None,
                execution_limitations=[],status="not_run")
    rc=1
    try:
        if not shutil.which("node"):
            raise FileNotFoundError("Node.js 22+ not installed on PATH")
        record["environment"]["node"]=subprocess.check_output(["node","--version"],text=True).strip()
        run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120)
        print(run.stdout,end="")
        print(run.stderr,end="")
        record["returncode"]=run.returncode
        record["status"]="executed"
        for field,tag in (("passed","pass"),("failed","fail"),("skipped","skipped"),("cancelled","cancelled"),("todo","todo")):
            match=re.search(r"(?m)^# "+tag+r" (\d+)\s*$",run.stdout)
            record[field]=int(match.group(1)) if match else None
        if record["passed"] is None or record["failed"] is None or record["skipped"] is None:
            record["execution_limitations"].append("TAP summary unavailable; counts unknown")
        else:
            rc=int(run.returncode!=0 or record["passed"]==0 or record["failed"]!=0)
    except (OSError,subprocess.SubprocessError) as exc:
        record["execution_limitations"].append(str(exc))
    args.manifest.parent.mkdir(parents=True,exist_ok=True)
    args.manifest.write_text(json.dumps(record,indent=2),encoding="utf-8")
    return rc

if __name__=="__main__":
    raise SystemExit(main())
