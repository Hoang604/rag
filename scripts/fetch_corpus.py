"""Fetches the Vietnamese traffic-law corpus from official government sources.

`data/` is gitignored, so without this script the corpus is not reproducible on
another machine and the ingestion pipeline cannot be re-run from scratch. The
registry below is the corpus definition; the downloaded text is derived data.

Which file to take, per document
--------------------------------
The government publishes the same statute in several places and only some of
them carry extractable text. Two failure modes were measured and are avoided by
the registry rather than worked around at parse time:

* Image-only PDFs. `datafiles.chinhphu.vn/.../168-nd-cp.signed.pdf` is 111
  pages containing 111 images and **zero** characters. The unsigned sibling is
  not reliably better -- `238-ndcp.pdf` is also a pure scan -- so every source
  below was probed for a real text layer before being added. OCR is refused on
  purpose: it introduces exactly the silent digit corruption the ingestion
  grounding gate exists to prevent.

* Truncated HTML. chinhphu.vn serves a short page (133 KB versus 1,035 KB) to
  clients advertising `Accept-Encoding: identity`, omitting the statutory body.
  `fetch_html` requests gzip for that reason.

Where a text-bearing PDF exists it is preferred, because Công báo PDFs are the
gazette of record. HTML is used where the PDF is a scan.

HTML is flattened block-aware: block-level tags become newlines, inline tags
(span, strong, a, ...) are removed without inserting whitespace. Treating every
tag as a line break splits figures such as "400.000 đồng đến 600.000 đồng"
across lines, which breaks both clause parsing and grounding verification.

Usage:
    uv run python scripts/fetch_corpus.py                 # fetch all
    uv run python scripts/fetch_corpus.py 168/2024/ND-CP  # fetch one
"""

from __future__ import annotations

import collections
import gzip
import html as html_module
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pdfplumber

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

OUTPUT_DIR = Path("data/raw")

SourceFormat = Literal["html", "pdf"]

_BLOCK_TAGS = (
    r"p|div|br|tr|li|h[1-6]|table|tbody|thead|tfoot|"
    r"section|article|blockquote|ul|ol|td|th|hr"
)
_SCRIPT_STYLE = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_BLOCK_RE = re.compile(rf"(?i)</?({_BLOCK_TAGS})\b[^>]*>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")

# The article body on the chinhphu.vn portals starts at the dateline and ends
# before the site chrome. Without trimming, the last chunk of every document is
# a copyright notice and the first is a navigation menu.
_HTML_BODY_START = re.compile(r"\(Chinhphu\.vn\)\s*[-–]")
_HTML_BODY_END = re.compile(r"Bản quyền thuộc Báo Điện tử Chính phủ")

# Công báo stamps a running header on every page. Left in place it becomes a
# statutory-looking line inside chunks and injects page numbers and gazette
# issue numbers into the digit space the grounding check reasons about.
_GAZETTE_HEADER = re.compile(
    r"(?m)^\s*\d{0,4}\s*CÔNG BÁO\s*/\s*Số\s*[\d\s+]+/\s*Ngày\s*[\d\-]+\s*\d{0,4}\s*$"
)
_BARE_PAGE_NUMBER = re.compile(r"(?m)^\s*\d{1,4}\s*$")
# A PDF column wraps between a figure and its unit: "từ 150.000.000\nđồng trở
# lên". The digits survive, but the line break separates the amount from what it
# measures, so a chunk boundary can land between them and a clause can be read
# as a bare number. Only the newline is replaced; no characters are altered.
_WRAPPED_UNIT = re.compile(r"(\d)\n(đồng|nghìn|triệu|tỷ|km/h|km|%)\b")


@dataclass(frozen=True)
class LegalSource:
    """One legal document and where its full text is officially published."""

    doc_code: str
    title: str
    effective_date: str
    urls: tuple[str, ...]
    filename: str
    fmt: SourceFormat = "html"
    superseded_by: str | None = None
    amends: str | None = None
    in_force: bool = True
    notes: str = ""
    expected_articles: int = 1
    keywords: tuple[str, ...] = field(default_factory=tuple)


