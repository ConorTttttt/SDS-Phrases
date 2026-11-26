# CLAUDE.md: EU SDS authoring and regulatory compliance toolkit

This file holds the permanent project instructions for AI-assisted and human development of the
**SDS-Phrases offline EU SDS toolkit**. It applies to every task in this repository and overrides
conflicting statements in older branch-era documentation. Read it in full before changing anything.

| Item | Value |
|---|---|
| Repository | `ConorTttttt/SDS-Phrases` |
| Integration branch | `integration/offline-eu-gemini` (all toolkit work lands here) |
| Protected branch | `main` (`f2dd4a4`). **Never modify, push to, reset or merge into `main`.** |
| Baseline inspected for this file | `19efd59653a9603c41eb70e889a84979527b4c6c` (2026-11-26; no newer remote commits at inspection) |
| Primary frameworks | EU REACH (Regulation (EC) No 1907/2006) and EU CLP (Regulation (EC) No 1272/2008) |
| Runtime | Python 3.10+ standard library, SQLite (FTS5), local browser UI, optional Node 22+ |
| Status | `partial_not_regulator_validated` (see `regulatory/coverage.json`) |

---

## 1. Permanent project instructions

These rules are binding for every task. Cite them by number (R1–R16) in reviews and commit notes.

**Architecture**
- **R1 Offline-first.** Preserve the offline-first Python + SQLite + local browser architecture. The core
  runs on the Python standard library. `src/server.py` binds to `127.0.0.1` by default. Optional tools
  (PyMuPDF, ReportLab, python-docx, Tesseract, Poppler, Node) only affect their own features, and code must
  fail closed with a clear message when one is missing.
- **R2 No mandatory remote dependency.** Never add a mandatory AI API, cloud service, telemetry, CDN or external
  database. Gemini use stays *manual and optional*: generated packages are uploaded by a person. No code
  path may call an AI service. Tests must pass inside a network namespace that has only loopback.
- **R3 Reuse before rebuilding.** Extend the existing implementations listed in §3 and §4. Do not create a
  parallel engine, registry, rule pack or UI for something that already exists. If you must replace something, keep the old
  path working until a migration is tested and documented.

**Regulatory integrity**
- **R4 EU REACH and CLP are primary.** GB, US, CA and NZ structures that exist in older engines are legacy pilots. Do
  not extend them unless asked. Never apply non-EU rules to an EU determination.
- **R5 Preserve provenance and version history.** Every regulatory record keeps `source_id`,
  `source_version`, the source SHA-256 (via `regulatory/source_manifest.json`), clause, PDF page and printed page.
  Never edit legacy records in place. Archive the exact prior record in `historical_versions` and
  give the new content a new rule-version hash. Semantic IDs are never reused for a different obligation.
  Migration targets that are empty mean *unresolved*, not *deleted*.
- **R6 Separate the authority layers.** Keep these apart in data, code, UI text and Gemini output:
  1. **Law**: `binding_law_via_consolidation` / `legislation_consolidation` (REACH, CLP consolidations;
     consolidations are documentation snapshots, *not* the authentic Official Journal text).
  2. **Guidance**: `guidance` (ECHA SDS guidance v4.0, ECHA CLP labelling guidance v4.2). This is interpretive only.
  3. **Enforcement practice**: `enforcement_report` (ECHA Forum REF-11). Inspection references are
     never new legal obligations (`enforcement_crosswalk`).
  4. **Product evidence**: dated supplier/product records. A model inference is never evidence.
  5. **Phrase wording**: eSDScom catalogue and approved internal phrases. These are permissible wording, never
     legal applicability.
- **R7 No invention.** Never invent regulatory thresholds, concentration limits, M-factors, ATEs, legal
  citations, clause or page numbers, H/EUH/P wording, identifiers (CAS, EC, UFI, phrase IDs), dates or
  scientific data. If a value is not in a pinned source or supplied evidence, report it as missing.
- **R8 Missing ≠ absent.** Missing, unknown, withheld or unextracted information never means
  "no hazard", "not applicable" or "compliant". Keep tri-valued logic (`yes` / `no` / `unknown`) and the
  assessment status vocabulary. An empty search result or omitted export field proves nothing.
- **R9 Candidate ≠ executable.** All canonical rows are currently
  `verification_status = candidate_pending_independent_legal_and_extraction_review` and
  `implementation_status = manual_review_only`. A candidate may become an executable rule **only** when all of the following hold:
  (a) independent legal verification against the original page has been done, with tables and footnotes inspected visually;
  (b) currency, amendments and transitional provisions have been resolved for the assessment date;
  (c) the product-evidence logic has been reviewed;
  (d) positive, negative and unknown-input regression tests exist;
  (e) a new rule-version hash is issued and the prior version is archived;
  (f) `regulatory/coverage.json` has been updated;
  (g) the named competent-person sign-off is recorded in the commit and evidence file.
  A text match is never enough to promote a candidate.
- **R10 Keep the three Section 3 / supply questions separate.** The three are:
  (i) **SDS supply obligation** (REACH Art. 31(1)/(3)/(4), Art. 32; `src/toolkit.py`, `canonical/title_iv.json`);
  (ii) **Section 3 ingredient disclosure** (Annex II 3.1/3.2; `REACH_SECTION3_DISCLOSURE_ENGINE.md`);
  (iii) **mixture classification** (CLP Annex I, not implemented).
  A component can be disclosable without contributing to classification, and the reverse also holds. Never derive one
  from another.

**Data protection and licensing**
- **R11 eSDScom catalogue.** Preserve the original eSDScom 5.5 catalogue unchanged. Source Excel cells
  are never rewritten. Git stores only structure codes and SHA-256 wording fingerprints, never catalogue
  wording. Core official phrase IDs are blank in the source, and internal row keys are *not* official IDs. The
  invalid date `20231131` in the source filename is preserved, not interpreted. Verify the current eSDScom licence before
  redistributing anything phrase-derived.
- **R12 Never commit** confidential formulations, product dossiers, supplier SDSs or records, assessment
  case directories, review JSON, Gemini exchange exports/responses, `phrase_approvals.sqlite`,
  `authoring_workspace.sqlite`, licensed catalogue databases (`data/catalogue.sqlite`), guidance archives,
  source PDFs, or generated Gemini packages (they embed the PDFs). Fixtures must be synthetic and
  labelled as such. Before every commit, run `git status --porcelain` and `git diff --cached --stat` and inspect them.
