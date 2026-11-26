# Implementation status — 26 November 2026
Baseline: c9da6bb2abf47d9e6bc337f28f17030034bff5d5 on integration/offline-eu-gemini. All ten SDS-Phrases feature tips are ancestors (compare behind_by=0). Main baseline f2dd4a4524b6e4bb9ac1be83676b29aff6999790. EU_SDS 3e4272df30979d3793f77ecefe511c425ae30629 rules and tests have identical Git blob IDs to inherited copies. SDS_Author pinned ba0014655372a56c855b46b85fb6fd0f002d09c0; missing v4 references and static checker restored. Separate writer/reviewer packages identified but not integrated. Korean toolkit 60d378dc98f384d9ac9e1fbde965bb04ebecdb05 is design reference only.

| Capability | Implementation | Verification |
|---|---|---|
| Catalogue importer/index/browser/reviews, finder | Implemented | Runtime pending; licensed catalogue unavailable |
| Phrase selection, section/profile/family suggestions | Partial/draft | Runtime pending |
| Demo regulatory engine | Partial | Unverified rule pack |
| ECHA/REACH local source browser | Implemented indexing | Full REACH page markers checked; runtime pending |
| Article 31 CLI | Partial | Runtime pending; 31(3)/32 absent |
| Annex II heading audit | Implemented structural only | Runtime pending |
| Section 9 | Partial | Original rules/tests identical by Git blob; runtime pending |
| Gemini generator | Implemented manual export | Runtime pending; no Gemini execution |
| CLP calculation, ingredient disclosure, REF-11 automation | Not implemented executable; some knowledge only | Unverified |
| PDF SDS intake, exchange import, release workflow | Not implemented | Not tested |

See regulatory/coverage.json, VALIDATION.md, KNOWN_LIMITATIONS.md and ROADMAP.md. Implementation does not mean verified compliance.
