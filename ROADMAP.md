# Roadmap

1. Restore CI runner scheduling (runs currently execute no steps); execute all suites on Linux and Windows in CI. A complete local Linux checkout has been executed.
2. Exercise positive and negative API routes, browser workflows, offline network isolation, no-catalogue operation and missing optional dependency cases.
3. Done locally at 19efd59 and re-run after the integration fixes: both builders, extraction and the original package checker were executed with the five hash-pinned PDFs. Validate live Gemini independently.
4. Extend partial Article 31/32 and Section 3 decision coverage and CLP calculation/label modules; independently review thresholds, exceptions and dates.
5. Expand assessment beyond structural and selected deterministic checks, verify REF-11 interpretation and document extraction fidelity. Independently review controlled authoring and any future release workflow.

The restored profile rule pack and upstream tests, new optional dependency and HTTP tests, canonical source registry and consolidated package-source preflight require a full regression run. Do not report CI as executed when runner IDs are zero and steps empty.
