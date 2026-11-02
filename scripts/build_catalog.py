#!/usr/bin/env python3
"""Rebuild a local inventory without treating downloads as reading evidence.

Each acquisition attempt stays in the JSONL logs. This catalogue reconciles
source aliases, actual files, hashes, text-layer warnings, and curated reading
annotations. It does not infer clinical validity or historical authenticity.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "references" / "sources"


def normalized_url(url):
    parts = urlsplit(url or "")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), unquote(parts.path), parts.query, ""))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    grouped = {}
    attempt_count = 0
    for manifest in sorted((BASE / "manifests").glob("*.jsonl")):
        for lineno, line in enumerate(manifest.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid manifest {manifest.name}:{lineno}: {exc}")
            source_id = record.get("id")
            if not source_id:
                raise SystemExit(f"Missing source ID: {manifest.name}:{lineno}")
            record["attempt_manifest"] = manifest.relative_to(ROOT).as_posix()
            record["attempt_line"] = lineno
            grouped.setdefault(source_id, []).append(record)
            attempt_count += 1
    annotations_path = BASE / "source-annotations.json"
    annotations = json.loads(annotations_path.read_text(encoding="utf-8")) if annotations_path.exists() else {}
    sources = []
    for source_id, attempts in sorted(grouped.items()):
        def stamp(r):
            return r.get("retrieved_at_utc", r.get("accessed_at", ""))
        attempts.sort(key=stamp)
        # Prefer an actual available file over a later failed retry. Keep all
        # attempts and the latest attempt's status independently.
        available = [r for r in attempts if r.get("path") and (ROOT / r["path"]).is_file() and r.get("status") != "failed"]
        chosen = dict((available or attempts)[-1])
        # Carry forward richer descriptions without overwriting their provenance.
        for record in reversed(attempts):
            for k in ("edition", "kind", "source_kind", "lacan_primary", "reading_scope"):
                if k not in chosen and k in record:
                    chosen[k] = record[k]
        chosen["id"] = source_id
        chosen["latest_attempt_status"] = attempts[-1].get("status", "unknown")
        chosen["manifest_record_count"] = len(attempts)
        chosen["reading_receipts"] = [{k:r[k] for k in ("reading_status","reading_scope","voice_scope","attempt_manifest","attempt_line") if k in r} for r in attempts if r.get("reading_scope") or r.get("voice_scope")]
        chosen["attempts"] = [{k: r[k] for k in ("status", "error", "url", "path", "retrieved_at_utc", "accessed_at", "attempt_manifest", "attempt_line") if k in r} for r in attempts]
        chosen.setdefault("kind", chosen.get("source_kind", "unclassified"))
        chosen.setdefault("reading_status", "archived_not_claimed_read")
        chosen.update(annotations.get(source_id, {}))
        chosen.setdefault("lacan_primary", False)
        path = ROOT / chosen["path"] if chosen.get("path") else None
        chosen["local_file_available"] = bool(path and path.is_file())
        if chosen["local_file_available"]:
            data = path.read_bytes()
            actual_hash = hashlib.sha256(data).hexdigest()
            if chosen.get("sha256") and chosen["sha256"] != actual_hash:
                raise SystemExit(f"Hash mismatch for {source_id}: {path}")
            chosen["sha256"] = actual_hash
            chosen["bytes"] = len(data)
            if path.suffix.lower() == ".pdf" and not data.startswith(b"%PDF-"):
                raise SystemExit(f"Not a PDF: {source_id}: {path}")
            if not chosen.get("text_path") and path.with_suffix(".txt").is_file():
                chosen["text_path"] = path.with_suffix(".txt").relative_to(ROOT).as_posix()
        text_path = ROOT / chosen["text_path"] if chosen.get("text_path") else None
        chosen["searchable_text_available"] = bool(text_path and text_path.is_file())
        if chosen["searchable_text_available"]:
            text = text_path.read_text(encoding="utf-8", errors="replace")
            chosen["text_chars"] = len(text)
            chosen["text_sha256"] = hashlib.sha256(text_path.read_bytes()).hexdigest()
            warnings = []
            if "\x00" in text:
                warnings.append("NUL characters: check original encoding")
            if text.count("\ufffd") > 10:
                warnings.append("Replacement characters: check font/encoding")
            if len(re.findall(r"/[A-Z]\d", text)) > 20:
                warnings.append("Possible unmapped PDF glyphs: inspect alternate extraction")
            page_blocks = re.split(r"(?:\[\[PDF_PAGE_\d+\]\]|\[PDF PAGE \d+\])", text)[1:]
            if page_blocks:
                chosen["extracted_page_markers"] = len(page_blocks)
                empty = sum(len(re.sub(r"\s|\d", "", p)) < 5 for p in page_blocks)
                chosen["nearly_empty_extracted_pages"] = empty
                if empty / len(page_blocks) > .15:
                    warnings.append("More than 15% of pages lack usable extracted text")
            chosen["text_quality_warnings"] = warnings
        chosen["document_identity"] = "sha256:" + chosen["sha256"] if chosen.get("sha256") else "url:" + normalized_url(chosen.get("url"))
        chosen["normalized_url"] = normalized_url(chosen.get("url"))
        sources.append(chosen)
    identities = {}
    for r in sources:
        identities.setdefault(r["document_identity"], []).append(r["id"])
    for r in sources:
        r["same_document_aliases"] = identities[r["document_identity"]]
    local_unique = {}
    for r in sources:
        if r["local_file_available"]:
            local_unique.setdefault(r["document_identity"], r)
    # A study-unit ratio uses explicit curated annotations, never the words
    # 'primary' or 'read' occurring in prose and never an archive index page.
    used = [r for r in sources if r.get("substantively_used")]
    used_unique = {}
    for r in used:
        identity = r.get("study_unit", r["document_identity"])
        used_unique.setdefault(identity, []).append(r)
    primary_units = sum(any(r.get("lacan_primary") for r in aliases) for aliases in used_unique.values())
    stats = {
        "source_aliases": len(sources),
        "manifest_records": attempt_count,
        "failed_manifest_records": sum(a.get("status") == "failed" for rows in grouped.values() for a in rows),
        "distinct_local_documents_by_hash": len(local_unique),
        "distinct_local_pdf_documents": sum(str(r.get("path", "")).lower().endswith(".pdf") for r in local_unique.values()),
        "distinct_local_bytes": sum(r.get("bytes", 0) for r in local_unique.values()),
        "searchable_text_characters_distinct_documents": sum(r.get("text_chars", 0) for r in local_unique.values()),
        "curated_substantively_used_units": len(used_unique),
        "curated_lacan_primary_units": primary_units,
        "curated_lacan_primary_ratio": primary_units / len(used_unique) if used_unique else None,
    }
    result = {"schema_version": 1, "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "counting_note": "Study units are explicitly annotated; aliases of the same historical text can share study_unit. Downloaded archive indexes and unread seminars do not increase the reading count. A critic's own text is not Lacan-primary.", "statistics": stats, "sources": sources}
    target = BASE / "catalog.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
