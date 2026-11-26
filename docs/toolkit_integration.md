# Offline EU SDS toolkit + Gemini integration — initial partial release
Based on the descendant feature/chemical-family-phrase-recommendations commit. The original main branch remains unchanged. The catalogue/importer, browser, regulatory evaluator, structural audit, evidence prompts and phrase finder are retained. Section 9 is integrated using the pinned original module with an explicit-input guard. Source identity is recorded in regulatory/upstream.json.

## Run offline
From the repo root:
```sh
python3 -m unittest discover -s tests -v
node --test modules/section9/tests/*.test.mjs
python3 src/server.py
```
Open http://127.0.0.1:8092/ and use the integrated Section 9 link or existing workbenches. Install your locally licensed eSDScom catalogue using the existing README instructions. Keep service loopback-only. Do not commit confidential data.

## Build Gemini reference package
Put the five original PDFs in a local directory (exact names in regulatory/source_manifest.json). Run:
```sh
python3 scripts/build_gemini_package.py --sources /path/to/pdfs --out /path/outside/repo/gemini-package
```
Add --extract only if local Poppler pdftotext is installed. Page-located extraction is not independently verified for tables or formulas. Hashes identify snapshots, not current law. Builder never contacts an AI service. It deliberately excludes licensed phrase catalogue and product data. Copy GEMINI_SYSTEM_PROMPT.md into your Gemini instructions and manually attach the generated knowledge base and selected reference files as permitted by organisation policy. This is not an executable Gemini plugin.

## Coverage and limitations
regulatory/coverage.json records incomplete coverage. Full CLP calculation and Annex VI extraction, executable ingredient disclosure and Article 31/32 checks, REF-11 automation, complete authoring/approval, PDF/OCR intake and Gemini findings import are not implemented by this integration slice. Only selected SDS_Author references are copied; remaining playbooks and test specifications must be migrated. Source PDFs are supplied locally at build time; no binary files or catalogue uploaded. Tests have not been executed or confirmed here. Independent legal validation, Windows, browser and Gemini runtime tests remain outstanding.