# Official sources only: chinhphu.vn (Government portal), congbao.chinhphu.vn
# (the gazette of record) and datafiles.chinhphu.vn. thuvienphapluat.vn and
# similar aggregators are excluded -- their terms of service restrict bulk
# retrieval and they are not the authority.
REGISTRY: tuple[LegalSource, ...] = (
    LegalSource(
        doc_code="168/2024/ND-CP",
        title=(
            "Nghị định quy định xử phạt vi phạm hành chính về trật tự, an toàn "
            "giao thông trong lĩnh vực giao thông đường bộ; trừ điểm, phục hồi "
            "điểm giấy phép lái xe"
        ),
        effective_date="2025-01-01",
        urls=(
            (
                "https://xaydungchinhsach.chinhphu.vn/"
                "toan-van-nghi-dinh-168-2024-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh"
                "-ve-trat-tu-atgt-duong-bo-119241231164556785.htm"
            ),
        ),
        filename="168-2024-ND-CP.txt",
        fmt="html",
        notes=(
            "Penalty decree. Primary source of fine amounts and licence point "
            "deductions. Amended by 238/2026/ND-CP from 2026-08-15."
        ),
        expected_articles=40,
        keywords=("Phạt tiền", "trừ điểm giấy phép lái xe"),
    ),
    LegalSource(
        doc_code="238/2026/ND-CP",
        title=(
            "Nghị định sửa đổi, bổ sung một số điều của Nghị định số "
            "168/2024/NĐ-CP quy định xử phạt vi phạm hành chính về trật tự, an "
            "toàn giao thông trong lĩnh vực giao thông đường bộ; trừ điểm, phục "
            "hồi điểm giấy phép lái xe"
        ),
        effective_date="2026-08-15",
        urls=(
            (
                "https://congbaocdn.chinhphu.vn/"
                "180507251028987904/2026/7/13/469913-1783914973_v1_1783915444_signed.pdf"
            ),
        ),
        filename="238-2026-ND-CP.txt",
        fmt="pdf",
        amends="168/2024/ND-CP",
        notes=(
            "Amends the penalty decree in force. Without it the corpus states "
            "superseded fine amounts as current. The datafiles.chinhphu.vn "
            "copies (signed and unsigned) are both image-only scans; this "
            "gazette PDF is the only text-bearing official copy."
        ),
        expected_articles=3,
        keywords=("ghế ngồi cho trẻ em", "sửa đổi, bổ sung"),
    ),
    LegalSource(
        doc_code="36/2024/QH15",
        title="Luật Trật tự, an toàn giao thông đường bộ",
        effective_date="2025-01-01",
        urls=(
            (
                "https://xaydungchinhsach.chinhphu.vn/"
                "toan-van-luat-trat-tu-an-toan-giao-thong-duong-bo-119240909105718285.htm"
            ),
        ),
        filename="36-2024-QH15.txt",
        fmt="html",
        notes="Governing statute for traffic rules; the decree penalises breaches of it.",
        expected_articles=50,
        keywords=("quy tắc giao thông", "người điều khiển"),
    ),
    LegalSource(
        doc_code="35/2024/QH15",
        title="Luật Đường bộ",
        effective_date="2025-01-01",
        urls=("https://datafiles.chinhphu.vn/cpp/files/vbpq/2024/9/35-2024-qh15.pdf",),
        filename="35-2024-QH15.txt",
        fmt="pdf",
        notes=(
            "Companion statute split from the 2008 traffic law alongside "
            "36/2024/QH15. Citations reading 'theo quy định của Luật Đường bộ' "
            "resolve here."
        ),
        expected_articles=80,
        keywords=("kết cấu hạ tầng đường bộ", "đường cao tốc"),
    ),
    LegalSource(
        doc_code="236/2026/ND-CP",
        title=(
            "Nghị định sửa đổi, bổ sung một số điều của các Nghị định quy định "
            "chi tiết Luật Trật tự, an toàn giao thông đường bộ"
        ),
        effective_date="2026-08-15",
        urls=(
            (
                "https://congbaocdn.chinhphu.vn/"
                "180507251028987904/2026/7/11/469899-1783757230_v1_1783757958_signed.pdf"
            ),
        ),
        filename="236-2026-ND-CP.txt",
        fmt="pdf",
        notes="Amends the decrees detailing 36/2024/QH15 (licences, point restoration).",
        expected_articles=10,
        keywords=("giấy phép lái xe",),
    ),
    LegalSource(
        doc_code="QCVN41/2024/BGTVT",
        title=(
            "Quy chuẩn kỹ thuật quốc gia về báo hiệu đường bộ QCVN 41:2024/BGTVT "
            "(ban hành kèm theo Thông tư 51/2024/TT-BGTVT)"
        ),
        effective_date="2025-01-01",
        urls=(
            (
                "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2024/11/43387/"
                "53148-1-20241359-136051-2024-tt-bgtvt.pdf"
            ),
            (
                "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2024/11/43387/"
                "53152-1-20241361-136251-2024-tt-bgtvt.pdf"
            ),
        ),
        filename="QCVN-41-2024-BGTVT.txt",
        fmt="pdf",
        notes=(
            "Road sign and marking standard. Answers 'what does sign P.124 "
            "mean' and 'may I cross a solid line', which the penalty decree "
            "presupposes but never defines. Parts 3-5 of the gazette are "
            "drawing appendices with no text layer and are excluded."
        ),
        expected_articles=20,
        keywords=("Biển số", "vạch"),
    ),
    LegalSource(
        doc_code="90/VBHN-VPQH",
        title="Luật Xử lý vi phạm hành chính (văn bản hợp nhất)",
        effective_date="2026-03-01",
        urls=("https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/3/90-vbhn-vpqh.pdf",),
        filename="90-VBHN-VPQH.txt",
        fmt="pdf",
        notes=(
            "Procedure the penalty decree presupposes: vehicle impoundment, "
            "limitation periods, payment and appeal. Consolidated text, so it "
            "already carries every amendment."
        ),
        expected_articles=140,
        keywords=("tạm giữ", "thời hiệu xử phạt"),
    ),
)


