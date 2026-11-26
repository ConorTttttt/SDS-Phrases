"""Generate both roles from shared offline records and pinned SDS_Author revisions."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from exchange import ROOT, INTAKE, OUTPUT, read

HERE = Path(__file__).resolve().parent
REG = ROOT/"regulatory"
PINS = {"writer": "2c6cc785f218b0a1fb6f3f24260cc9b75026be8d",
        "reviewer": "ba0014655372a56c855b46b85fb6fd0f002d09c0"}
CITE = """Cite source ID, authority, edition, article/annex/clause, table, row and footnote when applicable, and PDF page. Link the registered original filename under sources/ with #page=N. Distinguish printed page and PDF ordinal. Verify table alignment, qualifiers, exceptions, effective dates and transition rules visually against the original. Check amendments applicable to the market date. Use guidance as interpretation and REF-11 as inspection practice. If the pinpoint or currentness cannot be verified, mark source verification pending."""
GAPS = """Distinguish unavailable, withheld, incomplete extraction, conflicting evidence and evidenced non-applicability. Record the affected ID, missing item, reason, source requested, and dependent conclusions. Request the original page or dated primary product record. An omitted export field or empty search result proves neither absence nor compliance. Never invent facts, thresholds, wording, identifiers or citations."""
COMMON = """Use WORKFLOWS for all twelve commands. Apply the role-specific instructions below within the selected workflow. Never claim to have run attached code. Label your reasoning model interpretation. Identify imported deterministic outputs by engine, input identity and version when supplied. A model inference cannot become a measured value or engine output. No autonomous certification or automatic correction. For JSON exchange return only the assessment schema, echo trusted header fields exactly, and reference the actual offline finding IDs and exported evidence IDs. Human review is required."""
EXTRA = [
 ("CLP_REVIEW","Two concentration units differ and the density is unknown.","Request unit-compatible evidence. Withhold threshold conclusion."),
 ("CLP_REVIEW","A harmonised entry is supplied without its notes or the component identifier.","Request identity and complete entry including notes before applying it."),
 ("LABEL_REVIEW","Label image is clipped at the pictograms.","Record incomplete extraction and request the full label."),
 ("SECTION9_CHECK","A supplier reports a flash point with no units or method.","Quote the supplied value, request units and method, withhold numerical interpretation."),
 ("GAP_ANALYSIS","An export omits formulation fields at the supplier’s request.","Record withheld evidence and unresolved dependencies."),
 ("CROSS_SECTION_REVIEW","Two otherwise identical product names carry different revision hashes.","Keep the evidence sets distinct and request revision reconciliation.")
]


def write(folder, name, value):
    p = folder/name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=False),encoding="utf-8")


def upstream(repo, ref, path):
    return subprocess.check_output(["git","-C",str(repo),"show",ref+":"+path]).decode("utf-8")


def files(repo, ref, prefix):
    return subprocess.check_output(["git","-C",str(repo),"ls-tree","-r","--name-only",ref,prefix]).decode("utf-8").splitlines()


def evaluations(refs):
    cases = []
    for name in ("TEST_CASES","REF11_TEST_CASES","REACH_TEST_CASES"):
        for line in refs[name].splitlines():
            row = re.fullmatch(r"\| ([A-Z]\d+) \| (.*?) \| (.*?) \| (.*?) \|",line)
            if row:
                key,prompt,clause,expected = row.groups()
            else:
                row = re.fullmatch(r"(R?\d+)\. (.+)",line)
                if not row:
                    continue
                key,spec = row.groups()
                key = key if key.startswith("R") else "W"+key.zfill(2)
                parts = re.split(r"; |: |, (?=never |do not |flag |request |return )",spec,maxsplit=1)
                prompt = parts[0] if len(parts)>1 else "Evaluate this scenario: "+spec
                if key == "R37":
                    prompt = "A confirmed Section 8 defect is reported. Assign a priority and explain its basis."
                expected = spec
                clause = ""
            cases.append(dict(id=key,prompt=prompt,expected=expected,clause=clause,source=name))
    if len({x["id"] for x in cases}) != 128 or len(cases)!=128:
        raise ValueError("Upstream evaluation inventory changed")
    return cases+[dict(id=f"X{i:02}",prompt=cmd+" "+q,expected=a,source="extension") for i,(cmd,q,a) in enumerate(EXTRA,1)]


