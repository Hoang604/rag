"""Fetches the Vietnamese traffic-law corpus from official government sources.

`data/` is gitignored, so without this script the corpus is not reproducible on
another machine and the ingestion pipeline cannot be re-run from scratch. The
registry below is the corpus definition; the downloaded text is derived data.

Why HTML and not the signed PDF
-------------------------------
The authoritative signed PDFs on datafiles.chinhphu.vn are image scans. For
Nghị định 168/2024/NĐ-CP the PDF is 111 pages containing 111 images and
**zero** extractable characters, so pdfplumber yields nothing and OCR would be
required -- introducing exactly the silent digit corruption the ingestion
grounding gate exists to prevent. The government full-text HTML pages carry the
same text losslessly and are used instead.

HTML is flattened block-aware: block-level tags become newlines, inline tags
(span, strong, a, ...) are removed without inserting whitespace. Treating every
tag as a line break splits figures such as "400.000 đồng đến 600.000 đồng"
across lines, which breaks both clause parsing and grounding verification.

Usage:
    uv run python scripts/fetch_corpus.py                 # fetch all
    uv run python scripts/fetch_corpus.py 168/2024/ND-CP  # fetch one
"""

from __future__ import annotations

import gzip
import html as html_module
import json
import re
import sys
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

OUTPUT_DIR = Path("data/raw")

_BLOCK_TAGS = (
    r"p|div|br|tr|li|h[1-6]|table|tbody|thead|tfoot|"
    r"section|article|blockquote|ul|ol|td|th|hr"
)
_SCRIPT_STYLE = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_BLOCK_RE = re.compile(rf"(?i)</?({_BLOCK_TAGS})\b[^>]*>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")


@dataclass(frozen=True)
class LegalSource:
    """One legal document and where its full text is officially published."""

    doc_code: str
    title: str
    effective_date: str
    url: str
    filename: str
    superseded_by: str | None = None
    notes: str = ""
    expected_articles: int = 1
    keywords: tuple[str, ...] = field(default_factory=tuple)


# Official sources only: chinhphu.vn (Government portal) and its full-text
# subdomains. thuvienphapluat.vn and similar aggregators are excluded -- their
# terms of service restrict bulk retrieval and they are not the authority.
REGISTRY: tuple[LegalSource, ...] = (
    LegalSource(
        doc_code="168/2024/ND-CP",
        title=(
            "Nghị định quy định xử phạt vi phạm hành chính về trật tự, an toàn "
            "giao thông trong lĩnh vực giao thông đường bộ; trừ điểm, phục hồi "
            "điểm giấy phép lái xe"
        ),
        effective_date="2025-01-01",
        url=(
            "https://xaydungchinhsach.chinhphu.vn/"
            "toan-van-nghi-dinh-168-2024-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh"
            "-ve-trat-tu-atgt-duong-bo-119241231164556785.htm"
        ),
        filename="168-2024-ND-CP.txt",
        notes="Penalty decree. Primary source of fine amounts and licence point deductions.",
        expected_articles=40,
        keywords=("Phạt tiền", "trừ điểm giấy phép lái xe"),
    ),
    LegalSource(
        doc_code="36/2024/QH15",
        title="Luật Trật tự, an toàn giao thông đường bộ",
        effective_date="2025-01-01",
        url=(
            "https://xaydungchinhsach.chinhphu.vn/"
            "toan-van-luat-trat-tu-an-toan-giao-thong-duong-bo-119240909105718285.htm"
        ),
        filename="36-2024-QH15.txt",
        notes="Governing statute for traffic rules; the decree penalises breaches of it.",
        expected_articles=50,
        keywords=("quy tắc giao thông", "người điều khiển"),
    ),
)


def fetch_html(url: str, timeout: int = 60) -> str:
    """Retrieves a page and decompresses it.

    Compression is requested deliberately: chinhphu.vn serves a truncated page
    to clients advertising `Accept-Encoding: identity` (133 KB versus 1,035 KB),
    and the short version omits the entire statutory body. Requesting gzip and
    decompressing here is what gets the full text.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "vi,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw: bytes = response.read()
        encoding = (response.headers.get("Content-Encoding") or "").lower()

    if "gzip" in encoding:
        raw = gzip.decompress(raw)
    elif "deflate" in encoding:
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)

    return raw.decode("utf-8", errors="replace")


def html_to_text(raw_html: str) -> str:
    """Flattens HTML block-aware so inline markup never splits a figure."""
    stripped = _SCRIPT_STYLE.sub(" ", raw_html)
    stripped = _BLOCK_RE.sub("\n", stripped)
    stripped = _ANY_TAG.sub("", stripped)
    text = html_module.unescape(stripped).replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class FetchReport:
    """Outcome of fetching one source, including integrity signals."""

    doc_code: str
    characters: int
    articles: int
    split_figures: int
    missing_keywords: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return (
            self.characters > 5_000
            and self.articles > 0
            and self.split_figures == 0
            and not self.missing_keywords
        )


def analyse(text: str, source: LegalSource) -> FetchReport:
    """Checks the extracted text is usable before it reaches the parser."""
    articles = len(re.findall(r"Điều \d+\.", text))
    # A digit immediately followed by a line break and a currency word means
    # inline markup split a monetary figure during flattening.
    split_figures = len(re.findall(r"\d\s*\n\s*(?:đồng|nghìn|triệu)", text))
    missing = tuple(kw for kw in source.keywords if kw not in text)
    return FetchReport(
        doc_code=source.doc_code,
        characters=len(text),
        articles=articles,
        split_figures=split_figures,
        missing_keywords=missing,
    )


def fetch_source(source: LegalSource, output_dir: Path) -> FetchReport:
    """Downloads, flattens, verifies and persists one document plus metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    text = html_to_text(fetch_html(source.url))
    report = analyse(text, source)

    text_path = output_dir / source.filename
    text_path.write_text(text, encoding="utf-8")

    meta_path = text_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "doc_code": source.doc_code,
                "title": source.title,
                "effective_date": source.effective_date,
                "superseded_by": source.superseded_by,
                "source_url": source.url,
                "notes": source.notes,
                "characters": report.characters,
                "articles_detected": report.articles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def main(argv: list[str]) -> int:
    wanted = set(argv[1:])
    selected = [s for s in REGISTRY if not wanted or s.doc_code in wanted]
    if not selected:
        print(f"No source matches {sorted(wanted)}.", file=sys.stderr)
        print(f"Known: {[s.doc_code for s in REGISTRY]}", file=sys.stderr)
        return 2

    failures = 0
    for source in selected:
        print(f"-> {source.doc_code} ... ", end="", flush=True)
        try:
            report = fetch_source(source, OUTPUT_DIR)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"FAILED ({exc})")
            failures += 1
            continue

        status = "ok" if report.ok else "SUSPECT"
        print(
            f"{status}: {report.characters:,} chars, {report.articles} articles, "
            f"{report.split_figures} split figures"
        )
        if report.missing_keywords:
            print(f"   expected phrases absent: {list(report.missing_keywords)}")
        if report.articles < source.expected_articles:
            print(
                f"   only {report.articles} articles, expected >= "
                f"{source.expected_articles}; the page may be paginated"
            )
        if not report.ok:
            failures += 1

    print(f"\n{len(selected) - failures}/{len(selected)} sources usable -> {OUTPUT_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
