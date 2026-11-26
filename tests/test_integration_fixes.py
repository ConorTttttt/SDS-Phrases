"""Regression tests for integration defects found in the 19efd59 validation run (ledger L34, L36-L38)."""
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import canonical_requirements as c


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_registry(target):
    """Minimal synthetic root holding a copy of the committed registry inputs."""
    shutil.copytree(ROOT / "regulatory", target / "regulatory")
    return target


class DeterministicExports(unittest.TestCase):
    def test_committed_jsonl_uses_canonical_serialisation(self):
        text = (ROOT / "regulatory/canonical/requirements.jsonl").read_text(encoding="utf-8")
        pack, _, _ = c.load()
        self.assertEqual(text, c.jsonl(pack["requirements"]))
        for line in text.splitlines():
            self.assertEqual(line, json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        self.assertTrue(text.endswith("\n") and "\r" not in text)

    def test_jsonl_independent_of_key_order(self):
        pack, _, _ = c.load()
        rows = pack["requirements"][:3]
        self.assertEqual(c.jsonl(rows), c.jsonl([dict(reversed(list(r.items()))) for r in rows]))
        self.assertEqual(c.jsonl([]), "")

    def test_build_is_byte_reproducible_and_matches_committed(self):
        with tempfile.TemporaryDirectory() as d:
            first, second = Path(d) / "a", Path(d) / "b"
            c.build(first)
            c.build(second)
            names = sorted(p.name for p in first.iterdir() if p.suffix != ".sqlite")
            self.assertEqual(names, sorted(p.name for p in second.iterdir() if p.suffix != ".sqlite"))
            for name in names:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)
            for name in c.COMMITTED_EXPORTS:
                self.assertEqual((first / Path(name).name).read_bytes(), (ROOT / name).read_bytes(), name)
            self.assertEqual(c.jsonl(json.loads(l) for l in (first / "all_requirements.jsonl").read_text(encoding="utf-8").splitlines()),
                             (first / "all_requirements.jsonl").read_text(encoding="utf-8"))

    def test_committed_exports_are_current(self):
        self.assertEqual(c.sync_committed(check=True), [])


class CoverageMatrix(unittest.TestCase):
    def test_matrix_derived_from_registry(self):
        pack, raw, _ = c.load()
        matrix = c.coverage_matrix(pack, raw)
        cov = c.coverage(pack, raw)
        self.assertEqual(matrix["release"], pack["release"])
        self.assertEqual(list(matrix["sections"]), sorted(cov, key=int))
        self.assertEqual(sum(len(s["assessment_targets"]) for s in matrix["sections"].values()), len(pack["requirements"]))
        self.assertEqual(sum(s["source_records"] for s in matrix["sections"].values()), len(raw))
        for key, entry in matrix["sections"].items():
            self.assertEqual(entry["mapped_source_records"] + entry["unmapped_source_records"], entry["source_records"])
            self.assertEqual(entry["verification"], "incomplete")
        changed = json.loads(json.dumps(pack))
        changed["requirements"][0]["verification_status"] = "synthetic_changed_status"
        self.assertNotEqual(c.coverage_matrix(changed, raw), matrix)

    def test_drift_detected_and_regenerated(self):
        with tempfile.TemporaryDirectory() as d:
            root = copy_registry(Path(d))
            matrix = root / c.COMMITTED_EXPORTS[1]
            jsonl = root / c.COMMITTED_EXPORTS[0]
            self.assertEqual(c.sync_committed(root, check=True), [])
            matrix.write_text(matrix.read_text(encoding="utf-8").replace('"source_records": 24', '"source_records": 25', 1), encoding="utf-8")
            lines = jsonl.read_text(encoding="utf-8").splitlines()
            jsonl.write_text("\n".join([json.dumps(json.loads(lines[0]))] + lines[1:]) + "\n", encoding="utf-8")
            tampered = matrix.read_bytes()
            self.assertEqual(sorted(c.sync_committed(root, check=True)), sorted(c.COMMITTED_EXPORTS))
            self.assertEqual(matrix.read_bytes(), tampered)
            c.sync_committed(root)
            self.assertEqual(c.sync_committed(root, check=True), [])
            self.assertEqual(matrix.read_bytes(), (ROOT / c.COMMITTED_EXPORTS[1]).read_bytes())

    def test_cli_check_exit_status(self):
        run = subprocess.run([sys.executable, str(ROOT / "src/canonical_requirements.py"), "--check-committed"],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {"stale": []})
        missing = subprocess.run([sys.executable, str(ROOT / "src/canonical_requirements.py")],
                                 capture_output=True, text=True, timeout=120)
        self.assertEqual(missing.returncode, 2)


