"""Regression tests for *nonbinding* ECHA guidance source ingestion.

Synthetic fixture only; no ECHA source text is distributed in the repository.
"""
import json
import re
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from guidance_sources import GuidanceError,import_guidance,search,summary

PDF_HASH="2a4ac00f87544ebc6397e208e13da331a5ebabd6c5ceb5f149e84cb138501c28"

def fixture(section, *, invalid_authority=False):
    chapter=f"3.{section} SDS SECTION {section}"
    span=str(30+section)+"–"+str(30+section)
    head=f"""---
title: "{chapter}"
document_id: "echa-sds-guidance-v4-2020-s{section}"
source_version: "4.0 — December 2020"
source_reference: "ECHA-20-H-25-EN"
source_sha256: "{PDF_HASH}"
page_span: "{span}"
authority: "Explanatory ECHA guidance; {'CLAIMED PRIMARY LAW' if invalid_authority else 'NOT authoritative legislation'}"
---

# {chapter}
**ECHA printed page {30+section}** — source page
Historical nonbinding guidance.
"""
    if section==16:
        return head
    if section==3:
        return head+"""<a id="echa-sds-3-3"></a>
### 3.3 SDS SECTION 3: Not a real subsection
This text is a chapter introduction.
<a id="echa-sds-3-1"></a>
### 3.1. Substances
Illustrative source passage.
"""
    return head+f"""<a id="echa-sds-{section}-1"></a>
### {section}.1. Example source heading
Source text with a synthetic example for section {section}.
"""

def make_archive(path, *, remove=None, invalid=None):
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for sec in range(1,17):
            if sec==remove:continue
            z.writestr(f"CLP_A_I-main/SDS_Section_{sec:02}.md",
                       fixture(sec,invalid_authority=(sec==invalid)))

class ECHAGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        folder=Path(self.temp.name)
        self.archive=folder/"guidance.zip"
        self.db=folder/"guidance.sqlite"
        make_archive(self.archive)
    def tearDown(self):
        self.temp.cleanup()

    def test_complete_import_is_nonbinding(self):
        result=import_guidance(self.archive,self.db)
        self.assertEqual(result["sections"],16)
        self.assertEqual(result["subsection_passages"],15)
        self.assertFalse(result["original_pdf_in_package"])
        self.assertFalse(result["current_legal_requirements_verified"])
        details=summary(self.db)
        self.assertEqual(details["section_count"],16)
        self.assertEqual(details["metadata"]["source_type"],"nonbinding_historical_guidance")
        self.assertEqual(details["metadata"]["original_pdf_sha256_verified"],"no")
        self.assertEqual(details["metadata"]["legally_binding"],"no")

    def test_source_code_and_pages_correct(self):
        import_guidance(self.archive,self.db)
        r=search(self.db,section="3")
        self.assertEqual(r["total"],2) # section overview, 3.1; not chapter heading 3.3
        self.assertEqual([x["source_key"] for x in r["results"]],["3","3.1"])
        self.assertEqual(r["results"][1]["source_page"],33)
        self.assertEqual(r["results"][0]["legal_status"],"not_legally_verified")

    def test_no_pdf_no_legal_verification(self):
        import_guidance(self.archive,self.db)
        r=summary(self.db)
        self.assertEqual(r["metadata"]["original_pdf_in_package"],"no")
        self.assertEqual(r["metadata"]["current_legal_requirements_verified"],"no")
        self.assertEqual(r["metadata"]["declared_original_pdf_sha256"],PDF_HASH)

    def test_search_case_and_pagination(self):
        import_guidance(self.archive,self.db)
        r=search(self.db,query="SYNTHETIC EXAMPLE",limit=4)
        self.assertEqual(r["total"],14)
        self.assertEqual(len(r["results"]),4)
        self.assertEqual(len(search(self.db,query="SYNTHETIC EXAMPLE",limit=4,offset=13)["results"]),1)

    def test_invalid_archives_fail_closed(self):
        make_archive(self.archive,remove=4)
        with self.assertRaises(GuidanceError):
            import_guidance(self.archive,self.db)
        self.assertFalse(self.db.exists())
        make_archive(self.archive,invalid=8)
        with self.assertRaises(GuidanceError):
            import_guidance(self.archive,self.db)

    def test_reimport_is_atomic(self):
        import_guidance(self.archive,self.db)
        before=summary(self.db)["metadata"]["archive_sha256"]
        make_archive(self.archive,remove=1)
        with self.assertRaises(GuidanceError):
            import_guidance(self.archive,self.db)
        after=summary(self.db)["metadata"]["archive_sha256"]
        self.assertEqual(before,after)

    def test_untrusted_filter_rejected(self):
        import_guidance(self.archive,self.db)
        for bad in ("0","17","1 OR 1=1"):
            with self.subTest(bad=bad),self.assertRaises(GuidanceError):
                search(self.db,section=bad)
        with self.assertRaises(GuidanceError):
            search(self.db,limit=-1)

if __name__=="__main__":
    unittest.main()