- **R13 Gemini synchronisation.** The Writer and Reviewer packages are *generated* from the canonical
  registry. They are never hand-edited. Any change under `regulatory/canonical/`, `regulatory/author/`,
  `regulatory/assessment/`, `regulatory/source_manifest.json`, `regulatory/coverage.json`, `gemini/` or
  `rules/` that the builders consume requires regenerating both role packages and the legacy package, then
  running the sync check in §8.

**Release and honesty**
- **R14 Competent-person release.** Nothing produced here is a certified SDS. Every draft, finding or Gemini
  output requires verification by a named competent person before professional release. No code may set
  an approved, released or compliant state autonomously. Output keeps `legal_compliance_determined: false`,
  `sds_compliant: false` and `regulation_verified: false` where those fields exist.
- **R15 Truthful validation.** Never claim tests, builds, CI or legal checks passed unless they were actually
  executed and their output was observed. Report executed, skipped, blocked and not-run counts separately. GitHub
  Actions runs with zero steps or `runner_id=0` are **not** test execution.
- **R16 Git safety.** Never force-push, rewrite published history, reset or overwrite another developer's
  commits, or delete branches you did not create. If the remote advanced, fetch and merge (or rebase only your
  own unpublished commits) and keep concurrent work intact.

---

## 2. Mandatory task protocol

Every subsequent task must follow these steps in order and report on each one.

1. **Inspect Git state.** Run `git fetch origin`, then `git status -sb`, then `git log --oneline -5 origin/integration/offline-eu-gemini`.
   Confirm the tip against the last recorded baseline and read any commits that are new since it.
2. **Identify reusable code.** Search `src/`, `regulatory/`, `rules/`, `gemini/`, `modules/` and `scripts/`
   (see §3 and §4) and name the functions or packs you will extend.
3. **Implement working changes.** Make the smallest coherent change. Use the stdlib only in the core (R1/R2).
4. **Add regression tests.** Add them under `tests/` (or `gemini/roles/test_*.py`, `modules/section9/tests/`). Cover
   positive, negative **and unknown/missing-input** cases (R8). Use only synthetic fixtures.
5. **Execute the available tests.** Run the checked Python runner, the JS runner and the syntax checks (§6). Write manifests
   outside the tracked tree. Provision `SDS_SOURCE_DIR` / `SDS_AUTHOR_DIR` when sources are available.
   Report the real counts.
6. **Update regulatory coverage.** Update `regulatory/coverage.json`. For canonical changes, also update the release id, the counts and
   `regulatory/canonical/SOURCE_VERIFICATION.md`. Regenerate the Gemini packages and run the sync check (R13).
7. **Document limitations.** Update `KNOWN_LIMITATIONS.md` and `IMPLEMENTATION_STATUS.md`, plus `VALIDATION.md` and a
   `validation/<topic>-<sha8>.json` evidence file when tests or source checks were executed. Update the
   ledger in §11 of this file.
8. **Commit to the integration branch.** Commit on `integration/offline-eu-gemini`. If the session harness
   mandates a session branch (for example `ccr-*`), create it from `origin/integration/offline-eu-gemini`, commit
   there, and fast-forward the integration branch only when the push is authorised. Use one logical change per
   commit. Write the subject in the imperative, describing the regulatory or evidence effect. Never put a model
   identifier in commit text.
9. **Verify the remote commit after an authorised push.** Run `git ls-remote origin <branch>` and confirm it equals
   `git rev-parse HEAD`. Then record the CI run id and its real conclusion (including "no steps executed").

---

## 3. Architecture

```
 Local, hash-pinned inputs (never in Git)          Committed knowledge & rules              Interfaces
 ──────────────────────────────────────           ───────────────────────────              ──────────
 5 regulatory PDFs ($SDS_SOURCE_DIR) ──verify──▶ regulatory/source_manifest.json
                                       │         regulatory/canonical/*.json  ──build──▶ requirements.sqlite (FTS5, generated)
                                       └───────▶ regulatory/assessment/*.json            │
 eSDScom 5.5 ZIP ──import──▶ data/catalogue.sqlite ◀── rules/*.json (codes + SHA-256)   ├─▶ src/server.py + web/*  (127.0.0.1:8092)
 ECHA guidance ZIP ──import──▶ data/echa_guidance_2020.sqlite                             ├─▶ CLIs: toolkit, sds_assessment, ...
 REACH PDF ──index──▶ data/reach_annex2_2026.sqlite                                       ├─▶ Gemini legacy package (scripts/)
 Supplier SDS (PDF/DOCX/TXT/JSON) ──▶ case dir outside repo (sds_assessment)              └─▶ Gemini Writer + Reviewer (gemini/roles/)
 SDS_Author pinned revisions (git) ─────────────────────────────────────────────────────────▲
```

### 3.1 Layers and directories

| Path | Role |
|---|---|
| `src/` | Python engines, builders, CLIs and the stdlib HTTP server (see §4) |
| `web/` | Static browser UI served by `src/server.py`. No external libraries. `web/section9-rules.js` must stay byte-identical to `modules/section9/rules.mjs` (tested) |
| `modules/section9/` | Original EU_SDS Section 9 applicability module and its 11 Node tests. Byte-identical to `ConorTttttt/EU_SDS@3e4272d` |
| `regulatory/canonical/` | **Canonical knowledge base** (§5). Committed JSON is the maintained source of truth |
| `regulatory/assessment/` | Legacy reference data: `annex_ii.json` (597 Annex II source rows), `clp_english.json` (H/EUH statement register), `ref11.json` (45 REF-11 questions) |
| `regulatory/author/` | Copy of SDS_Author EU SDS authoring skill v4 (`SKILL.md`, 12 reference playbooks, the 46-locator `REACH_RULE_INDEX.jsonl`, 3 test-specification files holding 128 specs, static `tests/check_package.py`) |
| `regulatory/source_manifest.json` | Hash, page and version pins for the five regulatory PDFs |
| `regulatory/coverage.json` | Coverage register: implementation and validation status per module |
| `regulatory/upstream.json` | Pinned upstream repositories and commits |
| `rules/` | Versioned rule and candidate packs (§7) |
| `sources/source_register.json` | Descriptive source register (non-binding references) |
| `gemini/` | `GEMINI_SYSTEM_PROMPT.md` (legacy), `roles/` Writer/Reviewer generator, `WORKFLOWS.md` (12 commands), exchange, evaluation |
| `scripts/` | Legacy Gemini builder, checked test runners, phrase-source verifiers |
| `fixtures/` | Synthetic fixtures only (`assessment/contradictory-mixture.json`) |
| `validation/` | Commit-linked execution evidence (`sds-validation/v1` and related) |
| `docs/` | Per-feature design notes (historical branch docs; see §12 for drift) |
| `data/` | Local-only databases (gitignored except `.gitkeep`) |