def build(repo, sources, dest):
    if not shutil.which("git"):
        raise ValueError("Role generation requires Git on PATH and the pinned SDS_Author checkout")
    if not shutil.which("pdftotext"):
        raise ValueError("Role generation requires Poppler pdftotext on PATH")
    manifest = read(REG/"source_manifest.json")
    common = dest/"shared"
    common.mkdir()
    refs = {}
    pin = PINS["reviewer"]
    for path in files(repo,pin,"references"):
        name = Path(path).stem
        canonical = REG/"author"/path
        content = canonical.read_text(encoding="utf-8") if canonical.exists() else upstream(repo,pin,path)
        refs[name] = content
        if "TEST_CASES" not in name:
            write(common,Path(path).name,content)
    import sys
    sys.path.insert(0, str(ROOT/"src"))
    from canonical_requirements import load as load_canonical, requirement_version, coverage
    pack, raw, _ = load_canonical(ROOT)
    records = pack["requirements"]
    write(common,"canonical-requirements.json",pack)
    write(common,"canonical-coverage.json",coverage(pack,raw))
    sections = re.split(r"(?m)(?=^## Section \d+ —)",refs["ECHA_SECTION_PLAYBOOK"])
    index = []
    for n in range(17):
        body = [f"# REACH Annex II Part A — section {n}",sections[n] if n else sections[0]]
        body.append("Canonical decomposition incomplete; source extracts are not independently verified requirements.")
        for r in records:
            if r["clause"].split()[-1].split(".")[0] != str(n):
                continue
            page = r["pdf_pages"][0]
            anchor = f"[{r['clause']}, PDF p. {page}](sources/{manifest['sources'][0]['package_filename']}#page={page})"
            body.append(f"### {r['id']} · {anchor}\n\n{r['wording']}\n\nApplicability: {r['applicability_conditions']}\n\nEvidence: {r['required_product_evidence']}\n\nVersion: {requirement_version(r)}; {r['verification_status']}")
            index.append(f"{r['id']} | {r['clause']} | Section-{n:02}.md | PDF {r['pdf_pages']}")
        write(common,f"Section-{n:02}.md","\n\n".join(body))
    for line in refs["REACH_RULE_INDEX"].splitlines():
        r=json.loads(line)
        index.append(f"{r['id']} | {r['legal_clause']} | {r['topic']} | {r['pdf_pages']}")
    for q in read(REG/"assessment/ref11.json"):
        index.append(f"REF11/{q[0]} | {q[1]} | {q[3]} | printed p. {q[4]}")
    for code,r in read(REG/"assessment/clp_english.json").items():
        index.append(f"wording/{code} | CLP Annex III | {r['wording']} | PDF {r['page']}")
    write(common,"REQUIREMENTS.md","# Requirement lookup\n\n"+"\n\n".join(index))
    write(common,"SOURCE_CITATION.md",CITE)
    write(common,"MISSING_INFORMATION.md",GAPS)
    write(common,"WORKFLOWS.md",(HERE/"WORKFLOWS.md").read_text(encoding="utf-8"))
    for name in ("source_manifest.json","coverage.json"):
        shutil.copy(REG/name,common/name)
    write(common,"product-intake.schema.json",INTAKE)
    write(common,"assessment-output.schema.json",OUTPUT)
    cases=evaluations(refs)
    write(common,"evaluation.json",cases)
    # Full page runs retain continuations and footnotes. Use neighbouring chunks at boundaries.
    for s in manifest["sources"]:
        path=sources/s["filename"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=s["sha256"]:
            raise ValueError("Changed source: "+s["id"])
        (common/"sources").mkdir(exist_ok=True)
        shutil.copyfile(path,common/"sources"/s["package_filename"])
        pages=subprocess.check_output(["pdftotext","-layout",str(path),"-"]).decode("utf-8").split("\f")
        if pages[-1].strip() or len(pages)-1!=s["pages"]:
            raise ValueError("Unexpected page boundaries "+s["id"])
        for start in range(0,s["pages"],12):
            body=[]
            for page,txt in enumerate(pages[start:min(start+12,s["pages"])],start+1):
                body.append(f"## {s['id']} {s['version']} · [PDF {page}](../sources/{s['package_filename']}#page={page})\n\n```text\n{txt}\n```")
            write(common,f"pages/{s['id']}-{start+1:04}.md","\n\n".join(body))
    for role,ref in PINS.items():
        folder=dest/("eu-sds-"+role)
        shutil.copytree(common,folder)
        prefix="packages/eu-sds-"+role
        for path in files(repo,ref,prefix+"/references"):
            write(folder,Path(path).name,upstream(repo,ref,path))
        for path in files(repo,ref,prefix+"/templates"):
            write(folder,"templates/"+Path(path).name,upstream(repo,ref,path))
        role_text = (
            "You are the EU SDS Writer. Use every command as an authoring or readiness workflow. "
            "Write factual fields only from verified dated evidence for this product. Use only exact, "
            "approved phrase records for discretionary prose. Check ID, revision, language, scope, "
            "exclusions and approved substitutions. Preserve unresolved wording gaps. Mark drafts for competent-person review."
            if role == "writer" else
            "You are the EU SDS Compliance Reviewer. Assess the original independently. For each requirement "
            "evaluate applicability, presence, completeness, regulatory adequacy, scientific plausibility, "
            "internal consistency and expert judgement. Separate observed evidence from interpretation. "
            "Give a testable corrective action. For authoring commands review a proposed change."
        )
        instruction="\n\n".join((role_text, COMMON, GAPS, CITE, (common/"WORKFLOWS.md").read_text(encoding="utf-8")))
        write(folder,"GEM_INSTRUCTIONS.md",instruction)
        write(folder,"SKILL.md",f"---\nname: eu-sds-{role}\ndescription: Evidence-led EU SDS {role}\n---\n\n"+instruction)
        single=[instruction]
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in (".json",".md",".jsonl") and path.name not in ("evaluation.json","GEM_INSTRUCTIONS.md"):
                single.append("# "+path.name+"\n\n"+path.read_text(encoding="utf-8"))
        write(folder,"SINGLE_FILE_LLM_KNOWLEDGE_BASE.md","\n\n".join(single))
        shutil.copy(HERE/"evaluate.py", folder/"evaluate.py")
        shutil.copy(HERE/"README.md",folder/"INSTALL.md")
        shutil.make_archive(str(folder),"zip",folder)
    shutil.rmtree(common)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("author","sources","out"):
        p.add_argument("--"+arg,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():
        p.error("Choose a new output directory")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=a.out.parent) as tmp:
        stage=Path(tmp)/"packages"
        stage.mkdir()
        build(a.author,a.sources,stage)
        stage.rename(a.out)
