# Evidence-led SDS authoring workspace (draft implementation)

Launch the existing local server: python src/server.py --db data/catalogue.sqlite
then open http://127.0.0.1:8092/authoring.html. Import and index your own
original catalogue using the existing importer before selecting catalogue phrases.
No original source file or database is altered. The workspace creates separate
phrase_approvals.sqlite and authoring_workspace.sqlite beside the catalogue.
Keep these confidential and back them up locally; do not commit product data.

## Workflow
1. Enter product dossiers and source records (reference, version, locator).
   Each data domain is {"value": ..., "sources": ["source-id"]}; sources must exist.
   Formulation accepts exact mass percentages summing to 100. Do not insert
   approximations to fill confidential or missing concentrations.
   mixture_classification.value uses {"hazards": ["H..."], "complete": true};
   use the same field for a substance's classification. properties.value
   supports physical_state, ph and flash_point_c in addition to other data.
   profile, regulatory_input, readiness and assessment_context accept the existing
   engine-specific records; they are not proof of the facts entered.
2. Revalidate. Every subsection is shown, with a conservative product-level
   evidence inventory, existing rule results, original recommendations, approved
   candidates and gaps. Annex II assessment findings retain their source references.
   Profile engine already includes chemical-family recommendations.
3. Review exact catalogue source using search. Copy the original entry key and
   original wording; the approval database validates the row against the local
   catalogue. An internal adaptation is a separate internal phrase, not an
   eSDScom wording. Internal identifiers start INT-. Conditions map dossier
   domain names to exact evidence-backed values (conservative exact matching).
   Reviewers and rationales are recorded; update existing approval using id and
   expected_version. Rejected or superseded versions cannot be reused.
4. Draft each block with an explicit subsection and product IDs. Use fact,
   proposed, catalogue, internal or legal. Legal wording is checked against
   the repository's English CLP statement register, not generated. Catalogue
   or internal blocks must name current approval ID/version. Approving a block
   does not establish legal adequacy: independent per-product coverage and
   per-finding reviews are required. Draft gaps are deliberately visible.
5. Save revision. Revalidation recomputes all sections on each evaluation/save
   (conservative invalidation rather than minimal dependency tracking).
   Review record uses fingerprint, coverage[product][code] with status PASS,
   reviewer, reason; findings[product][finding-id] with assessment status
   "Compliant against assessed requirement" or "Not applicable", reviewer,
   reason; signoff keys applicable_law, classification, market_language,
   external_obligations, group_coverage, competent_person, each with
   approved:true, reviewer, reason. Any snapshot change invalidates signoff.
   Compare immutable revisions using the history and comparison controls.
6. Export draft JSON, DOCX or PDF. Install python-docx and reportlab locally
   if desired; not required for the core app. All exports carry draft markings.
   The structured JSON export contains the draft document and blockers, not
   the confidential raw formulation; workspace history retains full records.

## Coverage and limitations
Grouping follows SDS_Author's REACH_MULTI_PRODUCT_SDS_COVERAGE.md at
2c6cc785f218b0a1fb6f3f24260cc9b75026be8d (REACH Annex II 1.1, supplied
consolidation p119). Product-scoped blocks are rendered with product IDs in
group drafts. Every member needs evidence and content for every applicable
subsection. No classification-only grouping, inferred N/A or invented phrase
ID. Product-level content and adequacy still require independent review.
Current conservative domain mapping is section-level and does not automate
clause-specific adequacy or scientific evaluation. It deliberately overblocks
some legitimately inapplicable data. Existing assessment and regulatory packs
are incomplete/pilot and their findings are review cues, not legal certification.
English-only headings and legal wording; no verified localization. Exact
percentages only; no ranges or mixture-in-mixture calculation. The UI uses
structured JSON intake rather than complete field-by-field forms. Reviewer
names are local declarations, not authenticated electronic signatures.
Production release is deliberately disabled until validated rule coverage,
independent regulatory verification, source change tracking and authenticated
competent-person authority are implemented. No released export is available.
PDF uses ReportLab default fonts; validate unusual characters before use.
Recheck current legal sources/market requirements independently.