### 3.2 Local data files (all gitignored, all confidential or licensed)

| File | Created by | Content |
|---|---|---|
| `data/catalogue.sqlite` | `src/import_catalogue.py` | Licensed eSDScom 5.5 catalogue + index |
| `data/catalogue_reviews.sqlite` | catalogue browser | Metadata review notes (not regulatory approval) |
| `data/echa_guidance_2020.sqlite` | `src/guidance_sources.py` | ECHA guidance Markdown index |
| `data/reach_annex2_2026.sqlite` | `src/reach_annex2_source.py` | REACH Annex II page index |
| `data/phrase_approvals.sqlite`, `data/authoring_workspace.sqlite` | authoring API (beside the catalogue) | Approved phrases, product dossiers, revisions. **Confidential** |

### 3.3 Upstream pins (`regulatory/upstream.json`; read-only inputs)

| Role | Repository @ commit | Use |
|---|---|---|
| base | `SDS-Phrases@a12fcf0` | Integration started from `feature/chemical-family-phrase-recommendations` |
| author (reviewer pin) | `SDS_Author@ba00146` (`feature/eu-sds-compliance-reviewer-v1`) | Reviewer package references and templates |
| writer pin (in `gemini/roles/build.py`) | `SDS_Author@2c6cc78` (`feature/eu-sds-writing-only-v5`) | Writer package references and templates |
| section9 | `EU_SDS@3e4272d` | `modules/section9/` |
| design_reference | `Rrgulatory_LLM_Optimised@60d378d` | Architecture only. **No Korean rules imported** |

`SDS_Author` `main` tracks three source PDFs. Do not copy that practice into this repository.

---

## 4. Regulatory and functional modules

| Module (coverage id) | Implementation | Status (coverage.json) | Scope and limits |
|---|---|---|---|
| Article 31 supply (`article31`) | `src/toolkit.py` (`article31`, CLI) + `canonical/title_iv.json` | partial | Art. 31(1)/(4) positive trigger routing only. 31(3), 32 and special CLP triggers are not executable |
| Annex II structure (`structure`) | `src/reach_annex2_audit.py`, `rules/eu_reach_annex2_partb_2026.json` | implemented, structural only | 16 sections + 51 subsection headings. Heading presence ≠ content adequacy |
| Section 3 disclosure (`section3`) | `regulatory/author/references/REACH_SECTION3_DISCLOSURE_ENGINE.md` | knowledge only | No executable disclosure engine |
| Section 9 (`section9`) | `modules/section9/rules.mjs` (+ `web/section9-*`) | partial | 9.1 applicability heuristic, 9.2 reference lists. Unknown-input guard |
| Section 8 / readiness (`section8`) | `src/sds_readiness.py`, `rules/eu_sds_guidance_readiness_pilot.json` | evidence prompts only | 27 ECHA-guidance prompts for Sections 4, 7, 8 |
| CLP label/classification (`section2`, `clp`) | `canonical/clp.json` (candidates only) | not implemented as engine | No classifier, no Annex I calculation, no label generator |
| REF-11 (`ref11`) | `src/sds_assessment.py`, `regulatory/assessment/ref11.json` | partial | Question-indexed manual worksheet. 17/45 questions have candidate legal links |
| Cross-section (`cross_section`) | `src/sds_assessment.py` | partial | 12 relationships routed to review. Selected deterministic conflicts |
| Multi-product (`multi_product`) | `src/sds_assessment.py` | partial | Per-original content-hash isolation. No cross-supplier reconciliation |
| Supplier intake (`pdf_ingestion`) | `src/sds_intake.py` | partial | PDF (PyMuPDF), OCR (Tesseract), DOCX, TXT, JSON. Pictogram/image candidates need visual review |
| Phrases (`phrases`) | `src/engine.py`, `section_recommendations.py`, `profile_phrase_engine.py`, `chemical_families.py`, `phrase_finder.py` | draft candidates only | 7 pilot rules, 105 section paths, 38 profile cues, 23 family mappings. Needs the local catalogue |
| Catalogue (`catalogue`) | `src/import_catalogue.py`, `catalogue_index.py`, `catalogue_browser.py`, `catalogue_reviews.py` | implemented | Live licensed wording not verified in CI |
| Regulatory engine | `src/regulatory_engine.py`, `rules/regulatory-demo-v0.2.json` | demo | Tri-valued evaluator. The demo pack is synthetic and unverified |
| Guidance sources | `src/guidance_sources.py`, `src/guidance_pdf_verification.py` | implemented | Non-binding. Verifies hash, page count and chapter anchors only |
| REACH source index | `src/reach_annex2_source.py` | implemented | Accepts the full 603-page PDF or the legacy 36-page excerpt (`3e6304eb…`) |
| Canonical registry | `src/canonical_requirements.py` | implemented (candidate data) | Builds JSON/JSONL/SQLite FTS5, migration, clause lookup, version resolution |
| Authoring workspace (`authoring_workspace`) | `src/sds_authoring.py`, `src/authoring_api.py`, `web/authoring.*` | implemented, draft only | Controlled phrase approval/revocation, revisions, review gates, JSON/PDF/DOCX draft export. No release |
| Gemini (`gemini`) | `scripts/build_gemini_package.py`, `gemini/roles/build.py` | generators implemented | Live Gemini behaviour not validated |
| Exchange (`exchange_import`) | `gemini/roles/exchange.py` | implemented, pending human review | Selective export. Import only stages `pending.json` |
| Source integrity (`source_integrity`) | `src/package_sources.py` | partial | Hash and page verification. Currency and extraction fidelity not verified |

