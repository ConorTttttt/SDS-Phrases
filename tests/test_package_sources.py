import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from package_sources import verify_sources, extract_pages


class PackageSources(unittest.TestCase):
    def test_manifest_rejects_missing_tampered_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"synthetic.pdf"
            source.write_bytes(b"fixture")
            row={"id":"test","filename":source.name,"package_filename":"p.pdf","pages":1,
                 "sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
            manifest=root/"manifest.json"
            def write(rows):
                manifest.write_text(json.dumps({"sources":rows}),encoding="utf-8")
            write([row])
            self.assertEqual(verify_sources(manifest,root)["sources"],[row])
            for invalid in ("../synthetic.pdf","..","a\\b.pdf"):
                write([dict(row,filename=invalid)])
                with self.assertRaisesRegex(ValueError,"Invalid or duplicate"):
                    verify_sources(manifest,root)
            write([row,row])
            with self.assertRaisesRegex(ValueError,"Invalid or duplicate"):
                verify_sources(manifest,root)
            write([row])
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"Missing or changed pinned source"):
                verify_sources(manifest,root)
            source.unlink()
            with self.assertRaisesRegex(ValueError,"Missing or changed pinned source"):
                verify_sources(manifest,root)

    def test_poppler_missing_is_actionable(self):
        with patch("package_sources.shutil.which",return_value=None):
            with self.assertRaisesRegex(ValueError,"Poppler pdftotext"):
                extract_pages(Path("fixture.pdf"),1)

    @unittest.skipUnless(os.getenv("SDS_SOURCE_DIR") and os.getenv("SDS_AUTHOR_DIR"),
                         "Pinned PDF directory and SDS_Author Git checkout not provisioned")
    def test_role_generator(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/"packages"
            subprocess.run([sys.executable,str(ROOT/"gemini/roles/build.py"),
                           "--author",os.environ["SDS_AUTHOR_DIR"],"--sources",os.environ["SDS_SOURCE_DIR"],
                           "--out",str(output)],check=True,timeout=900)
            for role in ("writer","reviewer"):
                name="eu-sds-"+role
                with zipfile.ZipFile(output/(name+".zip")) as archive:
                    self.assertIsNone(archive.testzip())
                    for required in ("GEM_INSTRUCTIONS.md","SKILL.md","SINGLE_FILE_LLM_KNOWLEDGE_BASE.md",
                                     "canonical-requirements.json","evaluation.json","source_manifest.json"):
                        self.assertIn(required,archive.namelist())
