# REACH Annex II — EU SDS rule-source integration (Phase 2)

## Exact scope of uploaded PDF

- File: \`Full REACH_removed.pdf\`; **36 pages**.
- Scope: **REACH Annex II only**, extracted from a larger consolidated Regulation (EC) 1907/2006. It does **not** contain Article 31 or the rest of REACH.
- Visual edition: 22 June 2026 / **069.001** / pages 117–152.
- Official consolidated reference:
  https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX%3A02006R1907-20260622
- Uploaded PDF SHA-256: \`3e6304eb92c7ffb0b82fc7d634ac825f0bc8849195c81ac5d7efa4b16ead66fb\`
- The PDF appears to have been reprocessed, and retains **old 11 May 2026 / 068.001 page headers in its extractable text** in addition to the visually rendered June 2026 / 069.001 headers. Do **not** use an extracted header as a legal version or effective date without independent checking.
- **EUR-Lex consolidated texts are documentation tools**, not the legally authentic Official Journal enactments. This local PDF/structural transcription is a source reference; it does not constitute independent legal verification of obligations or amendments.

## What is now encoded

### Part B structure

\`rules/eu_reach_annex2_partb_2026.json\` contains all **16 SDS section headings and 51 subsection headings**, with reported source page labels.

The Part B exception for Section 3 is modelled explicitly: **only 3.1 for substances or 3.2 for mixtures, as appropriate**. Product type requires evidence. Part A 0.4 additionally says SDSs must not contain blank subsections: a heading may be present even if its content is insufficient.

\`src/reach_annex2_audit.py\` takes a **reported heading inventory**, not a finished SDS. It returns \`reported_present\`, \`reported_missing\`, \`information_required\`, \`product_type_required\`, \`not_expected_for_product_type\`, \`unexpected_heading_present\` and \`reported_blank\`. Missing entries cannot be called missing unless a complete inventory with evidence is explicitly supplied. A visible heading does not establish a sufficiently completed SDS subsection. All outputs have \`sds_compliant: false\`.

The 16-section and 51-subsection structure does **not** replace more detailed requirements of Part A, Article 31, CLP and national rules.

### Part A *review* inventory

\`rules/eu_reach_annex2_content_inventory_draft.json\` contains **28 non-executable draft entries**, referencing clauses, printed pages, relevant evidence and critical nuances. It is deliberately **not exhaustive**, verified, approved, or used for required/optional compliance decisions. Priority complex areas include:

- Section 3.2.1 and 3.2.2: ingredient disclosure depends on mixture classification, gas/non-gas status, multiple alternative concentration criteria, SCLs, M-factors, sensitisation and other flags. **Table 1.1 is not a universal single threshold.**
- Section 1.1: UFI placement under specific circumstances.
- Sections 4 and 7: product-specific first aid, relevant exposure routes, safe storage and incompatible materials.
- Section 8: national occupational exposure limits, PPE material/thickness/breakthrough.
- Section 9: physical state-specific exceptions, unavailable data and not-applicable reasons.
- Section 14.7: maritime bulk rules apply only in qualifying cases.

Keep each legal requirement separate from the eSDScom phrase wording library. CLP Annex IV Part 1 and Part 2 remain separate legal selection/wording tasks.

## Source PDF import

The original PDF and full extracted text are **not committed**. Place the PDF at \`~/Downloads/Full REACH_removed.pdf\` and run:

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
python3 src/reach_annex2_source.py ~/Downloads/'Full REACH_removed.pdf'
python3 src/server.py
\`\`\`

Requires \`pdftotext\` from \`poppler-utils\` (Ubuntu \`sudo apt install poppler-utils\` if absent). The local file \`data/reach_annex2_2026.sqlite\` preserves the full extracted text of each page, page digest, 36 PDF page numbers, printed page numbers, PDF source digest and extraction warnings. It is excluded from Git.

Open \`http://127.0.0.1:8092/reach.html\`. The structure checker and draft inventory are available even without the source SQLite file. Only the original-PDF text search requires import.

Endpoints:
- \`GET /api/reach/structure\`
- \`GET /api/reach/content-inventory\`
- \`POST /api/reach/audit\`
- \`GET /api/reach/source/summary\`
- \`GET /api/reach/source/search?query=...&page=...&limit=12\`

Sample audit request:

\`\`\`json
{
  "jurisdiction": "EU",
  "as_of": "2026-11-08",
  "product_type": {"value":"mixture","evidence":"Approved formulation register"},
  "inventory_complete": {"value":"yes","evidence":"Complete headings exported from draft SDS"},
  "headings": ["1","1.1","2","2.1","3","3.2","4","4.1"],
  "blank_subsections": []
}
\`\`\`

This deliberately reports many missing structural headings; it **does not** determine content sufficiency or overall compliance.

## Verification still required before automation

1. Independently compare all 36 pages against official EUR-Lex text and primary Official Journal enactments, not just sampled page layouts. Resolve the layered header problem formally.
2. Confirm consolidated edition/effective-date scope and transitional provisions for the intended SDS market date.
3. Extract the **complete** Part A clause hierarchy with parent-child scope, conditions, footnotes, joined tables, exceptions, optional and required statements.
4. Verify the 28 candidate records against primary sources with an independent audit and negative/boundary tests.
5. Build condition operators and product data inputs for actual content rules, including concentration thresholds, exposure context and Member State requirements.
6. Add review workflow with named approver, source version, exceptions and evidence, then link requirements to verified eSDScom phrase candidates without silently altering wording.

**Important:** This workbench is an evidence and structural review tool, not a legally verified SDS generator.
