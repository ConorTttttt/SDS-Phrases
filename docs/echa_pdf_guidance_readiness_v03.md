# v0.3: original ECHA guidance verification & subsection evidence pilot

**Source verification performed 8 November 2026 (technical only).**

## 1. Verified source identity and structure

The user-provided \`sds_guidance.pdf\` contains exactly **137 PDF pages** of
*ECHA Guidance on the compilation of safety data sheets*, Version 4.0,
December 2020, reference \`ECHA-20-H-25-EN\`, DOI \`10.2823/77155\`.

- Original file SHA-256:
  \`2a4ac00f87544ebc6397e208e13da331a5ebabd6c5ceb5f149e84cb138501c28\`.
- The above SHA-256 **matches all 16 declared source fingerprints** in the
  earlier \`CLP_A_I-main.zip\` Markdown source package.
- All 16 \`SDS_Section_XX.md\` records have ordered source-page labels; every
  referenced number matches the printed PDF page number, including overlapping
  pages between adjoining SDS sections.
- The beginning of ECHA chapter \`3.N SDS SECTION N\` was checked on each
  chapter's **actual first PDF page**:
  1=33, 2=41, 3=46, 4=57, 5=59, 6=61, 7=63, 8=68,
  9=77, 10=93, 11=97, 12=103, 13=109, 14=111, 15=115, 16=118.
- Rendered visual samples were inspected on PDF pages 20, 57, 64, 68, 72
  and 74. Page 72 is an unusually sparse continuation of the DNEL/PNEC
  example; it is not evidence of a lost or truncated page.
- **Not yet verified:** paragraph-by-paragraph transcription completeness,
  every Markdown page break, embedded table geometry, footnotes, formulae,
  captions, examples and all 2026 legislative amendments. A matching PDF
  hash proves source identity, **not extraction fidelity**.

ECHA states expressly that this document is explanatory guidance, not an
authentic legal reference. Legal requirements must be verified against the
applicable REACH Annex II and other binding rules on the product's market date.
The present 2020 guidance discusses the amendment under Regulation (EU)
2020/878; it is historical and does not automatically resolve later changes.
ECHA chapter numbers (such as **3.4**) are **not** SDS subsection numbers.

## 2. New subsection evidence requirements pilot

\`rules/eu_sds_guidance_readiness_pilot.json\` holds **27 authoring prompts**:

| SDS section | Guidance pages | Prompts | What they help collect |
|---|---:|---:|---|
| 4 First aid | 57–59 | 8 | Routes, urgency, responder PPE, acute/delayed symptoms, special treatment |
| 7 Handling/storage | 64–67 | 8 | Use-specific handling, incompatibilities, safe storage conditions, packaging, end use |
| 8 Exposure controls | 68–76 | 11 | OELs, biological values, DNEL/PNEC, engineering control, PPE and environmental control |

Each record stores a specific SDS subsection, descriptive topic, evidence
question, example evidence, ECHA printed-page references, a corresponding
REACH Annex II clause **for future legal review**, and cross-section
consistency link targets.

This is a **review/authoring information inventory**, not a validated legal
decision pack. No prompt changes the 105 existing source phrase mappings.

### Evaluation semantics

\`src/sds_readiness.py\` accepts these inputs for each prompt:

- \`status: unknown\` — not yet assessed.
- \`status: available\` with a **non-empty reference** — evidence submitted
  for expert review; does not mean adequate or legally approved.
- \`status: not_available\` with a **non-empty reason** — missing data reason
  submitted for review; does not mean that a legal requirement can be omitted.
- \`status: not_applicable\` with a **non-empty reason** — non-applicability
  claimed for review; does not mean the claim is legally justified.

With absent/unevidenced input the result is \`information_needed\`.
The engine never accepts an unsupported "Yes" as proof of adequacy.
Every result sets \`content_sufficient:false\` and
\`requirement_legally_verified:false\`; the overall
\`sds_compliant:false\`. UI records are not saved to an external system.

The section gaps and cross-check links are preliminary **information
dependencies**. Before any such prompt is promoted to a legal rule, independent
review must verify statutory wording, conditionality, exceptions and date scope.

### Sources and important examples

- ECHA printed pages 57–59 / REACH Annex II 4.1–4.3 distinguish first aid by
  exposure route, symptoms versus treatment, urgent attention and medical
  advice for competent responders.
- ECHA pages 64–67 / Annex II 7.1–7.3 emphasise identified uses, generation
  of dust/aerosols, incompatible materials, storage conditions and consistency
  with Sections 9/10.
- ECHA pages 68–76 / Annex II 8.1–8.2 distinguish destination-country OELs,
  monitoring, DNEL/PNEC, engineering controls, glove material/thickness/
  breakthrough, eye/face, respiratory and environmental protection.
- The ECHA compilation diagram on printed page 20 is **iterative**: chemical
  composition, physicochemical properties, toxicology/ecology, transport and
  other data feed the drafting of risk management sections and Section 2.
- Section 8 requirements can sometimes be met by applicable attached
  exposure scenarios; a simple blank-field check must not overrule this.

## 3. Local workflow

Save your source PDF as \`~/Downloads/sds_guidance.pdf\` and the earlier
Markdown extraction ZIP as \`~/Downloads/CLP_A_I-main.zip\`.

\`\`\`bash
cd /mnt/holochain/Regulatory/SDS_Phrases
git fetch origin
git switch --track origin/feature/phase3-echa-guidance-verified-evidence-pilot
python3 -m unittest discover -s tests -v

# Original PDF and all 16 Markdown chapter/source-page anchors:
python3 src/guidance_pdf_verification.py \
  ~/Downloads/sds_guidance.pdf --archive ~/Downloads/CLP_A_I-main.zip

# Optional: update the metadata in your already-imported guidance SQLite:
python3 src/guidance_pdf_verification.py \
  ~/Downloads/sds_guidance.pdf --archive ~/Downloads/CLP_A_I-main.zip \
  --db data/echa_guidance_2020.sqlite

python3 src/server.py --port 8095
\`\`\`

Local browser: \`http://127.0.0.1:8095/readiness.html\`.

The optional SQLite metadata update records the external PDF hash and
16-page-anchor verification, *without* changing the original Markdown,
the eSDScom phrase database, the regulatory rule pack or the status of the
text/legal audit.

New APIs:

- \`GET /api/readiness/prompts\` — full structured prompt pack (no source text).
- \`POST /api/readiness/evaluate\` — evidence status by source-traced subsection.

Example:

\`\`\`json
{
  "jurisdiction": "EU",
  "as_of": "2026-11-08",
  "evidence": {
    "ECHA2020-S04-01": {
      "status": "available",
      "reference": "Reviewed first-aid assessment, revision 1"
    },
    "ECHA2020-S04-02": {
      "status": "not_applicable",
      "reason": "Proposed reasoning; needs competent-person review"
    }
  }
}
\`\`\`

The return value does not mark a legal obligation met or an SDS completed.

## 4. Next milestones

1. Independently verify complete Part A REACH Annex II clause hierarchy
   against official consolidated *and* authentic enactment text, not solely
   this 2020 guidance.
2. Build a formal **applicability/exception model** for Sections 4, 7, 8
   with dated, jurisdiction-specific evidence.
3. Map each verified information obligation to product information fields;
   distinguish absence, non-applicability, unavailable data and evidence
   insufficient for a conclusion.
4. Map qualifying evidence to eSDScom phrase candidates only *after*
   regulatory review, preserving exact-source wording and approval workflow.
5. Develop cross-section contradiction tests (2/4/11, 7/9/10, 7/8 and
   6/8/12), then extend to all SDS subsections.
6. Add a reviewed authoring/export workflow without turning guidance
   explanations or list fragments into mandatory text.
