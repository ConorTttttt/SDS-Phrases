"""Shared local source verification for both Gemini package builders."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def verify_sources(manifest_path, source_dir):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    sources = manifest["sources"]
    for field in ("id", "filename", "package_filename"):
        values = [s[field] for s in sources]
        if len(values) != len(set(values)) or any(
            not isinstance(v, str) or not v or v in (".", "..") or "/" in v or "\\" in v
            for v in values
        ):
            raise ValueError("Invalid or duplicate source manifest " + field)
    for s in sources:
        if type(s["pages"]) is not int or s["pages"] < 1 or not re.fullmatch(r"[a-f0-9]{64}", s["sha256"]):
            raise ValueError("Invalid source fingerprint metadata: " + s["id"])
        path = Path(source_dir) / s["filename"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != s["sha256"]:
            raise ValueError("Missing or changed pinned source: " + s["filename"])
    return manifest


def extract_pages(path, expected_pages):
    tool = shutil.which("pdftotext")
    if not tool:
        raise ValueError("Page extraction requires Poppler pdftotext on PATH")
    try:
        result = subprocess.run([tool, "-layout", "-enc", "UTF-8", str(path), "-"],
                                capture_output=True, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Poppler page extraction failed: " + str(path)) from exc
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if len(pages) != expected_pages:
        raise ValueError("Page count mismatch: " + str(path))
    return pages