class LegacyKnowledgeBase(unittest.TestCase):
    def test_markdown_contains_records_versions_and_limits(self):
        text = c.knowledge_base_markdown()
        rows = c.all_requirements()
        self.assertEqual(len(rows), 369)
        for r in rows:
            self.assertIn("### " + r["id"] + "\n", text)
            self.assertIn("Rule version: " + c.requirement_version(r), text)
        for s in json.loads((ROOT / "regulatory/source_manifest.json").read_text(encoding="utf-8"))["sources"]:
            self.assertIn(f"| {s['id']} | {s['version']} |", text)
            self.assertIn(s["sha256"], text)
        clp = json.loads((ROOT / "regulatory/canonical/clp.json").read_text(encoding="utf-8"))
        for gap in clp["coverage_gaps"]:
            self.assertIn("Coverage gap: " + gap, text)
        self.assertIn("None is an independently verified legal obligation", text)
        self.assertNotIn("implementation: executable", text)

    def test_legacy_builder_embeds_registry_without_real_sources(self):
        builder = load_script("legacy_builder_under_test", ROOT / "scripts/build_gemini_package.py")
        manifest = json.loads((ROOT / "regulatory/source_manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "synthetic-sources"
            src.mkdir()
            for s in manifest["sources"]:
                (src / s["filename"]).write_bytes(b"synthetic placeholder, not a pinned source")
            with patch.object(builder, "verify_sources", return_value=manifest), \
                    contextlib.redirect_stdout(io.StringIO()):
                builder.build(src, Path(d) / "package")
            text = (Path(d) / "package/SINGLE_FILE_LLM_KNOWLEDGE_BASE.md").read_text(encoding="utf-8")
            self.assertIn("# Canonical regulatory requirement registry", text)
            for r in c.all_requirements():
                self.assertIn("### " + r["id"] + "\n", text)
            self.assertEqual(text.count("candidate_pending_independent_legal_and_extraction_review / manual_review_only"), 3)

    def test_legacy_builder_without_sources_still_fails_closed(self):
        builder = load_script("legacy_builder_closed", ROOT / "scripts/build_gemini_package.py")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "Missing or changed pinned source"):
                builder.build(Path(d), Path(d) / "package")
            self.assertFalse((Path(d) / "package").exists())


class OutputLocations(unittest.TestCase):
    def test_role_builder_refuses_repository_output(self):
        sys.path.insert(0, str(ROOT / "gemini/roles"))
        roles = load_script("role_builder_under_test", ROOT / "gemini/roles/build.py")
        for inside in (ROOT / "role-packages-test", ROOT / "data" / "nested" / "pkg", ROOT / "x" / ".." / "y"):
            with self.subTest(inside=inside), self.assertRaisesRegex(ValueError, "outside repository"):
                roles.check_output(inside)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(roles.check_output(Path(d) / "new"), Path(d) / "new")
            with self.assertRaisesRegex(ValueError, "new output directory"):
                roles.check_output(Path(d))

    def test_role_builder_cli_rejects_before_writing(self):
        target = ROOT / "role-packages-cli-test"
        self.assertFalse(target.exists())
        with tempfile.TemporaryDirectory() as d:
            run = subprocess.run([sys.executable, str(ROOT / "gemini/roles/build.py"), "--author", d,
                                  "--sources", d, "--out", str(target)], capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 2)
        self.assertIn("Output must be outside repository", run.stderr)
        self.assertFalse(target.exists())
        self.assertFalse(any(p.name.startswith("tmp") for p in ROOT.iterdir() if p.is_dir()))

    def test_both_builders_use_same_rule(self):
        builder = load_script("legacy_builder_location", ROOT / "scripts/build_gemini_package.py")
        with self.assertRaisesRegex(ValueError, "outside repository"):
            builder.build(ROOT, ROOT / "legacy-package-test")
        self.assertFalse((ROOT / "legacy-package-test").exists())


class CoverageEvidence(unittest.TestCase):
    def test_coverage_cites_executed_evidence(self):
        coverage = json.loads((ROOT / "regulatory/coverage.json").read_text(encoding="utf-8"))
        executed = coverage["executed_validation"]
        evidence = json.loads((ROOT / executed["evidence"]).read_text(encoding="utf-8"))
        self.assertEqual(evidence["commit"], executed["commit"])
        full = next(r for r in evidence["python_runs"] if r["run"] == "full optional dependencies")
        isolated = next(r for r in evidence["python_runs"] if r["run"] == "network namespace")
        for run, key in ((full, "python_tests"), (isolated, "network_isolated_python_run")):
            self.assertTrue(run["success"])
            self.assertEqual(sum(s["passed"] for s in run["suites"]), executed[key]["passed"])
        self.assertEqual(sum(s["skipped"] for s in full["suites"]), executed["python_tests"]["skipped"])
        self.assertEqual(evidence["javascript"]["passed"], executed["javascript_tests"]["passed"])
        self.assertIn("no independent legal", executed["scope"].lower())
        self.assertEqual(coverage["overall"], "partial_not_regulator_validated")
        for module in coverage["modules"]:
            self.assertNotEqual(module["validation_status"], "unverified_runtime", module["id"])
            self.assertNotRegex(module["validation_status"].lower(), r"legally (validated|verified)|certified")


if __name__ == "__main__":
    unittest.main()
