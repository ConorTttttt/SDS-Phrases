"""Local supplier evidence extraction. Page coordinates are PDF points."""
import base64
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

def _pdf_visuals(page):
    """Retain image regions and red vector marks as candidates for visual review."""
    import fitz
    regions = [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    for path in page.get_drawings():
        colors = (path.get("color"), path.get("fill"))
        if any(c and len(c) == 3 and c[0] > .55 and c[1] < .45 and c[2] < .45 for c in colors):
            box=path["rect"]
            if box.height >= 8 and 0.7 <= box.width / box.height <= 1.4:
                regions.append(box)
    previews = []
    for coords in dict.fromkeys(tuple(r) for r in regions):
        box = fitz.Rect(coords) & page.rect
        if box.is_empty:
            continue
        scale = min(2, 180 / max(box.width, box.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=box, alpha=False)
        previews.append({"bbox": list(box), "png": base64.b64encode(pix.tobytes("png")).decode()})
    return previews

def extract(path, ocr=False):
    path = Path(path)
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    pages = []
    context = {}
    if suffix == ".pdf":
        import fitz
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            for number, page in enumerate(pdf, 1):
                text = page.get_text(sort=True)
                method = "PDF text layer"
                if ocr and not text.strip():
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    text = subprocess.run(["tesseract", "stdin", "stdout"], input=pix.tobytes("png"),
                                          capture_output=True, check=True).stdout.decode()
                    method = "local OCR"
                pages.append(dict(page=number, text=text, method=method,
                                  tables=[t.extract() for t in page.find_tables().tables],
                                  image_regions=[list(i["bbox"]) for i in page.get_image_info()],
                                  visual_candidates=_pdf_visuals(page)))
    elif suffix == ".docx":
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            body = document.find(ns+"body")
            tables = []
            lines = []
            for child in body:
                if child.tag == ns+"tbl":
                    rows = [["".join(c.itertext()) for c in row.findall(ns+"tc")]
                            for row in child.findall(ns+"tr")]
                    tables.append(rows)
                    lines.extend("\t".join(row) for row in rows)
                elif child.tag == ns+"p":
                    lines.append("".join(t.text or "" for t in child.iter(ns+"t")))
            pages.append(dict(page=None, text="\n".join(lines), method="DOCX body order",
                              tables=tables, images=[n for n in archive.namelist() if n.startswith("word/media/")]))
    elif suffix == ".json":
        data = json.loads(raw)
        context = data.get("assessment_context", {})
        for item in data["pages"]:
            if item.get("page") is not None and (type(item["page"]) is not int or item["page"]<1):
                raise ValueError("Page numbers must be positive integers or null")
            if not isinstance(item["text"], str):
                raise ValueError("Each page needs string text")
            pages.append(dict(item, method="supplied JSON"))
    elif suffix == ".txt":
        parts = raw.decode("utf-8-sig").split("\f")
        pages = [dict(page=i if len(parts)>1 else None, text=t, method="plain text")
                 for i,t in enumerate(parts, 1)]
    else:
        raise ValueError("Supported supplier formats: PDF, DOCX, JSON and TXT")
    for page in pages:
        page["hazard_codes"] = sorted(set(re.findall(r"\b(?:EUH|H)\d{3}[A-Za-z]*\b", page["text"])))
        page["pictogram_codes"] = sorted(set(re.findall(r"\bGHS0[1-9]\b", page["text"])))
        page["fields"] = [dict(label=m[1], value=m[2]) for m in
                          re.finditer(r"(?m)^([^:\r\n]{1,80}):[ \t]*(.+)$", page["text"])]
    return dict(context=context, name=path.name, sha256=hashlib.sha256(raw).hexdigest(), pages=pages)

def blocks(pages, valid):
    result = {}
    heading = None
    for index, page in enumerate(pages):
        for line in page["text"].splitlines():
            match = re.match(r"^\s*(?:SECTION\s+(\d{1,2})\b|(\d{1,2}\.\d+)(?=[.\s:]|$))", line, re.I)
            if match and (code := match[1] or match[2]) in valid:
                heading = code
            if heading:
                result.setdefault(heading, []).append((index, line))
    return result
