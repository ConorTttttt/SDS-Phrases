# Canonical requirement registry — initial increment, 2026-11-26

Base commit: 2d2e7f03aa6b6ab593a08f705ecee82bd00897e8. All five supplied PDF SHA-256 values independently computed in local container and matched the existing source_manifest.json. The legacy Annex II inventory is pinned by Git blob 1bf7a9fdc1984b93ce5122c10000285c992df809; the separate draft inventory's source_sha256 is different and is not accepted as identity evidence. Existing REACH author rule index, CLP statements and REF-11 inventory were inspected and retained as reference data, not promoted automatically to verified obligations.

Visual spot check: REACH PDF ordinals/printed pages 124 and 125, Table 1.1, all 19 hazard-category rows across the page boundary. The repeated column heading is not an obligation. Thresholds are reference values within the classified-mixture lowest-applicable-limit rule, not stand-alone classification triggers. The source text from pages 119–120 was checked for UFI, supplier details, identified uses and emergency contacts. Remaining tables, footnotes, continued paragraphs and the other four documents require full clause-level verification; this commit does not assert exhaustive extraction. PDF text extraction can contain overlapping old/current page headers (REACH) and printed/PDF offsets (labelling guidance).

Official source checks on 2026-11-26:
- https://eur-lex.europa.eu/eli/reg/2020/878/oj/eng — Annex II replacement; application 2021-01-01, transition through 2022-12-31.
- https://eur-lex.europa.eu/eli/reg/2006/1907 — lists post-snapshot amendments 2026/2382, 2026/2501, 2026/2530; scope, dates and individual application remain unresolved.
- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32025R2439 — amendment of CLP revision application dates and transitions; reconcile with supplied CLP consolidation before date-specific execution.
- https://eur-lex.europa.eu/eli/reg/2024/2865 — consolidated amending act includes transition provisions; no blanket date assumption.

All canonical rows remain candidate/manual-only. 53 assessment targets generated, not an independently verified obligation count; 456 legacy rows have no requirement mapping; linked rows also require exhaustive review. Source record order is preserved for historical findings. Stable semantic IDs are separate from content-derived rule-version hashes. Never overwrite historical findings or equate a source record with a legal obligation. Coverage gaps remain explicit in assessment and authoring output. Old Gemini exchanges remain keyed to historical exports; do not silently translate an old approval to a split requirement.

Validation: connector-side checks of inventory count, uniqueness, exact substring wording, and migration targets performed during construction. Local Python execution of repository tests was blocked by unavailable Git networking in the container; committed tests are intended for existing GitHub CI. No Python test pass claimed at commit creation. No independent legal sign-off.

Concurrency: original draft Git commit a280f170f020e3a6475d918a9a5715225628f3bd was not applied because the branch advanced to dfeba79b0a8e48f0dfce63d6d6fab49fd11cdb70. This integration retains the concurrent UTF-8, optional-tool, test-discovery and QA fixes. CSV export handles structured finding metadata. No force push.