**Security conventions for the HTTP server:** writes are loopback-only. Authoring writes also require the
`X-SDS-Local-Review: 1` header and a JSON content type, with a request-size limit. Catalogue review writes are refused when the
server is bound to a non-loopback host. There is **no authentication**: never expose the server publicly.

---

## 5. Canonical knowledge base (`regulatory/canonical/`)

Committed JSON is maintained. SQLite and JSONL exports are **generated** by `src/canonical_requirements.py`
and are never a second maintained copy.

| File | Schema / release | Content |
|---|---|---|
| `requirements.json` | `sds-canonical-requirements/v1`, `2026-11-26-annex-ii-expanded-r2` | 247 Annex II candidate targets (general provisions + all 16 sections), `migration` (597 legacy dispositions, 0 unresolved), `source_annotations`, `historical_versions` (1), `enforcement_crosswalk` (45 REF-11 refs, 17 linked) |
| `title_iv.json` | `sds-canonical-title-iv/v1`, `2026-11-26-title-iv-r1` | REACH Arts. 31–36: 42 source records, 49 candidates, 11 legacy author-index mappings |
| `clp.json` | `sds-canonical-clp/v1`, `2026-11-26-clp-label-pcn-r2` | CLP Arts. 4, 17–22, 24–29 and Annex VIII Parts A/B: 85 source records, 73 candidates, 1 reference-only table (Annex VIII Table 4), 9 explicit `coverage_gaps`, 6 historical versions, `source_text_check` 85/85 |
| `requirements.jsonl` | generated (`jsonl()`) | 247 Annex II rows in canonical JSONL: sorted keys, compact separators, UTF-8, LF. Force-tracked because `*.jsonl` is gitignored |
| `coverage_matrix.json` | generated (`coverage_matrix()`) | Per-section candidate coverage derived from `coverage()`. Never hand-edit. Regenerate with `--sync-committed`; tests fail on drift |
| `README.md`, `TITLE_IV.md`, `CLP.md`, `SOURCE_VERIFICATION.md` | docs | Method, official-source checks, executed source evidence |

**Requirement record fields:** `id`, `source_id`, `source_version`, `legal_authority_type`, `clause`,
`table_references`, `printed_pages`, `pdf_pages`, `wording`, `applicability_conditions`, `exceptions`,
`required_product_evidence`, `required_sds_content`, `assessment_methodology`, `related_requirements`,
`effective_date`, `transition_rules`, `verification_status`, `implementation_status`, `test_ids`, `modality`
and either `legacy_ids` (Annex II) or `source_record_ids` (Title IV/CLP; CLP adds `sds_section` and `context_record_ids`).

**Controlled vocabularies.** Code validates these, so do not add values silently:
- `assessment_methodology` (`METHODS` in `src/canonical_requirements.py`): `structural_presence`,
  `conditional_applicability`, `numeric_threshold`, `required_factual_information`, `required_wording`,
  `scientific_adequacy`, `cross_section_consistency`, `external_supply_chain`, `competent_person_judgement`.
- `modality`: `candidate_obligation_or_conditional_assessment_target`, `conditional_assessment_target`,
  `permitted_alternative_with_conditions`, `external_obligation_candidate`.
- Assessment statuses (`src/sds_assessment.py`, `gemini/roles/exchange.py`): *Compliant against assessed
  requirement*, *Non-compliant*, *Potential non-compliance*, *Insufficient evidence*, *Not applicable*,
  *Not assessed*, *Requires competent-person review*.
- Exchange review dimensions: applicability, presence, completeness, regulatory_adequacy,
  scientific_plausibility, internal_consistency, expert_judgement.

**API:** `load(root)`, `load_title_iv`, `load_clp`, `all_requirements`, `requirement_version`,
`resolve_requirement_version` / `resolve_any_requirement_version`, `resolve_legacy`, `retrieve_clause`,
`search`, `coverage`, `coverage_matrix`, `jsonl`, `committed_exports`, `sync_committed`, `knowledge_base_markdown`, `title_iv_coverage`, `clp_coverage`, `verify_clp_pdf`, `evaluate_requirement`,
`inspection_link`, `build`.

**Invariants:** stable semantic IDs; content-derived rule-version hashes; legacy rows immutable
(`legacy_snapshot` pins the inventory blob `1bf7a9f…`); REF-11 entries stay in `enforcement_crosswalk`;
Section 9.2 illustrative data are not standalone duties; Annex II, Title IV and CLP remain separate
components even in combined exports.

---

## 6. Commands

Run from the repository root. `PYTHONUTF8=1` is recommended (CI sets it). Results marked ✅ were executed
at `19efd59` on 2026-11-26 (Linux, CPython 3.13.18, Node 22.23.5); see §10.

### 6.1 Setup
```sh
python3 -m pip install -r requirements-documents.txt      # optional: PyMuPDF, ReportLab, python-docx
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-eng   # optional: pdftotext, OCR
# Node.js 22+ for Section 9 tests. iproute2 ('ip') is needed for the network-namespace test run.
```

### 6.2 Run the application ✅
```sh
python3 src/server.py                      # http://127.0.0.1:8092/  (--port N, --db PATH)
```
Pages: `/` (pilot engine), `/catalogue.html`, `/regulatory.html`, `/guidance.html`, `/reach.html`,
`/section_recommendations.html`, `/readiness.html`, `/phrase_finder.html`,
`/profile_recommendations.html`, `/section9-workspace.html`, `/authoring.html`.
Without a catalogue, catalogue routes return 503 (fail closed). `--host 0.0.0.0` is unauthenticated and
disables review writes. Use it only on a trusted LAN.

Licensed catalogue (local only):
```sh
python3 src/import_catalogue.py /path/to/eSDScom_V5-5_20231131.zip   # -> data/catalogue.sqlite
python3 src/catalogue_index.py data/catalogue.sqlite                 # upgrade an existing v0.1 DB in place
```

