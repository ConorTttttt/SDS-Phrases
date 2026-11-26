# SDS-Phrases: offline EU SDS authoring and review toolkit

An offline, local-first toolkit that helps a competent person draft and review EU/EEA Safety Data Sheets.
It is grounded in EU REACH (Regulation (EC) No 1907/2006: Article 31, Title IV and Annex II) and EU CLP
(Regulation (EC) No 1272/2008). Everything runs with the Python standard library, SQLite and a local browser.
No AI API, cloud service or external database is required.

> **Draft-support tool, not a certified SDS generator.** Every regulatory record in this repository is a
> *candidate* assessment target pending independent legal and extraction review. Passing software tests
> is not legal or regulatory validation. Missing information never means "no hazard" or "compliant".
> A named competent person must verify every draft, finding and Gemini output before professional release.

## Branches

All toolkit work is integrated on **`integration/offline-eu-gemini`**. It combines the earlier feature
branches into one working application:
- the catalogue browser;
- the regulatory evaluator;
- the REACH Annex II structure;
- ECHA guidance;
- section, profile and chemical-family phrase recommendations;
- the phrase finder;
- Section 9;
- supplier assessment;
- authoring;
- the canonical registry;
- the Gemini generators.

`main` is not used for integration work. The historical feature branches are retained for provenance only. Their
per-branch instructions are preserved in Git history and in `docs/`. Project rules, the task protocol and the development ledger are in
[`CLAUDE.md`](CLAUDE.md).

```sh
git clone -b integration/offline-eu-gemini https://github.com/ConorTttttt/SDS-Phrases.git
cd SDS-Phrases
```

## Requirements

- Python 3.10+ (CI targets 3.12 and 3.14; locally validated on 3.13). Core features need only the standard library.
- Optional: `python -m pip install -r requirements-documents.txt` (PyMuPDF PDF intake, ReportLab PDF export,
  python-docx DOCX export). Poppler (`pdftotext`) is needed for source indexing and package builds, and Tesseract for OCR.
- Node.js 22+ for the Section 9 module tests. See [`DEPENDENCIES.md`](DEPENDENCIES.md).

## Run the application

```sh
python3 src/server.py            # http://127.0.0.1:8092/   (--port N, --db PATH)
```

| Page | Purpose |
|---|---|
| `/` | Pilot phrase-rule engine |
| `/catalogue.html` | eSDScom catalogue quality browser and metadata review notes |
| `/phrase_finder.html` | Find original catalogue phrases and build a draft selection |
| `/section_recommendations.html`, `/profile_recommendations.html` | Evidence-gated draft phrase candidates (section, product profile, chemical family) |
| `/regulatory.html` | Tri-valued regulatory decision workbench (synthetic demo pack) |
| `/reach.html` | REACH Annex II structure, source index and heading audit |
| `/guidance.html`, `/readiness.html` | ECHA SDS guidance reference and information-readiness prompts |
| `/section9-workspace.html` | Section 9 applicability aid |
| `/authoring.html` | Evidence-led authoring workspace with controlled phrase approvals and revisions |

The server binds to loopback and has **no authentication**. Do not expose it to untrusted networks.
`--host 0.0.0.0` disables review writes. Catalogue-backed routes return 503 until a licensed catalogue is imported.

### Licensed phrase catalogue (local only)

```sh
python3 src/import_catalogue.py /path/to/eSDScom_V5-5_20231131.zip   # writes data/catalogue.sqlite
```

The eSDScom 5.5 catalogue is licensed. It and every derived database stay in `data/` (gitignored). The repository
stores only structure codes and SHA-256 wording fingerprints, never catalogue wording. Verify the current eSDScom
licence terms before redistributing anything phrase-derived.

## Command-line tools

```sh
python3 src/toolkit.py regulatory/example.synthetic.json                     # advisory Article 31 + heading review
python3 src/sds_assessment.py --out ../supplier-cases [--ref11 "/path/REF SDS.pdf"] [--ocr] supplier.pdf
python3 src/sds_assessment.py --out ../reviewed --review review.json supplier.pdf
```

Supplier assessment accepts PDF, DOCX, UTF-8 text or JSON. It writes a case directory per original (by SHA-256)
with `report.html`, JSON/CSV findings, corrective actions and supplier evidence requests. Keep case directories
outside the repository, because they contain confidential supplier data.

## Regulatory sources and canonical registry

The five regulatory PDFs are pinned by SHA-256 in [`regulatory/source_manifest.json`](regulatory/source_manifest.json):
- the REACH consolidation of 22 June 2026;
- the CLP consolidation of 1 July 2026;
- ECHA SDS guidance v4.0;
- the ECHA REF-11 report;
- ECHA CLP labelling guidance v4.2.

Keep the PDFs outside the repository in a directory such as `../pdfs/`, under the exact manifest filenames. They are never committed.

The canonical registry in [`regulatory/canonical/`](regulatory/canonical/README.md) holds three components:
- REACH Annex II: 247 candidates;
- REACH Title IV, Arts. 31–36: 49 candidates;
- CLP label and poison-centre provisions: 73 candidates.

```sh
python3 src/canonical_requirements.py /path/outside/repo/canonical-out [--sources ../pdfs]   # JSON, JSONL, SQLite FTS5
python3 src/canonical_requirements.py --check-committed     # committed generated exports are current
python3 src/canonical_requirements.py --sync-committed      # regenerate requirements.jsonl and coverage_matrix.json
```

`regulatory/canonical/requirements.jsonl` and `coverage_matrix.json` are generated from the maintained JSON
registry and checked by tests. Do not edit them by hand.

## Gemini packages (manual, optional)

```sh
python3 scripts/build_gemini_package.py --sources ../pdfs --out /path/outside/repo/gemini-package [--extract]
python3 gemini/roles/build.py --author ../SDS_Author --sources ../pdfs --out /path/outside/repo/gem-packages
```

The builders produce a legacy single package and separate EU SDS **Writer** and **Compliance Reviewer** packages.
Each package embeds the canonical requirement records, source versions and verification limitations. Both
builders refuse output inside the repository, because packages embed the source PDFs. Nothing is uploaded
automatically. A person attaches the files to Gemini as organisational policy permits. See
[`gemini/roles/README.md`](gemini/roles/README.md) for Gem setup, the offline exchange and blind evaluation.

## Tests

```sh
python3 scripts/run_tests_checked.py --manifest /path/outside/repo/python-validation.json
SDS_SOURCE_DIR=../pdfs SDS_AUTHOR_DIR=../SDS_Author python3 scripts/run_tests_checked.py --manifest /path/outside/repo/python-validation.json
python3 scripts/run_js_tests_checked.py --manifest /path/outside/repo/js-validation.json
```

The checked runner fails on leaked SQLite connections. Source-gated tests run only when the pinned PDFs and
SDS_Author checkout are provisioned. All fixtures are synthetic. Executed results are recorded per commit in
[`VALIDATION.md`](VALIDATION.md) and `validation/*.json`. Coverage and limitations are recorded in
[`regulatory/coverage.json`](regulatory/coverage.json), [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)
and [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

## What is not implemented

The following are not implemented:
- a CLP classification calculator (Annex I);
- an executable Section 3 ingredient-disclosure engine;
- Article 31(3)/32 execution;
- Annex VI extraction;
- label generation;
- autonomous approval or release.

Supply obligations, Section 3 disclosure and mixture classification are kept as separate questions. See
[`ROADMAP.md`](ROADMAP.md).
