# v0.6 — Chemical-family phrase recommendations

## Direct user workflow

Open **\`/profile_recommendations.html\`** in the local SDS-Phrases app.
Enter the product's **existing hazard classification**, physical properties,
and optionally tick **one or more chemical families**. Select
**Get recommended SDS phrases**.

The engine returns literal, unmodified English **eSDScom 5.5 Core**
phrase candidates grouped by SDS section. Each shows:

- The original catalogue wording (only if its unique source code, version,
  section, grammar and SHA-256 match the locally imported source).
- Why it was retrieved, including **the user-declared chemical family**.
- Any **H/EUH code prerequisite** for that family-related phrase.
- Any other process-condition gate, such as confirmation that water dilution
  was assessed for the exact product.
- The remaining **compatibility, exposure or legal label checks**.
- The original source metadata and an **Add to draft** action, using the
  existing local phrase-finder board.

This expands the prior **38 profile-driven mappings** with **23 manually
curated chemical-family mappings** spanning **10 family groups**. Some
source codes support more than one family and are not shown twice. The
new sidecar source pack holds references and exact original English
wording fingerprints, **not** any eSDScom wording.

## Initial family groups

| Family ID | User-visible family |
|---|---|
| \`acids\` | Acids and acidic formulations |
| \`alkalis\` | Alkalis and alkaline formulations |
| \`organic_solvents\` | Organic-solvent-containing products |
| \`isocyanates\` | Isocyanate-containing products |
| \`epoxy_resins\` | Epoxy-resin-containing products |
| \`oxidising_substances\` | Oxidising substances or mixtures |
| \`organic_peroxides\` | Organic peroxides |
| \`water_reactive_substances\` | Water-reactive substances |
| \`metal_powders\` | Metal powders and metallic dusts |
| \`acid_reactive_gas_releasers\` | Acid-reactive toxic-gas releasers |

This is a deliberately limited first-pass taxonomy, **not an exhaustive
chemical ontology**. More precise families (e.g. organic vs inorganic
acids, hydrofluoric acid, particular diisocyanates or epoxy hardeners)
need their own reviewed source rules and product-identity data.

### What the family tag does and does not do

A selected family **adds catalogue-source discovery cues**. It does **not**:

- Prove that a product or constituent actually belongs to the family,
  or determine concentration, physical form or chemical structure.
- Calculate a CLP hazard or establish the relevant hazard statement.
- Prove the need for specific eye/skin/respiratory PPE, firefighting media,
  extinguishing procedures, medical advice or storage incompatibilities.
- Determine if EUH204/EUH205 supplemental statements meet the **actual CLP
  Annex II conditions** or if an EUH031/EUH032 statement is applicable.
- Establish that any source list fragment is a complete SDS sentence.
- Make a mandatory or legally approved phrase selection.

For that reason, **the result is always an unreviewed draft candidate**,
never \`approved_for_sds:true\` or \`sds_compliant:true\`.

## Stronger safeguards

The source catalogue includes many references to acids, alkalis, oxidising
materials and amines that are embedded in **lists of incompatible materials**.
These were **not** automatically turned into product recommendations by
keyword search. Only manually reviewed, source-code-specific entries are
included in the family pack.

Several more sensitive family entries require **additional evidence**:

- **Water-reactive:** handling/cleanup candidates require **H260 or H261**
  in the entered hazard classification. This is not a new classification
  calculation; it is a relevance prerequisite.
- **Oxidising materials:** a general heat/ignition precaution appears only
  if **H270, H271 or H272** was already entered, with product-specific
  stability review still required.
- **Organic peroxides:** a heat/ignition precaution is gated by
  **H240, H241 or H242** and an actual organic peroxide family selection.
- **Acid-reactive toxic-gas releasers:** EUH031 and EUH032 wording is
  gated by the respective **existing EUH code**.
- **Metal powders:** dust-control candidates need a **solid** product
  plus documented powder form or dust-generation potential.
- **Acid dilution:** dilution-with-water wording requires the user to
  affirm separately that this particular dilution process has been
  assessed as compatible; it is not suggested solely because the
  family is an acid. A water-reactive family conflicts with the
  affirmative dilution assessment until reconciled.
- **Isocyanates and epoxy resins:** family selection surfaces potential
  EUH204/EUH205 phrase wording for **legal review only**; this is not
  a determination that the supplemental phrase is legally required.

No rule uses an absent H-code to infer a non-hazardous, non-DG, non-reactive
or otherwise negative condition.

## Technical architecture

- \`rules/eu_chemical_family_phrase_cues_v01.json\`: 10 family tags and
  23 SHA-pinned source-code mappings. All have review notes and no legal
  approval.
- \`src/chemical_families.py\`: pack schema guard, allowed family
  validation, H/EUH/property/process prerequisites, exact local source
  identity and quality flag checks, family provenance.
- \`src/profile_phrase_engine.py\`: accepts
  \`chemical_families: ["acids","organic_solvents"]\` and
  \`family_assessments: {"water_dilution_approved":"unknown"}\`;
  combines family candidates with existing 38 profile mappings,
  avoids duplicate verified source wording and still returns all 16
  SDS sections.
- \`GET /api/profile-recommendations/families\`: read-only family names,
  descriptions and process assessment choices (no licensed text).
- \`POST /api/profile-recommendations/evaluate\`: the existing
  recommendation API with optional family inputs.
- \`web/profile_recommendations.html\` + JS/CSS: family multi-select and
  guidance for family-specific candidate review.
- \`scripts/verify_family_phrase_sources.py\`: checks all mapped source
  fingerprints against the user's original local indexed eSDScom database.
  Only names, IDs, counts and errors are printed; it never redistributes
  licensed English phrase wording.

### Example API input

\`\`\`json
{
  "jurisdiction": "EU",
  "as_of": "2026-11-08",
  "hazards": ["H315", "H319"],
  "product_type": "mixture",
  "physical_state": "liquid",
  "colour": "colourless",
  "ph": 5.2,
  "chemical_families": ["organic_solvents", "isocyanates"],
  "family_assessments": {"water_dilution_approved": "unknown"}
}
\`\`\`

All family tags and classification/property data in this example are
**fictional**. No particular phrase follows automatically as a legal
requirement. Exact returned wording depends on the original locally
licensed eSDScom file.

## Test on Ubuntu

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
git fetch origin
git switch --track origin/feature/chemical-family-phrase-recommendations
python3 scripts/run_tests_checked.py
python3 scripts/verify_family_phrase_sources.py
python3 src/server.py --port 8098
\`\`\`

Open: **http://127.0.0.1:8098/profile_recommendations.html**.

If the browser reports that the local phrase index is missing:

\`\`\`bash
python3 src/catalogue_index.py data/catalogue.sqlite
\`\`\`

The source ZIP, complete English phrases and local database remain
on the desktop. None has been committed to GitHub.

## What to develop next

We should next introduce composition-backed family matching (CAS/EC
identifiers, constituent weight percentages, actual isocyanate/epoxy
components), chemical subfamily distinctions, concentration-specific
conditions and primary-law verification of each EUH statement. That would
support genuinely product-specific phrase selection rather than
family-associated discovery alone.
