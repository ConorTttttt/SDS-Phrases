# Known limitations

- Supplier intake, requirement-based assessment, REF-11 worksheet, selected cross-section checks, controlled phrase review, revision tracking, draft exports and both Gemini generators exist. They are not evidence of comprehensive regulatory validation.
- No complete CLP classifier, executable comprehensive Section 3 or Article 31(3)/32 engine, or autonomous approved-document release established.
- Licensed eSDScom catalogue and guidance import archive unavailable; no licensed wording bundled or redistributed.
- Consolidated PDFs are snapshots, not authenticated Official Journal law or verified current law. Guidance and REF-11 are nonbinding. Extraction fidelity and legal currentness remain unverified.
- Section 9 is an applicability heuristic, not a physical-property measurement or full calculator UI parity.
- GitHub Actions now executes the workflow (from run 45908436704 at be0524e). Ubuntu jobs passed, including the loopback-only Python run. Windows Python suites failed because a CRLF checkout invalidated the Git-blob pin of the legacy Annex II inventory. `.gitattributes` now forces LF; see VALIDATION.md for the confirming run. Full local execution at 19efd59 is in validation/full-19efd596.json, and post-fix runs are in VALIDATION.md. Browser E2E, live licensed-catalogue verification and live Gemini evaluation remain unexecuted. Software test results are not legal or regulatory validation.
- Missing document-processing tools affect their own formats/features. See DEPENDENCIES.md. No live Gemini output has been validated. Package canonical records are checked against the offline registry, but Gemini's use of them is not.
