# CLP canonical label and PCN component

Scope: selected Articles 4, 17–22, 24–29 and Annex VIII Parts A/B. 73 manual assessment targets, 85 source records, one reference-only Table 4. The wording is transcribed from the supplied CLP consolidation; no comprehensive CLP compliance claim.

The component is consumed by the common Python registry, SQLite/JSON/JSONL exports, assessment, authoring revision fingerprint and both Gemini roles. Keep label and notification obligations distinct from REACH SDS content; an SDS is not evidence of PCN receipt, packaging conformity or applicable Member State exemptions. UFI location is conditional, not universally mandatory in SDS 1.1. Part A 5.3 permits multiple placement routes; Part B 1.3 requires 24/7 contact for limited submissions, not every SDS emergency number.

Source integrity and text-span check: run from repo root:
```sh
PYTHONPATH=src python -c "import canonical_requirements as c; print(c.verify_clp_pdf(c.load_clp(), '/path/to/CELEX_02008R1272-20260701_EN_TXT.pdf'))"
```
The verifier only checks identity and normalized text matching; soft hyphenation, inline amendment markers and cross-page text may require reconciliation. No source wording is silently corrected. See coverage gaps in clp.json. No rule is promoted to executable solely on a text match.

Official version dependencies (checked 2026-11-26): EUR-Lex lists 1 July 2026 as the consolidated version (https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32008R1272). Apply original and amended legal acts separately: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32025R2439 and https://eur-lex.europa.eu/eli/reg/2024/2865. Regulation 2026/2382 Article 2 replaces CLP Article 1(4) on defence exemptions (https://eur-lex.europa.eu/eli/reg/2026/2382/oj); Article 1 also changes REACH Article 2(3). Scope must not be determined from the old snapshot alone. Later Annex VIII dutyholder amendments and operative dates must be reconciled before any deterministic conclusion.

R2: 85/85 source spans matched normalized local extraction using dual fingerprints; six corrected records archived. Table 4 visually checked on page 1573. Still candidate/manual only.