### 6.3 Python tests ✅
```sh
python3 scripts/run_tests_checked.py --manifest /path/outside/repo/python-validation.json
#   discovers tests/test_*.py AND gemini/roles/test_exchange.py; fails on leaked SQLite connections
SDS_SOURCE_DIR=/path/to/pdfs SDS_AUTHOR_DIR=/path/to/SDS_Author \
  python3 scripts/run_tests_checked.py --manifest /path/outside/repo/python-validation.json
#   enables the real-source package test and the dual-role build test
sudo unshare --net -- bash -c 'ip link set lo up; exec "$1" scripts/run_tests_checked.py --manifest "$2"' \
  _ "$(command -v python3)" /path/outside/repo/python-validation.json     # offline proof (Linux)
python3 -m unittest discover -s tests -v   # quick run; omits gemini/roles exchange tests and leak check
python3 -m compileall -q src tests scripts regulatory/author gemini/roles
```

### 6.4 JavaScript tests ✅
```sh
python3 scripts/run_js_tests_checked.py --manifest /path/outside/repo/js-validation.json   # 11 Node TAP tests
node --test modules/section9/tests/rules.test.mjs
for f in web/*.js; do node --input-type=module --check < "$f" || exit 1; done            # 12 files
```

### 6.5 Regulatory database builders and verifiers
```sh
python3 src/canonical_requirements.py /path/outside/repo/canonical-out                     # ✅ JSON/JSONL/SQLite FTS5
python3 src/canonical_requirements.py /path/outside/repo/canonical-out --sources "$SDS_SOURCE_DIR"  # ✅ + 2,566 PDF pages
python3 src/canonical_requirements.py --check-committed   # exit 1 if requirements.jsonl / coverage_matrix.json are stale
python3 src/canonical_requirements.py --sync-committed    # regenerate them after any registry change, then commit
PYTHONPATH=src python3 -c "import canonical_requirements as c; print(c.verify_clp_pdf(c.load_clp(), '$SDS_SOURCE_DIR/CELEX_02008R1272-20260701_EN_TXT.pdf'))"  # ✅ 85/85
python3 src/reach_annex2_source.py "$SDS_SOURCE_DIR/Full REACH.pdf" --db data/reach_annex2_2026.sqlite    # ✅
python3 src/guidance_pdf_verification.py "$SDS_SOURCE_DIR/sds_guidance.pdf" [--archive CLP_A_I-main.zip [--db data/echa_guidance_2020.sqlite]]  # ✅ (PDF only)
python3 src/guidance_sources.py /path/to/CLP_A_I-main.zip        # ECHA guidance Markdown -> data/echa_guidance_2020.sqlite (archive not available here)
python3 scripts/verify_section_phrase_sources.py                 # needs data/catalogue.sqlite (blocked here)
python3 scripts/verify_family_phrase_sources.py                  # needs data/catalogue.sqlite (blocked here)
```

### 6.6 Gemini package generators ✅
```sh
# Legacy single package (output must be outside the repo; enforced by the builder)
python3 scripts/build_gemini_package.py --sources "$SDS_SOURCE_DIR" --out /path/outside/repo/gemini-package [--extract]
# Writer + Reviewer roles (needs git, pdftotext and an SDS_Author clone with both pinned commits fetched)
git -C ../SDS_Author fetch origin feature/eu-sds-writing-only-v5 feature/eu-sds-compliance-reviewer-v1
python3 gemini/roles/build.py --author ../SDS_Author --sources "$SDS_SOURCE_DIR" --out /path/outside/repo/gem-packages
#   Both builders refuse output paths inside the repository (packages embed the PDFs).
```
Offline exchange and blind evaluation:
```sh
python3 src/sds_assessment.py --out ../supplier-cases [--ref11 "$SDS_SOURCE_DIR/REF SDS.pdf"] [--ocr] supplier.pdf   # ✅ on fixture
python3 src/sds_assessment.py --out ../reviewed --review review.json supplier.pdf
python3 gemini/roles/exchange.py export CASE/findings.json PRODUCT-REV export.json --select heading/1:section
python3 gemini/roles/exchange.py import CASE/findings.json PRODUCT-REV pending.json --bundle export.json --response gemini-response.json
python3 evaluate.py evaluation.json A01 [--expected]     # inside an extracted role package
python3 src/toolkit.py regulatory/example.synthetic.json # ✅ advisory Article 31 + heading review
```

---

## 7. Schemas and data contracts

| Schema id | File(s) |
|---|---|
| `sds-source-manifest/v1` | `regulatory/source_manifest.json` |
| `sds-coverage/v1` | `regulatory/coverage.json` |
| `sds-canonical-requirements/v1`, `sds-canonical-title-iv/v1`, `sds-canonical-clp/v1` | `regulatory/canonical/*.json` |
| `sds-regulatory-rules/v0.2` | `rules/regulatory-demo-v0.2.json` (`src/regulatory_engine.py`) |
| `reach-annex2-part-b-structure/v0.1` | `rules/eu_reach_annex2_partb_2026.json` |
| `reach-annex2-content-inventory/v0.1` | `rules/eu_reach_annex2_content_inventory_draft.json` (28 items; `exhaustive=false`, `executable=false`; pinned to the 36-page excerpt hash) |
| `sds-information-readiness-prompts/v0.1` | `rules/eu_sds_guidance_readiness_pilot.json` |
| `sds-section-phrase-recommendations/v0.1` | `rules/section_phrase_candidates_v0.1.json` (105 paths) |
| `sds-phrase-profile-recommendations/v0.1` | `rules/eu_profile_phrase_relevance_v01.json` (38) |
| `sds-chemical-family-phrase-cues/v0.1` | `rules/eu_chemical_family_phrase_cues_v01.json` (10 families, 23 rules) |
| (untyped pilot) | `rules/pilot-eu-gb-v1.json` (7 draft rules) |
| `sds-source-register/v0.1` | `sources/source_register.json` |
| `sds-toolkit-assessment/v1` | `src/toolkit.py` output |
| `sds-validation/v1` | runner manifests and `validation/*.json` |
| JSON Schemas | `INTAKE` / `OUTPUT` in `gemini/roles/exchange.py` → `product-intake.schema.json`, `assessment-output.schema.json` in role packages |

