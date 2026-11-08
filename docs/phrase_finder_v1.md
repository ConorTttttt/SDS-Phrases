# v0.4 — Get actual SDS phrases from your local eSDScom catalogue

## Purpose

The original 105 evidence-triggered authoring candidates were useful but
made a user confirm many facts *before* any source wording was visible.
The **Phrase Finder** reverses that interaction: browse real source phrases,
filter by SDS section/subsection/text, place them into a shortlist, and
evaluate suitability with competent-person review later.

**This is genuine original-source retrieval**, NOT generated text, rewriting,
translation, statutory P-statement mapping or a completed SDS.

## How it works

- Web page: \`/phrase_finder.html\`.
- **105 curated source paths** (EU only): the original source structure codes,
  exact English wording SHA-256 and original Core catalogue version/grammar
  are checked against locally imported eSDScom 5.5.
- **Full Core catalogue mode**: every original eSDScom Core entry can be
  explored by section, subsection, language-specific source structure,
  keyword, original structure code and grammar. This is broader than the 105
  examples and allows candidates to be discovered without adding new
  hard-coded rules to the repository.
- 16 SDS sections and contextual subsection pickers, with original source
  counts and curated-code counts. **Subsection mappings in full catalogue mode
  are derived from original structure-code patterns; not legally validated
  mappings.** Curated older records with an explicit Part A context use
  that recorded context when available.
- Default filters hide records with source quality flags. Users can opt in
  to see them; snippets with placeholders and table fragments have explicit
  caution messages and a confirm-to-add step.
- Original English text, source file, row, structure code, source grammar,
  catalogue revision and wording hashes are supplied from the **local** SQLite
  database. No eSDScom wording is committed to GitHub.
- Search is exact-term matching (all words required), not AI relevance or a
  legal applicability/risk score. Results are ordered by textual match,
  source flags, grammar and original source row.
- Draft board lets users add up to 200 phrases, remove any phrase, and copy or
  export the selected **unreviewed** original source wording grouped by
  section. This is NOT export of a completed SDS.
- Draft board is saved in this browser's \`localStorage\`. It is not sent to
  GitHub, stored in the server database or synced between devices. Opening
  the site on another browser/profile does not share the draft.
- Before copy/export, the browser calls a read-only source check comparing
  saved entry key, catalogue version, section, original code, full catalogue
  metadata digest and independently computed SHA-256 of original English text
  against the latest local SQLite catalogue. A changed or missing source row
  blocks export until reselected. Source identity verification is **not**
  legal suitability review.

## Run locally

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
git fetch origin
git switch --track origin/feature/phrase-finder-all-catalogue-v1
python3 scripts/run_tests_checked.py
python3 src/server.py --port 8096
\`\`\`

Open \`http://127.0.0.1:8096/phrase_finder.html\`.

The app expects your existing imported original licensed eSDScom database:

\`data/catalogue.sqlite\`

If missing, import it once using the original archive:

\`\`\`bash
python3 src/import_catalogue.py ~/Downloads/eSDScom_V5-5_20231131.zip
\`\`\`

If an index is missing, rebuild it without changing the original catalogue
rows: \`python3 src/catalogue_index.py data/catalogue.sqlite\`.

Try Section **4** and curated mode to browse example first-aid phrases. Then
switch to **Entire local Core phrase library** and search for \`eye\`, \`wash\`,
\`water\`, or a source structure code.

## API contracts

\`GET /api/phrase-finder/sections\`

Returns section metadata, catalogue count, curated count and subsection
labels. Counts are local English Core rows only and do not certify coverage.

\`GET /api/phrase-finder/search?jurisdiction=EU&section=4&subsection=4.1&query=eye&mode=catalogue&kind=ALL&include_flagged=0&limit=30&offset=0\`

Returns exact original catalogue entries, original metadata and caution
flags. The \`curated\` mode checks the selected 105-rule source mapping but
does not require any product data and does not assert the proposed phrase
is suitable for a given formulation. The \`catalogue\` mode retrieves all
Core entries in the selected source jurisdiction structure, including non-EU
source structures where available; those are **catalogue collections**, not
a determination that the phrase complies with national regulations.

\`POST /api/phrase-finder/validate-draft\`

Accepts an array of at most 200 source snapshots (entry key, original source
code, section, catalogue version, full index wording hash and independent
English text SHA-256), returning source unchanged or changed/missing for
each. No source text leaves the local system except at the user's explicit
copy/export action.

## Legal and product safety limits

- An exact source-code/wording match is **not evidence** that a phrase should
  appear in a specific product's SDS.
- Some source phrases are mutually incompatible (e.g. classified/not
  classified, CSA carried out/not carried out, transport DG/non-DG).
  **The finder does not resolve these using product data.**
- Certain catalogue texts are **table fragments, property values or wording
  with placeholders**, not complete SDS paragraphs.
- Sections 2/3/8/9/11/12/14 often require original classification,
  compositional, exposure, measurement, national regulatory, or
  mode-specific transport information rather than generic reusable phrases.
- CLP Annex IV Part 1 selection conditions and Part 2 legal English wording
  still need separate independently verified mappings; eSDScom catalogue
  text is never substituted for those authentic legal requirements.
- The PDF/guidance ingestion and earlier readiness prompts remain accessible
  from their existing pages, but the **new primary authoring flow is phrase
  retrieval and selection**.
- Original eSDScom 5.5 licence and any further restrictions remain applicable
  to source wording and exported drafts.

## Next improvement

Add product-specific matching and draft conflict detection in the selection
board after legal source requirements are independently checked. That can
prioritise source wording against product facts *without* making it a
mandatory/legal phrase or claiming that the SDS is complete.
