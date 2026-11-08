# Phrase recommendations across all 16 SDS sections

## Goal and scope

This is the first **evidence-gated authoring** capability layered on top of the
local eSDScom 5.5 catalogue. It is *not* a mandatory phrase selection engine,
an SDS compliance assessor or a substitute for product-specific authoring.
The rules are independently readable and fail closed if source wording changes.

A REACH Annex II subsection is a **content requirement**, not a licence to
automatically insert a catalogue phrase. For example:
- Annex II Part A 4.1 expects appropriate first aid by exposure route; the
  selected text must also address medical attention and special cases.
- Annex II Part A 7.2 requires storage content consistent with product
  properties; do not suggest tightly closed storage for a product needing vents.
- Annex II Part A 8.2 requires suitably specific PPE. A generic glove
  sentence cannot replace material, thickness, breakthrough and standard data.
- Annex II Part A 14 needs transport mode-specific classification; a CLP
  result does *not* prove a product is not dangerous goods.
- Annex II Part A 11 and 12 remain information obligations even where
  mixture-level test data are unavailable.

## Curation and provenance

The non-executable curated authoring pack at
\`rules/section_phrase_candidates_v0.1.json\` identifies 21 first-pass
**context-dependent** source candidates across all 16 sections. Each rule
has a stable ID, a section, original eSDScom Core structure code, **SHA-256 of
the exact English source wording**, a three-valued condition, a regulatory
*topic* locator, and explicit warnings. It contains no eSDScom wording.

The local SQLite catalogue supplies the **original unmodified English phrase**
only when all of these match: Core collection, exact structurecode, **unique
source record**, catalogue version 5.5, expected SDS section and exact
SHA-256 of the English wording. A mismatch blocks the suggestion rather than
silently using a similar text. Core workbook official phrase IDs may be empty;
the UI preserves this fact.

The curated rules are versioned independently of both the original phrase
catalogue and future legal rules. None is labelled legally verified.
Known product facts (yes/no), product type and hazards require documented
evidence. Unknown evidence is **not** presumed negative.

The first curated choices are illustrative and deliberately incomplete.
Some source phrases are only **list fragments** and must be embedded in a
properly structured SDS table rather than pasted as complete sentences.
Many necessary SDS passages must be authored from underlying measurements,
supplier identity, full classification, constituent data and national
requirements. This prototype does not automatically generate them.

## Application

In your checkout:

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
git fetch origin
git switch --track origin/feature/phase2-section-phrase-recommendations
# If the catalogue is missing, import your original eSDScom ZIP:
python3 src/import_catalogue.py ~/Downloads/eSDScom_V5-5_20231131.zip
# Check exact catalogue codes and English wording hash for all curated candidates:
python3 scripts/verify_section_phrase_sources.py
# Run tests / application:
python3 -m unittest discover -s tests -v
python3 src/server.py --port 8093
\`\`\`

Open **http://127.0.0.1:8093/section_recommendations.html**. Port 8093 avoids
interfering with an older SDS engine already running on 8092.

Use **Load fictional test profile** for an H315/H319 example that produces
several illustrative candidate matches. The example has fictional evidence
and must not be used for an actual chemical product.

In the interface:
- Product jurisdiction and date, hazards, independent classification evidence
  and substance/mixture type are separate from the 22 conditional facts.
- For each fact, select Yes, No or Unknown and provide its actual source
  assessment. Blank evidence means Unknown in the engine.
- Evaluate produces **all 16 sections**, including zero-suggestion sections,
  with draft wording, blocked candidates, missing evidence and a trace.
- Each section links to the full phrase library with a section filter.
- Exact original text can be copied for later review, but doing so is not
  approval or a regulatory requirement.
- No product profile is saved or transmitted to an external service.

## API

- \`GET /api/section-recommendations/config\` — curated candidate pack,
  condition data and all section headings. No catalogue wording.
- \`POST /api/section-recommendations/evaluate\` — product input in the same
  evidence-aware shape as Phase 2 Stage A; returns section-grouped decisions.
- \`scripts/verify_section_phrase_sources.py\` — local integrity check for all
  21 curated source mappings, independent of product facts.

The input follows the Phase 2 product contract. Example fragment:

\`\`\`json
{
  "jurisdiction": "EU",
  "as_of": "2026-11-08",
  "hazards": ["H315", "H319"],
  "classification_complete": {
    "value": "yes", "evidence": "Approved test classification reference"
  },
  "attributes": {
    "product_type": {"value": "mixture", "evidence": "Approved identity reference"}
  },
  "facts": {
    "soap_water_skin_first_aid_assessed": {
      "value": "yes", "evidence": "Product-specific first-aid review"
    }
  }
}
\`\`\`

**Outcomes:**
- \`draft_candidate\`: documented condition met and exact source matched.
- \`evidence_required\`: missing/unknown/unevidenced condition; no phrase.
- \`not_triggered\`: condition false on evaluated evidence.
- \`blocked_catalogue_mismatch\`: missing, changed, duplicate, incompatible
  catalogue or missing local database.
- \`blocked_conflicting_evidence\`: contradictory data, currently the
  mutually exclusive Section 15 CSA claims.
- \`outside_jurisdiction\`: EU pilot rules do not apply to GB/US.

All outcomes have \`approved_for_sds: false\` and
\`legally_required: false\`. At the response level \`sds_compliant: false\`.
An assessment date is retained for traceability but **legal effective-date
applicability has not been verified**; \`date_applicability_reviewed: false\`.

## Subsequent work before compliance automation

1. Source-by-source review of all eSDScom drafting candidates, usage notes
   and licenses, particularly first aid, waste and transport.
2. Complete coverage of each REACH Annex II subsection as separately verified
   information requirements rather than a count of available phrases.
3. Integrate official CLP Annex IV Part 1 selection criteria and Part 2 exact
   English wording, verified per hazard class and category.
4. Add field-specific validators, ingredient 3.2 calculations and Section 9
   physical properties, Section 14 modal DG determinations, current OELs,
   national rules and transport caveats.
5. Add review workflow, authorisations and versioned rationale recording.
6. Add jurisdiction-specific GB, US, CA and NZ sources and independently
   versioned evidence rules.

**Copyright/source handling:** The local eSDScom phrase catalogue is not
committed to GitHub. The source is eSDScom 5.5 and remains subject to its
stated licensing conditions. The curated pack contains identifiers and
wording fingerprints, not the source English phrases themselves.
