# Validation evidence
Baseline c9da6bb2abf47d9e6bc337f28f17030034bff5d5, 26 November 2026.

Executed locally: sha256sum and pdfinfo on five supplied PDFs (REACH 603, CLP 1584, ECHA SDS 137, REF-11 42, ECHA label 200 pages); all hashes/page counts match regulatory/source_manifest.json. Poppler pdftotext -f 117 -l 152 -layout on full REACH: 36 pages, Annex II Part A, Table 1.1, Part B, Section 16 markers match legacy importer expectations; font warnings present. Not legal or extraction fidelity validation.

Remote Git inspection: identical EU_SDS rules/test blobs; all ten SDS-Phrases feature tips behind_by=0. Missing v4 references restored from pinned upstream. Direct git ls-remote failed with DNS resolution error. No full checkout or inherited suite result available at time of record. No unexecuted test claimed passed.

CI configured to run checked Python discovery, all web JavaScript syntax checks, original Section 9 Node tests and HTTP smoke checks in an isolated network namespace after dependencies provisioned. Optional real-source tests require SDS_SOURCE_DIR; explicitly skipped otherwise. Inspect Actions results at exact commit SHA. Browser UI, licensed catalogue, Gemini execution and independent legal review remain outstanding.