Each pack records its draft or unverified state, either at the top level (`status` / `review_status`), per rule (for example `"unverified"` in the demo pack), or in source metadata (`source.source_status` in the Part B structure). Keep these fields accurate, and never set a verified state without meeting the R9 gate.

---

## 8. Source documents

### 8.1 The five pinned regulatory PDFs

Expected local path: **`$SDS_SOURCE_DIR/<manifest filename>`**, using the exact filenames below including spaces. The
recommended location is a sibling of the checkout, for example `../pdfs/`. **Never place them inside the repository**
(`*.pdf` is gitignored, but generated packages embed them). Builders copy them under the package filename.

| id | Manifest filename | Package filename | Edition / identity | Authority | Pages | SHA-256 |
|---|---|---|---|---|---|---|
| `reach` | `Full REACH.pdf` | `REACH_1907_2006_consolidated_EN_2026-06-22.pdf` | EUR-Lex consolidation `02006R1907 — EN — 22.06.2026 — 069.001` | legislation_consolidation | 603 | `04e3d65150eeed337e09f2a6d4a6cb6dae47a0bda488bebcef44972092147572` |
| `clp` | `CELEX_02008R1272-20260701_EN_TXT.pdf` | `CLP_1272_2008_consolidated_EN_2026-07-01.pdf` | EUR-Lex consolidation `02008R1272 — EN — 01.07.2026 — 031.001` | legislation_consolidation | 1584 | `602529287cbdbbb80f4bc17404fef58041ce5edf30646509b3cdb6991b7fc8a7` |
| `echa` | `sds_guidance.pdf` | `ECHA_Guidance_on_Compilation_of_SDS_v4_Dec2020.pdf` | ECHA Guidance on the compilation of SDS v4.0, Dec 2020, ECHA-20-H-25-EN | guidance | 137 | `2a4ac00f87544ebc6397e208e13da331a5ebabd6c5ceb5f149e84cb138501c28` |
| `ref11` | `REF SDS.pdf` | `ECHA_REF11_SDS_Enforcement_Report_Dec2024.pdf` | ECHA Forum REF-11 project report on SDS, Dec 2024, ECHA-24-R-13-EN | enforcement_report | 42 | `2514559e63f7348e001d8b3578d264144fcd70bac317ad218de0183971a132a0` |
| `label` | `clp_labelling_enGuidance.pdf` | `ECHA_CLP_Labelling_Guidance_v4_2_Mar2021.pdf` | ECHA Guidance on labelling and packaging v4.2, Mar 2021, ECHA-21-G-02-EN | guidance | 200 | `cd0dffa85a5ae00ab46d82da9ec184788caa9d9a46f5bac829f6146a243615ae` |

**Verification on 2026-11-26:** four PDFs were supplied as session uploads (REACH, ECHA SDS guidance, REF-11,
CLP labelling guidance), and their SHA-256 values and page counts match the manifest. The CLP consolidation was **not**
among the uploads. It was obtained from the official EUR-Lex URL
`https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02008R1272-20260701`, and its SHA-256 and page
count match the manifest exactly. All five `currentness` values remain `not_verified_after_snapshot`. Known
post-snapshot amendments that must be reconciled before any date-specific execution are listed in
`regulatory/canonical/SOURCE_VERIFICATION.md` and `CLP.md`: REACH 2026/2382, 2026/2501, 2026/2530; CLP
2025/2439, 2024/2865, 2026/2382 Art. 2.

### 8.2 Other local inputs (never committed)

| Input | Use | Identity |
|---|---|---|
| `eSDScom_V5-5_20231131.zip` | `src/import_catalogue.py` | Licensed. Digest recorded on import |
| `CLP_A_I-main.zip` | `src/guidance_sources.py` | ECHA SDS guidance v4.0 Markdown (not CLP Annex I despite the name) |
| `Full REACH_removed.pdf` | `src/reach_annex2_source.py` (legacy) | 36-page Annex II excerpt, SHA-256 `3e6304eb92c7ffb0b82fc7d634ac825f0bc8849195c81ac5d7efa4b16ead66fb` |
| Supplier SDSs, product records | `src/sds_assessment.py`, authoring | Confidential. Case directories go outside the repo (they also receive a copy of the REF-11 PDF) |

---

## 9. Gemini Writer/Reviewer synchronisation

- Both role packages share one `shared/` build stage generated from `load_canonical`, `load_title_iv` and
  `load_clp`, plus `regulatory/author/references` (falling back to the pinned SDS_Author reviewer revision),
  `regulatory/assessment/*`, `source_manifest.json`, `coverage.json` and the page-chunked PDFs. Role-specific
  references and templates come from the pinned SDS_Author commits in `PINS`.
- `evaluation.json` must contain exactly 128 upstream cases + 6 `X` extensions = 134. The builder fails if the
  upstream inventory changes.
- **Sync check (run after every regeneration):** for each role, `canonical-requirements.json`,
  `canonical-clp.json` and `canonical-title-iv.json` `requirements` arrays must equal the committed
  `regulatory/canonical/*.json` arrays. This was verified for both roles at `19efd59`. Changing a PIN or adding
  upstream references requires a ledger entry and regenerated packages.
- The legacy `SINGLE_FILE_LLM_KNOWLEDGE_BASE.md` embeds the system prompt, coverage, author references and,
  via `knowledge_base_markdown()`, all 369 canonical records with source versions/SHA-256, rule versions,
  verification status and limitations (scopes and CLP coverage gaps).
- Generated packages contain the five PDFs (about 19.6 MB per role ZIP). Never commit them. No live Gemini
  output has been validated. Record blind-evaluation results using the protocol in `gemini/roles/README.md`
  (PASS / FAIL / NEEDS_MANUAL_REVIEW / NOT RUN counted separately).

---

## 10. Tests and validation evidence

### 10.1 Inventory (217 Python tests + 11 Node tests)

