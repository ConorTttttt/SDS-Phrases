"""Build a local source-pinned manual Gemini reference folder. No data upload."""
import argparse
import json
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from package_sources import verify_sources, extract_pages
def build(source_dir, out, extract=False):
    source_dir, out = Path(source_dir), Path(out)
    if out.exists(): raise ValueError("Output must not already exist")
    if out.resolve().is_relative_to(ROOT): raise ValueError("Output must be outside repository")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sds-build-", dir=out.parent) as staging:
        target = Path(staging) / "package"
        _build(source_dir, target, extract)
        if out.exists(): raise ValueError("Output appeared during build")
        target.rename(out)

def _build(source_dir, out, extract=False):
    if extract and not shutil.which("pdftotext"):
        raise ValueError("Page extraction requires Poppler pdftotext on PATH; install poppler-utils or omit --extract")
    manifest=verify_sources(ROOT/"regulatory/source_manifest.json", source_dir)
    out.mkdir(parents=True)
    shutil.copytree(ROOT/"regulatory/author",out/"author")
    shutil.copytree(ROOT/"regulatory/canonical",out/"canonical")
    (out/"sources").mkdir()
    for s in manifest["sources"]:
        shutil.copy2(source_dir/s["filename"],out/"sources"/s["package_filename"])
    # Retain the original author package relative source paths.
    (out/"author/sources").mkdir()
    for s in manifest["sources"]:
        if s["id"] in {"reach", "echa", "ref11"}:
            shutil.copy2(out/"sources"/s["package_filename"], out/"author/sources"/s["package_filename"])
    for name in ["source_manifest.json","coverage.json","upstream.json"]:
        shutil.copy2(ROOT/"regulatory"/name,out/name)
    (out/"shared_rules").mkdir()
    for name in ["eu_reach_annex2_partb_2026.json","eu_reach_annex2_content_inventory_draft.json","eu_sds_guidance_readiness_pilot.json"]:
        shutil.copy2(ROOT/"rules"/name,out/"shared_rules"/name)
    shutil.copy2(ROOT/"modules/section9/rules.mjs",out/"shared_rules"/"section9-reference.mjs")
    shutil.copy2(ROOT/"gemini/GEMINI_SYSTEM_PROMPT.md",out/"GEMINI_SYSTEM_PROMPT.md")
    text=(out/"GEMINI_SYSTEM_PROMPT.md").read_text(encoding="utf-8")
    text+="\n\n# Coverage\n"+(out/"coverage.json").read_text(encoding="utf-8")
    for r in sorted((out/"author/references").glob("*.md")):
        text+="\n\n# Reference: "+r.name+"\n"+r.read_text(encoding="utf-8")
    (out/"SINGLE_FILE_LLM_KNOWLEDGE_BASE.md").write_text(text,encoding="utf-8")
    subprocess.run([sys.executable, "-X", "utf8", str(out/"author/tests/check_package.py")], check=True)
    if extract:
        with (out/"page_chunks.jsonl").open("w",encoding="utf-8") as f:
            for s in manifest["sources"]:
                pages=extract_pages(out/"sources"/s["package_filename"],s["pages"])
                for i,page in enumerate(pages,1):
                    f.write(json.dumps({"source_id":s["id"],"pdf_page":i,"authority":s["authority"],"text":page,"extraction_status":"unverified_layout"},ensure_ascii=False)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--extract",action="store_true",help="Optional local Poppler page index; not verified table extraction")
    a=p.parse_args()
    build(a.sources,a.out,a.extract)
