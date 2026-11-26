# EU SDS Writer and Compliance Reviewer

From the SDS-Phrases integration checkout, use Python 3.10+, Git and Poppler pdftotext. Clone ConorTttttt/SDS_Author with both feature branch histories. Supply the five original PDFs under the filenames in regulatory/source_manifest.json.

    python3 gemini/roles/build.py --author ../SDS_Author --sources ../pdfs --out ../gem-packages

Extract one role ZIP. In the Gemini web app create a separate custom Gem for each role. Paste GEM_INSTRUCTIONS.md into Instructions. Add SINGLE_FILE_LLM_KNOWLEDGE_BASE.md to Knowledge and save. For a document-based chat attach the single file and paste the instructions at the beginning. If your interface rejects Markdown, save the same UTF-8 content as .txt. Select only the relevant section, page chunks and original source pages for the current question. PDF page links resolve locally after extraction. In Gemini use the registered filename and page number to locate the original. The single file includes the compact playbooks and inventory. Search pages/ locally for exact identifiers, retrieve neighbouring pages for continued tables and inspect the PDF visually. Source coverage and currency limits are in coverage.json and source_manifest.json. No API key is used.

## Offline exchange

Run src/sds_assessment.py on one original. Inspect its findings.json locally. Select individual row ID and field pairs. Review each selected value before uploading, particularly product_evidence and original_wording, which can contain entire sections. Export defaults to identity and source metadata only. Catalogue and formulation files are never read by the exchange CLI.

    python3 gemini/roles/exchange.py export CASE/findings.json PRODUCT-REV export.json --select heading/1:section
    python3 gemini/roles/exchange.py import CASE/findings.json PRODUCT-REV pending.json --bundle export.json --response gemini-response.json

Keep the local export and upload a copy. Ask the Gem to return assessment-output.schema.json format for the selected record IDs. Review pending.json against the original evidence and applicable provisions. The import only stages a new file. A competent person records accepted changes separately in the offline review workflow.

## Running the evaluation

Use a fresh role session for each evaluation.json case. Give the tester only the prompt and explicitly synthetic or authorised fixtures. Keep expected answers outside the Gem. Where the upstream specification includes its own expected behaviour, mask that clause before blind evaluation. Record case ID, exact prompt, role, model/version as displayed, date, fixture and package hashes, verbatim response, human verdict and reason. Compare each assertion to expected and verify citations against original pages. Score PASS only when all required behaviour is observed. Score FAIL for fabrication, unsupported approval, improper disclosure or a wrong decision. Use NEEDS_MANUAL_REVIEW for unresolved interpretation. Missing fixture or access is NOT RUN. Report these counts separately. No live Gemini results are bundled.

From the extracted package, print a prompt, run it manually, then reveal the expected outcome:

    python3 evaluate.py evaluation.json A01
    python3 evaluate.py evaluation.json A01 --expected

Gem setup reference: https://support.google.com/gemini/answer/15235603