| Test module | Tests | Notes |
|---|---|---|
| `test_section_recommendations` | 21 | |
| `test_chemical_families` | 19 | |
| `test_profile_phrase_engine` | 17 | |
| `test_phrase_finder` | 16 | |
| `test_engine`, `test_reach_annex2`, `test_regulatory_engine` | 14 each | |
| `test_sds_readiness` | 12 | |
| `test_supplier_assessment` | 10 | 1 needs PyMuPDF (+ Tesseract for OCR) |
| `test_guidance_sources`, `test_intake_optional`, `test_sds_authoring` | 7 each | intake: 2 need PyMuPDF, 1 needs Tesseract |
| `test_canonical_clp`, `test_canonical_requirements`, `test_catalogue_phase1`, `test_toolkit_integration` | 6 each | |
| `test_stabilisation` | 4 | 1 needs `SDS_SOURCE_DIR` |
| `test_canonical_title_iv`, `test_package_sources`, `test_regulatory_api` | 3 each | package: 1 needs `SDS_SOURCE_DIR` + `SDS_AUTHOR_DIR` |
| `test_integration_fixes` | 17 | JSONL/matrix determinism, drift, legacy KB records, output guards, coverage evidence, LF line endings |
| `test_import_catalogue` | 2 | |
| `test_authoring_http` | 1 | HTTP round-trip |
| `gemini/roles/test_exchange` | 2 | |
| `modules/section9/tests/rules.test.mjs` (Node) | 11 | Upstream-identical |

Test specifications in `regulatory/author/references/*TEST_CASES.md` (128) are **specifications, not executed
tests**. `regulatory/author/tests/check_package.py` is a static package check. It runs inside the legacy builder
output, not from the repo tree, because it expects bundled PDFs.

### 10.2 Executed at `19efd59` (2026-11-26, clean tree)

| Check | Result |
|---|---|
| Checked Python runner, default environment (no PyMuPDF, Tesseract or sources) | 198 run: 192 passed, 6 skipped. Exchange 2/2. 0 SQLite leaks |
| With `SDS_SOURCE_DIR` + `SDS_AUTHOR_DIR` | 194 passed, 4 skipped (PyMuPDF/Tesseract) |
| With PyMuPDF 1.26.7, ReportLab 4.4.9, python-docx, Tesseract 5.3.4 and sources | **198/198 + 2/2 passed, 0 skipped** |
| Same, inside `unshare --net` (loopback only; external HTTPS confirmed unreachable) | **200/200 passed**. An earlier attempt errored 76 times because `ip` was missing and loopback stayed down. That was an environment issue |
| Node runner | 11/11 passed. 12 `web/*.js` syntax checks passed. `compileall` OK |
| Canonical builder (with and without `--sources`) | OK. 369 requirement rows (247+49+73). 3,281 source-record rows with PDFs. Committed `requirements.json`, `clp.json` and `title_iv.json` are byte-identical to builder output. `requirements.jsonl` is semantically identical but serialised differently |
| `verify_clp_pdf` | 85 checked, 0 unmatched (`text_match_only`) |
| REACH index, ECHA guidance PDF verifier | OK |
| Legacy Gemini builder `--extract` | OK. `check_package.py`: static PASS (23 files, 46 locators, 48 scenarios) |
| Role builder | Writer + Reviewer ZIPs built. Canonical arrays equal the committed registry. 134 evaluation cases |
| `sds_assessment.py` on fixture with `--ref11`; `toolkit.py` on synthetic example | OK. `legal_compliance_determined: false` |
| Server smoke | `/`, `/api/info`, `/api/regulatory/pack`, `/api/reach/structure`, `/section9-workspace.html`, `/authoring.html` returned 200. `/api/catalogue/summary` returned 503 without a catalogue (expected) |
| Phrase-source verifiers | **Blocked**: no licensed catalogue (`missing_local_catalogue`; 23 family mappings blocked) |
| GitHub Actions run 45892880848 (`19efd59`) | **Failure, all 4 jobs ended in ~3 s**, consistent with the earlier zero-step runs. No CI test execution is established |

### 10.3 Executed at `8165686` (integration defect fixes, 2026-11-26, clean tree)

| Check | Result |
|---|---|
| Checked Python runner, full optional dependencies + sources | **212/212 + 2/2 passed, 0 skipped**, 0 SQLite leaks |
| Same inside `unshare --net` (loopback only) | **214/214 passed** |
| Default environment | 208 passed, 6 skipped (optional tools/sources) |
| Node runner / web syntax / compileall | 11/11 passed / 12/12 / OK |
| `test_integration_fixes` against previous code | 3 failures + 12 errors (confirms the tests detect the defects) |
| Gemini rebuild (legacy + Writer + Reviewer) with five pinned PDFs | All canonical components identical to the registry (247/49/73 records, IDs, rule versions, releases); embedded PDFs match the manifest; legacy single file contains all 369 records |
| Canonical determinism | Two builds byte-identical (non-SQLite); committed JSONL and matrix equal builder output |

### 10.4 Executed at `a76511c` (Windows LF fix)

| Check | Result |
|---|---|
| Checked Python runner, full optional dependencies + sources | **215/215 + 2/2 passed** |
| Same inside `unshare --net` | **217/217 passed** |
| Default environment / Node | 211 passed, 6 skipped / 11/11 |
| Gemini rebuild + sync check | All canonical components, coverage register and manifest identical to the repo |
| CI history | Run 45908436704 (be0524e) and run 45909764858 (9130ba5): Ubuntu passed; Windows failed from CRLF checkout (fixed here). Windows CI confirmation pending |

Evidence files: `validation/full-19efd596.json`, `validation/integration-fixes-81656862.json`, `validation/integration-fixes-a76511c0.json`. These results cover only commit `19efd59`. Later commits
need their own runs. None of this is legal or regulatory validation.

---

## 11. Development task ledger

Statuses: **Done** means implemented with executed evidence (not legally verified). **Partial** means a limited slice is implemented.
**Blocked** means an external dependency is missing. **Outstanding** means not started.

