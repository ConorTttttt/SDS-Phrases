# Implementation status — 26 November 2026

Inspected remote baseline: 2d2e7f03aa6b6ab593a08f705ecee82bd00897e8. The prior baseline remains historical evidence in Git. Implementation is distinct from executed verification and independent legal review.

| Capability | Implementation | Verification |
|---|---|---|
| Catalogue importer/index/browser/reviews, finder | Implemented | Licensed catalogue unavailable; runtime pending |
| Phrase selection and recommendations | Draft candidates | Runtime pending |
| Regulatory engine, Article 31 | Partial | 31(3)/32 and comprehensive Section 3 decision logic not established |
| Annex II source browser and structural audit | Implemented indexing and headings | PDF identity verified; extraction fidelity/runtime pending |
| Section 9 | Original applicability heuristic and local Node integration | 11 original upstream-identical Node tests passed |
| Supplier intake | PDF, OCR, DOCX, TXT, JSON | Five isolated format tests and two missing-dependency checks passed at 36219aa2 |
| Assessment | Requirement inventory, selected deterministic conflicts, REF-11 worksheet, corrections and reports | Integrated execution and independent regulatory validation pending |
| Evidence-led authoring | Controlled phrase approval/revocation, review gates, revisions, draft JSON/PDF/DOCX export, local endpoints | Implementation and tests present; integrated execution pending |
| Gemini | Legacy generator and separate writer/reviewer generator | Build execution pending |
| Gemini exchange | Selective export and staged review import | Two original tests passed again at 36219aa2 |
| Comprehensive CLP classification and Section 3 engine | Not established as executable | Pending |
| Release | Draft gates only; no autonomous certification | Pending competent-person review |

See regulatory/coverage.json, VALIDATION.md, KNOWN_LIMITATIONS.md and ROADMAP.md. No application-wide runtime or regulatory sign-off is implied.

Restored exact upstream profile rule pack, documentation and original tests from f6e3b90a7264febda1fe989cb9d2c20d0e221cc8; omission previously caused authoring fingerprint evaluation to fail before engines ran. Canonical requirement registry and coverage matrix added by concurrent commits d05412ca and 36219aa2; completeness and runtime still unverified.
