# Regulatory Rule Engine — Stage A (v0.2)

## Scope and safety boundary

This stage introduces a **generic evaluator**, not verified CLP, REACH, HazCom or WHMIS rules. Included rules are exclusively synthetic authoring-workflow demonstrations. No output constitutes a legally required phrase, a compliant SDS section or a regulatory approval.

The eSDScom 5.5 catalogue and rule evaluation remain **separate**. Regulatory legal requirements are **not inferred** from eSDScom structure codes, phrase frequency or section membership. Rule/phrase matching is planned for a later reviewed release.

## Product input contract

\`\`\`json
{
  "jurisdiction": "EU",
  "as_of": "2026-11-08",
  "hazards": ["H315", "H319"],
  "classification_complete": {"value": "yes", "evidence": "Classification independently reviewed"},
  "facts": {
    "skin_contact_possible": {"value": "yes", "evidence": "Verified exposure assessment"}
  },
  "attributes": {
    "physical_form": {"value": "liquid", "evidence": "Approved specification"}
  }
}
\`\`\`

- **Hazards** are externally determined H/EUH codes, **not** chemical classifications calculated here. Missing codes imply exclusion only if an evidenced completeness statement says \`yes\`.
- **Facts** take \`yes\`, \`no\` or \`unknown\`. A missing or unevidenced fact is treated as unknown.
- **Attributes** are text-based properties and have the same evidence gate.
- \`as_of\` is an explicit calendar date. No clock-dependent evaluation default.
- Negative facts, not just positive ones, require supporting evidence.

## Versioned rule contract

Each rule has an immutable ID, jurisdiction, SDS section or subsection, source instrument/reference/document version, inclusive effective-from and optional effective-until date, conditions, review status and intended effect.

Supported condition operators are \`all\`, \`any\`, \`not\`, \`hazard_any\`, \`fact_equals\`, \`attribute_equals\`. These are JSON data, **never executable Python or JavaScript**. Conditions obey three-valued logic:

| Input truth | Meaning |
|---|---|
| yes | Confirmed true |
| no | Confirmed false |
| unknown | Insufficient substantiated evidence |

For \`all\`: any no ⇒ no; otherwise any unknown ⇒ unknown; otherwise yes.
For \`any\`: any yes ⇒ yes; otherwise any unknown ⇒ unknown; otherwise no.
For \`not\`: yes ⇄ no; unknown ⇒ unknown.

## Decision categories

- \`candidate_unverified\`: rule fired but has no independently verified regulatory status. **Never required or applicable.**
- \`information_required\`: unknown condition(s); full missing-data trace.
- \`not_triggered_unverified\`: draft rule did not fire; not a declaration of legal non-applicability.
- \`required\`, \`applicable\`, \`not_applicable\`: reserved for rules with independent review metadata and a non-internal source. The evaluator cannot itself verify the truth of that review; a legal audit is mandatory.
- \`outside_jurisdiction\`, \`outside_effective_dates\`: explicitly scoped skips.

All decisions include the evaluated expression tree, original source identity, missing inputs, matched hazards, applicable date range, rule review status, and \`publishable:false\`. An explicit 16-section coverage grid always reports \`is_sds_complete:false\`.

**Never treat an empty match set, missing source rule, or an expired pack as proof that an SDS is complete or a product is safe.**

## How to use

Run the local server and open \`http://127.0.0.1:8092/regulatory.html\`.

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
python3 src/server.py
\`\`\`

HTTP API:

- \`GET /api/regulatory/pack\` — metadata and non-binding demo rule definitions.
- \`POST /api/regulatory/evaluate\` — evaluate the product object above.
- \`GET /regulatory.html\` — local graphical evaluation workbench.

The new evaluator does not require the eSDScom SQLite catalogue (which remains necessary for the separate phrase library). API requests are stateless; product profiles are not stored or transmitted to third-party services.

## Requirements before upgrading to verified rules

1. Pin authoritative legal text, amendment, date and jurisdiction.
2. Extract each table cell, footnote, exception, choice and conditional rule.
3. Record source locator, reviewer, independent verification evidence and date.
4. Add negative and threshold regression tests, including missing-data and conflicting conditions.
5. Separately verify exact required English wording and phrase selection with the applicable CLP Annex IV Part 1 and Part 2 text.
6. Build coverage to a legally reviewed requirement inventory, not merely the number of rules encoded.

This phase intentionally does not establish legal applicability for any CLP hazard category.