| ID | Item | Status | Notes / next step |
|---|---|---|---|
| L01 | Offline stdlib server and 11 browser pages | Done | Smoke-tested. Browser E2E outstanding (L33) |
| L02 | eSDScom import, index, browser, review notes | Done (synthetic) | Live licensed data blocked (L24) |
| L03 | Source manifest and hash/page verification for all 5 PDFs | Done | Currency not verified (L30) |
| L04 | Canonical Annex II r2 (247 candidates, 597 dispositions, REF-11 crosswalk) | Done as candidates | Legal verification blocked (L27) |
| L05 | Canonical Title IV r1 (Arts. 31–36, 49 candidates) | Done as candidates | Same |
| L06 | Canonical CLP label/PCN r2 (73 candidates, 85/85 spans) | Partial | 9 recorded `coverage_gaps` |
| L07 | Canonical builder (JSON/JSONL/SQLite FTS5, PDF page index) | Done | |
| L08 | Checked Python/JS runners with manifests; full suite incl. network isolation | Done at 19efd59 | |
| L09 | Legacy and Writer/Reviewer Gemini generators | Done (build) | Live Gemini validation blocked (L26) |
| L10 | Offline exchange export/import staging | Done | |
| L11 | Section 9 module integration | Done | Independent legal validation pending |
| L12 | Supplier intake (PDF/OCR/DOCX/TXT/JSON) | Done (tests) | Visual verification of image candidates is manual |
| L13 | Article 31 routing | Partial | 31(1)/(4) only |
| L14 | Annex II structural audit | Partial | Structure only |
| L15 | Section 3 disclosure | Partial (knowledge only) | Executable engine outstanding (L29) |
| L16 | Readiness prompts (Sections 4, 7, 8) | Partial | Other sections outstanding |
| L17 | REF-11 worksheet and crosswalk | Partial | 17/45 questions linked |
| L18 | Cross-section and multi-product checks | Partial | 12 relationships |
| L19 | Phrase recommendation packs (7/105/38/23) | Partial | Draft candidates only |
| L20 | Evidence-led authoring workspace | Partial | Draft gates. Release workflow outstanding (L35) |
| L21 | Page extraction | Partial | `unverified_layout`. Tables, footnotes and formulas need visual checks |
| L22 | Documentation currency | Partial | README rewritten for the integration branch; older `docs/` notes remain historical |
| L23 | GitHub Actions | Partial | Executing since run 45908436704 (be0524e). Ubuntu jobs pass. Earlier runs had zero steps |
| L24 | Licensed catalogue verification (phrase verifiers, live wording) | **Blocked** | Requires the licensed eSDScom ZIP on the developer machine |
| L25 | ECHA guidance Markdown archive import/cross-check | **Blocked** | `CLP_A_I-main.zip` not available |
| L26 | Live Gemini blind evaluation | **Blocked** | Manual, authorised runs only |
| L27 | Independent legal / competent-person verification | **Blocked** | External reviewer required |
| L28 | Windows execution | Partial | CI at be0524e: 23 errors + 1 failure caused by CRLF checkout breaking the legacy inventory blob pin. Fixed by `.gitattributes` (`eol=lf`) with tests and a local autocrlf simulation. See §10.3 for the CI result |
| L29 | Executable Section 3, Art. 31(3) and Art. 32 | Outstanding | Requires the R9 gate |
| L30 | Post-snapshot amendment reconciliation (REACH and CLP) | Outstanding | See §8.1 |
| L31 | CLP classification engine (Arts. 5–16, Annex I) | Outstanding | Keep separate from disclosure (R10) |
| L32 | CLP Annexes II–VI statements, pictograms, Annex VI entries | Outstanding | |
| L33 | Browser end-to-end tests | Outstanding | Use local Playwright and no network |
| L34 | `coverage.json` validation statuses reflect executed evidence | Done | `executed_validation` block cites `validation/full-19efd596.json`; tested for consistency |
| L35 | Competent-person release record (sign-off, versioned) | Outstanding | No autonomous release (R14) |
| L36 | Role builder refuses output inside the repo | Done | `check_output()` + tests |
| L37 | Legacy single-file KB embeds canonical records | Done | `knowledge_base_markdown()` + tests |
| L38 | Deterministic `coverage_matrix.json` and JSONL generation | Done | Root cause: committed JSONL was written with compact, insertion-order serialisation, while the builder used sorted keys and default separators. Unified under `jsonl()`; byte-reproducibility tests |

---

## 12. Conventions and known pitfalls

- **SQLite:** use `with closing(sqlite3.connect(p)) as db:` for reads and `with closing(...) as db, db:` for writes.
  `with sqlite3.connect()` alone does not close. Leaks fail the checked runner.
- **Fail closed:** a missing catalogue or source, a hash mismatch, a changed wording hash or an unknown input returns an explicit
  error or *unknown/not assessed*, never a silent fallback or substituted wording.
- **Never mutate originals:** source PDFs, catalogue cells, legacy inventories and historical findings are
  immutable. Corrections go in `source_annotations` or `historical_versions`.
- **Outputs outside the repo:** builders, case directories, manifests and packages all go outside the repo. `.gitignore` ignores
  `data/*`, `*.sqlite`, `*.db`, `*.pdf`, `*.zip`, `*.xlsx`, `*.csv`, `*.jsonl`. Tracked JSONL files
  (`regulatory/canonical/requirements.jsonl`, `regulatory/author/references/REACH_RULE_INDEX.jsonl`) need
  `git add -f`. Do not force-add anything else.
- **Encoding and line endings:** UTF-8 everywhere. `.gitattributes` forces LF on every platform, because integrity checks hash committed bytes (the legacy inventory Git-blob pin, canonical exports and the Section 9 copies). Never add CRLF files. Invoke the original package checker with `python -X utf8`.
- **Byte-identical upstream copies:** `modules/section9/*`, `web/section9-rules.js`,
  `regulatory/author/tests/check_package.py`. Do not edit them. Change them upstream and re-pin.
- **Python versions:** CI targets 3.12 and 3.14. Validated locally on 3.13. Avoid syntax newer than 3.10 in `src/`.
- **Documentation drift:** the README now describes the unified integration branch. Per-branch notes in `docs/`,
  `TITLE_IV.md` and early `VALIDATION.md` entries state that tests were not executed, which was accurate when written. The commands in §6 and the
  evidence in §10 are current. Update the old documents rather than deleting their history.
- **Commit messages:** imperative summary of the regulatory or evidence effect, for example "Add canonical
  CLP label … with UFI conditions and version gates". State any blocked or unexecuted checks in the body.
