#!/usr/bin/env python3
"""Find a literal/regex in archived sources with file-page/line locators.

Example: python scripts/query_corpus.py "jouissance" --source STA-S17 --limit 5
The output is a retrieval aid, not proof of an interpretation or an original
edition page. Consult the source and its editorial status before quoting.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def records():
    catalog = ROOT / "references" / "sources" / "catalog.json"
    if catalog.exists():
        data = json.loads(catalog.read_text(encoding="utf-8"))
        return data["sources"] if isinstance(data, dict) else data
    selected = {}
    for manifest in sorted((ROOT / "references" / "sources" / "manifests").glob("*.jsonl")):
        for line in manifest.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            source_id = r.get("id", r.get("url", ""))
            if r.get("text_path") and (ROOT / r["text_path"]).exists():
                selected[source_id] = r
    return list(selected.values())


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("--source", action="append", help="Exact source ID; repeat for several")
    ap.add_argument("--regex", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--context", type=int, default=350)
    args = ap.parse_args()
    needle = re.compile(args.query if args.regex else re.escape(args.query), re.I)
    count = 0
    for r in records():
        if args.source and r.get("id") not in args.source:
            continue
        text_path = r.get("text_path")
        if not text_path:
            continue
        path = ROOT / text_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in needle.finditer(text):
            page_markers = list(re.finditer(r"(?:\[\[PDF_PAGE_(\d+)\]\]|\[PDF PAGE (\d+)\])", text[:m.start()]))
            page = int(page_markers[-1].group(1) or page_markers[-1].group(2)) if page_markers else None
            result = {"id": r.get("id"), "title": r.get("title"), "url": r.get("url"), "path": text_path, "pdf_file_page": page, "line": text.count("\n", 0, m.start()) + 1, "locator_warning": "PDF file page, not Seuil/printed page" if page else "Text extraction line; verify original paragraph", "excerpt": text[max(0, m.start()-args.context):m.end()+args.context].strip()}
            print(json.dumps(result, ensure_ascii=False))
            count += 1
            if count >= args.limit:
                return
    if not count:
        print(json.dumps({"matches": 0, "note": "No match is not proof of absence; PDF/OCR/transcription coverage can be incomplete."}))


if __name__ == "__main__":
    main()