def fetch_bytes(url: str, timeout: int = 300) -> tuple[bytes, str]:
    """Retrieves a URL, decompressing when the server compressed the body.

    Compression is requested deliberately: chinhphu.vn serves a truncated page
    to clients advertising `Accept-Encoding: identity` (133 KB versus 1,035 KB),
    and the short version omits the entire statutory body.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
            "Accept-Language": "vi,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw: bytes = response.read()
        encoding = (response.headers.get("Content-Encoding") or "").lower()
        content_type = (response.headers.get("Content-Type") or "").lower()

    if "gzip" in encoding:
        raw = gzip.decompress(raw)
    elif "deflate" in encoding:
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)

    return raw, content_type


def fetch_html(url: str, timeout: int = 60) -> str:
    """Retrieves a page as decoded text."""
    raw, _ = fetch_bytes(url, timeout=timeout)
    return raw.decode("utf-8", errors="replace")


def _collapse(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text(raw_html: str) -> str:
    """Flattens HTML block-aware so inline markup never splits a figure."""
    stripped = _SCRIPT_STYLE.sub(" ", raw_html)
    stripped = _BLOCK_RE.sub("\n", stripped)
    stripped = _ANY_TAG.sub("", stripped)
    text = html_module.unescape(stripped).replace("\xa0", " ")
    return _collapse(text)


def trim_portal_chrome(text: str) -> str:
    """Drops the navigation menu and site footer around a portal article."""
    start = _HTML_BODY_START.search(text)
    if start is not None:
        text = text[start.start() :]
    end = _HTML_BODY_END.search(text)
    if end is not None:
        text = text[: end.start()]
    return text.strip()


def _strip_running_furniture(pages: list[str]) -> str:
    """Removes gazette headers, page numbers and any line repeated across pages.

    A running header is indistinguishable from a statutory line once the pages
    are concatenated, and its digits enter the numeric space that grounding
    verification reasons about. Frequency is measured per page rather than per
    occurrence so a genuine repeated phrase inside one long page survives.
    """
    if not pages:
        return ""

    seen_on_pages: collections.Counter[str] = collections.Counter()
    for page in pages:
        for line in {ln.strip() for ln in page.splitlines() if ln.strip()}:
            seen_on_pages[line] += 1

    threshold = max(3, int(len(pages) * 0.30))
    boilerplate = {
        line
        for line, count in seen_on_pages.items()
        if count >= threshold and len(line) <= 120
    }

    kept: list[str] = []
    for page in pages:
        body = _GAZETTE_HEADER.sub("", page)
        body = _BARE_PAGE_NUMBER.sub("", body)
        kept.extend(
            line for line in body.splitlines() if line.strip() not in boilerplate
        )
    return _collapse(_WRAPPED_UNIT.sub(r"\1 \2", "\n".join(kept)))


def pdf_to_text(data: bytes) -> str:
    """Extracts the text layer, refusing scans rather than silently returning ''."""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return _strip_running_furniture(pages)


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


def extract_source_text(source: LegalSource) -> str:
    """Downloads every part of a document and joins them in registry order."""
    parts: list[str] = []
    for url in source.urls:
        raw, _ = fetch_bytes(url)
        if source.fmt == "pdf":
            parts.append(pdf_to_text(raw))
        else:
            parts.append(
                trim_portal_chrome(html_to_text(raw.decode("utf-8", errors="replace")))
            )
    return "\n\n".join(part for part in parts if part)


def fetch_source(source: LegalSource, output_dir: Path) -> FetchReport:
    """Downloads, flattens, verifies and persists one document plus metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    text = extract_source_text(source)
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
                "amends": source.amends,
                "in_force": source.in_force,
                "format": source.fmt,
                "source_urls": list(source.urls),
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
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
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
