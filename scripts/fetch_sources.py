#!/usr/bin/env python3
"""Archive explicit public source URLs and extract searchable, page-marked text.

The manifest distinguishes retrieval from reading. No credentials, paywall
circumvention, global proxy changes, or implicit crawling are performed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 100 * 1024 * 1024


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def safe_path(relative):
    # Validate lexically before touching the filesystem. Windows realpath on a
    # concurrently-created parent can mix extended and ordinary drive prefixes.
    rel = Path(str(relative).replace("/", os.sep))
    if rel.is_absolute() or rel.drive or ".." in rel.parts or rel.parts[:2] != ("references", "sources"):
        raise ValueError("Source destination must be a relative path in references/sources")
    p = ROOT / rel
    for parent in [p, *p.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError(f"Source destination must not traverse filesystem links: {parent}")
    return p


def decode(data, content_type):
    encodings = []
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encodings.append("utf-32")
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.append("utf-16")
    charset = re.search(r"charset\s*=\s*[\"']?([\w-]+)", content_type)
    meta = re.search(br'charset\s*=\s*[\"\']?([\w-]+)', data[:8192], re.I)
    if charset:
        encodings.append(charset.group(1))
    if meta:
        encodings.append(meta.group(1).decode("ascii", "ignore"))
    encodings.extend(["utf-8-sig", "cp1252", "latin-1"])
    for enc in encodings:
        try:
            return data.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            pass
    return data.decode("utf-8", "replace"), "utf-8-replace"


def extract(path, content_type):
    data = path.read_bytes()
    target = path.with_suffix(".txt")
    if data.startswith(b"%PDF-"):
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = [p.extract_text() or "" for p in reader.pages]
        text = "\n\n".join(f"[[PDF_PAGE_{i:04d}]]\n{t}" for i, t in enumerate(pages, 1))
        method = "pypdf; PDF page numbers are 1-based file pages, not printed/Seuil pages"
        detail = {"pages": len(pages), "empty_pages": sum(not p.strip() for p in pages)}
    elif "html" in content_type.lower() or b"<html" in data[:2048].lower():
        raw, enc = decode(data, content_type)
        parser = TextExtractor()
        parser.feed(raw)
        text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
        text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()
        method = "HTMLParser; HTML paragraph order, no PDF page equivalence"
        detail = {"encoding": enc}
    elif path.suffix.lower() in {".txt", ".md"} or content_type.startswith("text/"):
        text, enc = decode(data, content_type)
        method, detail = "decoded text", {"encoding": enc}
    else:
        return {"extraction_status": "unsupported_format"}
    target.write_text(text, encoding="utf-8")
    return {"extraction_status": "extracted" if text.strip() else "no_text", "text_path": target.relative_to(ROOT).as_posix(), "text_chars": len(text), "extraction_method": method, **detail}


def retrieve(url, path, proxy, timeout):
    """Prefer native curl's OS trust store; never disable TLS verification."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if curl:
        temp = path.with_suffix(path.suffix + ".download")
        command = [curl, "--silent", "--show-error", "--fail", "--location", "--max-redirs", "5", "--connect-timeout", str(min(12, timeout)), "--max-time", str(timeout), "--max-filesize", str(MAX_BYTES), "--user-agent", "Mozilla/5.0 (compatible; LacanPersonalResearch/2.0)", "--output", str(temp), "--write-out", "%{http_code}\n%{content_type}\n%{url_effective}"]
        command += ["--proxy", proxy] if proxy else ["--noproxy", "*"]
        command += [url]
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout + 5, check=False)
            if result.returncode:
                raise OSError(result.stderr.decode("utf-8", "replace").strip())
            info = result.stdout.decode("utf-8", "replace").splitlines()
            data = temp.read_bytes()
            return data, info[1] if len(info) > 1 else "", info[2] if len(info) > 2 else url
        finally:
            if temp.exists():
                temp.unlink()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LacanPersonalResearch/2.0)", "Accept": "application/pdf,text/html,text/plain,*/*"})
    with opener.open(request, timeout=timeout) as response:
        return response.read(MAX_BYTES + 1), response.headers.get("Content-Type", ""), response.geturl()


def fetch_one(spec, proxy=None, timeout=45):
    record = dict(spec)
    record["retrieved_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    record.setdefault("reading_status", "archived_not_claimed_read")
    try:
        url = str(spec["url"])
        if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("Only explicit public HTTP(S) URLs are accepted")
        path = safe_path(spec["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size:
            data = path.read_bytes()
            ctype = "application/pdf" if data.startswith(b"%PDF-") else "text/html"
            record.update(status="cached", final_url=url, content_type=ctype)
        else:
            for attempt in range(2):
                try:
                    data, ctype, final_url = retrieve(url, path, proxy, timeout)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code < 500 or attempt:
                        raise
                    time.sleep(0.8)
                except (TimeoutError, OSError):
                    if attempt:
                        raise
                    time.sleep(0.8)
            if len(data) > MAX_BYTES:
                raise ValueError("Source exceeds 100 MiB download bound")
            if len(data) < 100:
                raise ValueError("Response too small to be a substantive source")
            if path.suffix.lower() == ".pdf" and not data.startswith(b"%PDF-"):
                raise ValueError("Expected PDF signature; response was not a PDF")
            if any(token in data[:3000].lower() for token in [b"<title>just a moment", b"<title>access denied", b"verify you are human"]):
                raise ValueError("Access-control/interstitial response; no bypass attempted")
            temp = path.with_suffix(path.suffix + ".part")
            temp.write_bytes(data)
            os.replace(temp, path)
            record.update(status="downloaded", final_url=final_url, content_type=ctype)
        record.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        try:
            record.update(extract(path, record["content_type"]))
        except Exception as exc:
            record.update(extraction_status="failed", extraction_error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    return record


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", type=Path, help="JSON list of explicit id/title/url/path source objects")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--proxy", help="Optional per-run HTTP proxy; no system settings are changed")
    args = ap.parse_args()
    specs = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    ids = [s["id"] for s in specs]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate source IDs in fetch plan")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with args.manifest.open("w", encoding="utf-8") as out, concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futures = {pool.submit(fetch_one, s, args.proxy, args.timeout): s for s in specs}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            results.append(r)
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
            print(json.dumps({k: r[k] for k in ("id", "status", "bytes", "text_chars", "error") if k in r}, ensure_ascii=False), flush=True)
    print(json.dumps({"total": len(results), "retrieved": sum(r["status"] != "failed" for r in results), "failed": sum(r["status"] == "failed" for r in results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
