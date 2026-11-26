# Implementation status — 26 November 2026

Current baseline: integration/offline-eu-gemini after be0524ec. Full execution evidence at 19efd59: validation/full-19efd596.json. Post-fix re-execution is recorded in VALIDATION.md. Earlier baselines remain historical evidence in Git. Implementation is distinct from executed verification and independent legal review.

| Capability | Implementation | Verification |
|---|---|---|
| Catalogue importer/index/browser/reviews, finder | Implemented | Synthetic tests passed at 19efd59; licensed catalogue unavailable |
| Phrase selection and recommendations | Draft candidates | Synthetic tests passed at 19efd59; source verifiers blocked without licensed catalogue |
| Regulatory engine, Article 31 | Partial | 31(3)/32 and comprehensive Section 3 decision logic not established |
| Annex II source browser and structural audit | Implemented indexing and headings | PDF identity verified; extraction fidelity/runtime pending |
| Section 9 | Original applicability heuristic and local Node integration | 11 original upstream-identical Node tests passed |
| Supplier intake | PDF, OCR, DOCX, TXT, JSON | All intake tests incl. PyMuPDF and Tesseract passed at 19efd59 |
| Assessment | Requirement inventory, selected deterministic conflicts, REF-11 worksheet, corrections and reports | Integrated execution and independent regulatory validation pending |
| Evidence-led authoring | Controlled phrase approval/revocation, review gates, revisions, draft JSON/PDF/DOCX export, local endpoints | Unit and HTTP tests passed at 19efd59; browser E2E pending |
| Gemini | Legacy generator and separate writer/reviewer generator; both refuse in-repo output; legacy single file embeds canonical records | Both builds executed with five pinned PDFs; package canonical records equal the registry; live Gemini not validated |
| Gemini exchange | Selective export and staged review import | Two original tests passed at 19efd59 |
| Comprehensive CLP classification and Section 3 engine | Not established as executable | Pending |
| Canonical generated exports | requirements.jsonl and coverage_matrix.json generated deterministically from the registry | Byte-reproducibility and drift tests pass |
| Test execution | Checked Python and Node runners | 200 Python (incl. source-gated, network-isolated) and 11 Node tests passed at 19efd59; GitHub Actions still executes no steps |
| Release | Draft gates only; no autonomous certification | Pending competent-person review |

See regulatory/coverage.json, VALIDATION.md, KNOWN_LIMITATIONS.md and ROADMAP.md. No application-wide runtime or regulatory sign-off is implied.

Restored exact upstream profile rule pack, documentation and original tests from f6e3b90a7264febda1fe989cb9d2c20d0e221cc8; omission previously caused authoring fingerprint evaluation to fail before engines ran. Canonical requirement registry and coverage matrix added by concurrent commits d05412ca and 36219aa2; completeness and runtime still unverified.
