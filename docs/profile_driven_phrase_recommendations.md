# v0.5 — Hazard classification + physical properties → original SDS phrases

## Purpose

This product-first feature lets the SDS author enter **existing classified
H-statement codes and physical properties once**. It returns the exact local
**English eSDScom Core 5.5 wording** grouped by SDS section. The 38
source-reference-only mappings draw on the existing 105 curated candidate
records. These are **review candidates**, not binding phrases or automatic
regulatory decisions. No original licensed wording is committed.

## What to enter

EU source jurisdiction, SDS assessment date, existing classified H-codes,
substance/mixture identity, physical state, form, colour, dust generation,
volatility, heat/sunlight sensitivity, pressure on heating, professional use,
and optional measured pH and flash point in °C. Quick-add buttons provide
common H-code/category pairings. The engine does **not** calculate a CLP
classification from this information.

The engine displays **all 16 sections** and reports matching original
wording, explanation and matched inputs, source provenance, text integrity
checks and important product-specific confirmations. Mapped profile rules
currently span **Sections 1–10**. For Sections 11–16 the engine does not
infer unsafe negative or technical statements solely from hazard and physical
data. Open the full local phrase finder for those sections and complete
product-specific analysis independently.

Suggested wording must uniquely match the Core 5.5 source code, EU structure,
SDS section, exact original English SHA-256 and grammar. Quality-flagged,
duplicate, absent or changed source rows are blocked rather than replaced
with invented or approximate text.

The user can deliberately add candidates to the **existing browser-local
draft** at \`sds_phrase_finder_draft_v1\`. The full phrase finder at
\`/phrase_finder.html\` allows reviewing, copying and exporting the draft
and checks that saved source digests are unchanged before export.

## Example — fictional mixture

\`\`\`json
{
  "jurisdiction": "EU",
  "as_of": "2026-11-08",
  "hazards": ["H315", "H319"],
  "product_type": "mixture",
  "physical_state": "liquid",
  "colour": "colourless",
  "ph": 5.2,
  "flash_point_c": null
}
\`\`\`

The selected source pack may offer candidates in Section 2 (H315/H319
wording), Section 3 (mixture table *headings only*), Section 4
(skin/eye first-aid *subject to medical review*), Section 8 (PPE
*subject to an exposure and equipment assessment*) and Section 9
(liquid/colourless *list fragments*). It does not establish
that any section is adequate or that the phrases must be used.

## Regulatory safeguards

- **pH outside 2–11.5** and **liquid flash point below 60 °C** are only
  broad **search/relevance screening cues**. They are not the legally
  operative CLP/GHS hazard classification algorithms or cutoffs.
- An H-code appearing in input is not independently checked for correct
  hazard class/category or intended market.
- The engine blocks all profile-derived recommendations if the entered
  state contradicts gas/liquid/solid flammability codes, powder is recorded
  for a non-solid, or both H318 and H319 are present. Such cases require
  assessment rather than silently choosing one interpretation.
- Missing hazards do **not** establish absence of hazards, no classification,
  no mixture testing, "not dangerous goods" or "CSA not performed".
- A first-aid, PPE, firefighting, spill or storage candidate requires
  **product-specific** validation. H315 does not prove soap-and-water
  treatment is adequate. H319 does not by itself establish complete medical
  instructions. H225 does not prove any particular extinguishing medium is
  suitable or that a specific respirator is required.
- CLP Annex IV Part 1/2 selection and correct current English legal
  wording require independent legal verification, not just eSDScom matching.
- No source phrase is automatically copied to an approved SDS.
- All response objects explicitly mark regulatory applicability, completed
  SDS sections and authoring approval as **false**.

## API

\`POST /api/profile-recommendations/evaluate\`

Returns all 16 sections with candidate phrases, source identifiers/digests,
original version, matched profile fields, review conditions and conflict
notices. On missing local catalogue, returns a 503 error if a source match
is needed. On contradictory profile information, returns a blocked result
without inventing wording. Inputs are validated and limited.

## Run locally

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
git fetch origin
git switch --track origin/feature/profile-driven-section-phrase-engine
python3 scripts/run_tests_checked.py
python3 src/server.py --port 8097
\`\`\`

Open **http://127.0.0.1:8097/profile_recommendations.html**.

Your imported original licensed \`data/catalogue.sqlite\` must exist and
include its browsing index. If missing, restore your eSDScom Core 5.5
import and run \`python3 src/catalogue_index.py data/catalogue.sqlite\`
to rebuild the index. The original ZIP/database are not included in GitHub.

## Future development

Add verified product/ingredient information for Sections 3, 8, 11 and 12;
verified waste decisions for Section 13; and independent modal dangerous
goods classification for Section 14. This requires more product data than
H-codes and physical properties alone.
