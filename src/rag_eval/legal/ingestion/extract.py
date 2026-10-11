"""Per-format extractors: each turns one source file into labelled blocks in reading order.

A block says what kind of content it carries, so the cleaner decides what to keep by label
rather than by guessing from flattened text. Footnotes and page furniture are recognised
here, where the source still says what they are: in Word they live in parts of their own,
in a PDF they are set apart by type size and position.

The Word reader renders a document the way Word displays it and consumes every piece of
body text: anything it cannot represent raises `ExtractionGapError` instead of vanishing,
and text typed in a legacy 8-bit Vietnamese font raises `LegacyEncodingError`.

The PDF reader is best effort and has known limits: furniture is recognised by recurrence
rather than position, a body-size page number below the footnotes hides them, multi-column
pages, rotated table cells and doubled ("fake bold") glyphs are not handled, and pages with
no text layer are skipped. Prefer a Word source whenever one exists.
"""

from __future__ import annotations

import collections
import io
import itertools
import re
import shutil
import statistics
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal
from xml.etree import ElementTree as ET

import pdfplumber
from pdfplumber.page import Page
from pdfplumber.utils import extract_text as chars_to_text

BlockKind = Literal["text", "table", "footnote", "furniture", "corrupt"]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str


class ExtractionGapError(ValueError):
    """Body text the extractor did not consume and no rule excludes; names the file, the enclosing construct and a sample."""


class LegacyEncodingError(ValueError):
    """Text typed in a legacy Vietnamese 8-bit font (TCVN3/VNI); the source must be converted to Unicode first."""


def extract(path: Path) -> list[Block]:
    """Blocks of one source file in reading order; raises ExtractionGapError / LegacyEncodingError instead of dropping text."""
    suffix = path.suffix.lower()
    if suffix in (".doc", ".docx"):
        return extract_word(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    raise ValueError(f"unsupported source format: {path.name}")


def markdown_table(rows: Sequence[Sequence[str]]) -> str:
    cleaned = [[" ".join(cell.split()).replace("|", "\\|") for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    lines = ["| " + " | ".join(padded[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in padded[1:]]
    return "\n".join(lines)


# --------------------------------------------------------------------------- Symbol fonts and legacy encodings

_SYMBOL_ORDER = (
    " !∀#∃%&∋()∗+,−./0123456789:;<=>?"
    "≅ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ[∴]⊥_"
    "‾αβχδεφγηιϕκλμνοπθρστυϖωξψζ{|}∼"
)
_SYMBOL_HIGH = (
    "€ϒ′≤⁄∞ƒ♣♦♥♠↔←↑→↓°±″≥×∝∂•÷≠≡≈…⏐⎯↵"
    "ℵℑℜ℘⊗⊕∅∩∪⊃⊇⊄⊂⊆∈∉∠∇®©™∏√⋅¬∧∨⇔⇐⇑⇒⇓"
    "◊〈®©™∑"
)

# Symbol-font characters by their 8-bit code. Only codes whose glyph is known are listed: an
# unlisted code raises rather than turning into a wrong character.
SYMBOL_FONTS: Final[dict[str, dict[int, str]]] = {
    "symbol": {0x20 + i: ch for i, ch in enumerate(_SYMBOL_ORDER)}
    | {0xA0 + i: ch for i, ch in enumerate(_SYMBOL_HIGH)}
    | {0xF1: "〉", 0xF2: "∫"},
    "wingdings": {
        0x20: " ", 0x6C: "●", 0x6E: "■", 0x6F: "□", 0x71: "❑", 0x72: "❒", 0x73: "⬧", 0x74: "⧫",
        0x75: "◆", 0x76: "❖", 0x77: "⬥", 0x9F: "•", 0xA1: "○", 0xA7: "▪", 0xA8: "◻", 0xD8: "➢",
        0xE8: "➔", 0xF0: "⇨", 0xFB: "✗", 0xFC: "✓", 0xFD: "☒", 0xFE: "☑",
    },
    # Recognised as symbol fonts so their glyphs never pass through as private-use characters;
    # no glyph is listed until one is confirmed, so each raises.
    "wingdings 2": {0x20: " "},
    "wingdings 3": {0x20: " "},
    "webdings": {0x20: " "},
}

_PRIVATE_USE_OFFSET = 0xF000


def symbol_table(font: str) -> dict[int, str] | None:
    """The decoding table of a symbol font, None for an ordinary text font."""
    return SYMBOL_FONTS.get(font.strip().lower())


def decode_symbol(source: str, font: str, code: int) -> str:
    """The Unicode character a symbol-font code shows; raises ExtractionGapError for a code the table lacks."""
    table = symbol_table(font)
    if table is None:
        return chr(code)
    eight_bit = code - _PRIVATE_USE_OFFSET if code >= _PRIVATE_USE_OFFSET else code
    if eight_bit not in table:
        raise ExtractionGapError(f"{source}: symbol {code:#06x} of font '{font}' has no known Unicode character")
    return table[eight_bit]


_LEGACY_FONT = re.compile(r"^\s*(?:\.vn|vni)", re.IGNORECASE)
_VIETNAMESE_LETTER = re.compile(r"[đĐăĂâÂêÊôÔơƠưƯẠ-ỹ]")
_LEGACY_CODE_POINT = re.compile(r"[¡-ª¬-¯²-¶¸-º¼-ÖØ-öø-ÿ]")


def check_legacy_encoding(source: str, font: str, text: str) -> None:
    """Raises LegacyEncodingError when text in a legacy Vietnamese font is 8-bit TCVN3/VNI rather than Unicode.

    A legacy font name alone proves nothing: documents keep `.VnTime` in their styles long
    after their text became Unicode. The text decides: TCVN3/VNI letters live in the
    Latin-1 range, and Unicode Vietnamese letters never appear in such text.
    """
    if _LEGACY_FONT.match(font) and _LEGACY_CODE_POINT.search(text) and not _VIETNAMESE_LETTER.search(text):
        raise LegacyEncodingError(
            f"{source}: text in legacy Vietnamese font '{font}' is not Unicode, e.g. '{text.strip()[:40]}'"
        )


# --------------------------------------------------------------------------- Word

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
_O = "{urn:schemas-microsoft-com:office:office}"
_NO_BORDER = {"nil", "none"}
_TEXT_TAGS = (f"{_W}t", f"{_M}t")
_TOC_STYLE = re.compile(r"^toc\s*\d$", re.IGNORECASE)


def extract_word(path: Path) -> list[Block]:
    """Reads a Word document; a legacy .doc is first saved as .docx by LibreOffice."""
    if path.suffix.lower() == ".docx":
        return _WordDocument(path.name, path.read_bytes()).blocks()
    soffice = shutil.which("soffice")
    if soffice is None:
        raise RuntimeError(f"LibreOffice (soffice) is required to read {path.name}")
    with tempfile.TemporaryDirectory() as tmp:
        profile = (Path(tmp) / "profile").as_uri()
        result = subprocess.run(
            [soffice, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "docx", "--outdir", tmp, str(path)],
            check=False,
            capture_output=True,
            timeout=600,
        )
        converted = Path(tmp) / f"{path.stem}.docx"
        if not converted.exists():
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"LibreOffice did not convert {path.name}: {stderr or f'exit code {result.returncode}'}")
        return _WordDocument(path.name, converted.read_bytes()).blocks()


def _attr(element: ET.Element | None, name: str) -> str | None:
    return None if element is None else element.get(f"{_W}{name}")


def _on(element: ET.Element | None) -> bool | None:
    """The value of an OOXML toggle property: None when absent, else whether it is switched on."""
    if element is None:
        return None
    return _attr(element, "val") not in ("0", "false", "off")


def _caps(r_pr: ET.Element) -> bool | None:
    """Whether a run-property element sets caps or small caps; None when it sets neither."""
    caps, small = _on(r_pr.find(f"{_W}caps")), _on(r_pr.find(f"{_W}smallCaps"))
    if caps is None and small is None:
        return None
    return bool(caps) or bool(small)


def _edge(borders: ET.Element | None, *names: str) -> bool | None:
    """Whether `borders` draws the named edge (a line that is not nil/none, zero-width or white); None when it does not say."""
    if borders is None:
        return None
    edge = next((e for name in names if (e := borders.find(f"{_W}{name}")) is not None), None)
    if edge is None:
        return None
    return (
        (_attr(edge, "val") or "none") not in _NO_BORDER
        and _attr(edge, "sz") != "0"
        and (_attr(edge, "color") or "").upper() != "FFFFFF"
    )


@dataclass(frozen=True)
class _Style:
    kind: str  # "paragraph", "character", "table" or "numbering"
    name: str
    based_on: str | None  # None: the style inherits from no other style
    element: ET.Element


@dataclass(frozen=True)
class _RunStyle:
    font: str  # effective ascii font family; "" when no rule names one
    hidden: bool  # effective w:vanish
    upper: bool  # effective w:caps or w:smallCaps


class _Styles:
    """styles.xml: style inheritance, effective run properties and effective table borders."""

    def __init__(self, root: ET.Element | None) -> None:
        self.by_id: dict[str, _Style] = {}
        self.default_table: str | None = None  # None: the document defines no default table style
        self.default_rpr: ET.Element | None = None  # None: no document-wide run defaults
        if root is None:
            return
        self.default_rpr = root.find(f"{_W}docDefaults/{_W}rPrDefault/{_W}rPr")
        for style in root.iter(f"{_W}style"):
            style_id = _attr(style, "styleId") or ""
            kind = _attr(style, "type") or "paragraph"
            self.by_id[style_id] = _Style(
                kind=kind,
                name=_attr(style.find(f"{_W}name"), "val") or "",
                based_on=_attr(style.find(f"{_W}basedOn"), "val"),
                element=style,
            )
            if kind == "table" and _attr(style, "default") in ("1", "true"):
                self.default_table = style_id

    def chain(self, style_id: str | None) -> list[_Style]:
        """The style and its ancestors, nearest first."""
        styles: list[_Style] = []
        seen: set[str] = set()
        while style_id and style_id in self.by_id and style_id not in seen:
            seen.add(style_id)
            style = self.by_id[style_id]
            styles.append(style)
            style_id = style.based_on
        return styles

    def is_toc(self, style_id: str | None) -> bool:
        style = self.by_id.get(style_id or "")
        return style is not None and bool(_TOC_STYLE.match(style.name) or _TOC_STYLE.match(style_id or ""))

    def run_style(self, run: ET.Element, paragraph_style: str | None) -> _RunStyle:
        r_pr = run.find(f"{_W}rPr")
        candidates: list[ET.Element | None] = [r_pr]
        if r_pr is not None:
            candidates += [s.element.find(f"{_W}rPr") for s in self.chain(_attr(r_pr.find(f"{_W}rStyle"), "val"))]
        candidates += [s.element.find(f"{_W}rPr") for s in self.chain(paragraph_style)]
        candidates.append(self.default_rpr)
        present = [s for s in candidates if s is not None]
        return _RunStyle(
            font=next((f for s in present if (f := _attr(s.find(f"{_W}rFonts"), "ascii"))), ""),
            hidden=next((v for s in present if (v := _on(s.find(f"{_W}vanish"))) is not None), False),
            upper=next((v for s in present if (v := _caps(s)) is not None), False),
        )

    def table_borders(self, tbl_pr: ET.Element | None) -> ET.Element | None:
        """The table-level borders in effect; None when neither the table nor its style declares any."""
        direct = tbl_pr.find(f"{_W}tblBorders") if tbl_pr is not None else None
        if direct is not None:
            return direct
        style_id = _attr(tbl_pr.find(f"{_W}tblStyle"), "val") if tbl_pr is not None else None
        for style in self.chain(style_id or self.default_table):
            borders = style.element.find(f"{_W}tblPr/{_W}tblBorders")
            if borders is not None:
                return borders
            for conditional in style.element.findall(f"{_W}tblStylePr"):
                if _attr(conditional, "type") == "wholeTable":
                    borders = conditional.find(f"{_W}tblPr/{_W}tblBorders")
                    if borders is not None:
                        return borders
        return None

    def cell_borders(self, tbl_pr: ET.Element | None) -> ET.Element | None:
        """Cell borders the table's style chain applies to every cell; None when no style in the chain sets any."""
        style_id = _attr(tbl_pr.find(f"{_W}tblStyle"), "val") if tbl_pr is not None else None
        for style in self.chain(style_id or self.default_table):
            borders = style.element.find(f"{_W}tcPr/{_W}tcBorders")
            if borders is not None:
                return borders
            for conditional in style.element.findall(f"{_W}tblStylePr"):
                if _attr(conditional, "type") == "wholeTable":
                    borders = conditional.find(f"{_W}tcPr/{_W}tcBorders")
                    if borders is not None:
                        return borders
        return None

    def numbering_of(self, style_id: str | None) -> tuple[str | None, int | None]:
        """(numId, ilvl) a paragraph style applies through its chain; each None when no style in the chain sets it."""
        num_id: str | None = None
        ilvl: int | None = None
        for style in self.chain(style_id):
            num_pr = style.element.find(f"{_W}pPr/{_W}numPr")
            if num_pr is None:
                continue
            if num_id is None:
                num_id = _attr(num_pr.find(f"{_W}numId"), "val")
            if ilvl is None and (value := _attr(num_pr.find(f"{_W}ilvl"), "val")) is not None:
                ilvl = int(value)
        return num_id, ilvl


@dataclass(frozen=True)
class _Level:
    start: int
    fmt: str
    text: str
    restart: int | None  # None: restart after any shallower level advances (Word's default); 0: never restart
    legal: bool  # w:isLgl: every referenced level is rendered as a decimal
    suffix: str  # what follows the number: " " or ""
    style: str | None  # the paragraph style bound to this level; None when the level is bound to none


def _parse_level(lvl: ET.Element) -> _Level:
    restart = _attr(lvl.find(f"{_W}lvlRestart"), "val")
    return _Level(
        start=int(_attr(lvl.find(f"{_W}start"), "val") or "1"),
        fmt=_attr(lvl.find(f"{_W}numFmt"), "val") or "decimal",
        text=_attr(lvl.find(f"{_W}lvlText"), "val") or "",
        restart=int(restart) if restart is not None else None,
        legal=bool(_on(lvl.find(f"{_W}isLgl"))),
        suffix="" if _attr(lvl.find(f"{_W}suff"), "val") == "nothing" else " ",
        style=_attr(lvl.find(f"{_W}pStyle"), "val"),
    )


@dataclass
class _Numbering:
    """Renders Word's automatic list numbers exactly as Word displays them."""

    abstract_levels: dict[str, dict[int, _Level]] = field(default_factory=dict)
    abstract_link: dict[str, str] = field(default_factory=dict)  # abstract id -> numbering style it links to
    abstract_of: dict[str, str] = field(default_factory=dict)  # num id -> abstract id
    level_override: dict[str, dict[int, _Level]] = field(default_factory=dict)
    start_override: dict[tuple[str, int], int] = field(default_factory=dict)
    counters: dict[str, dict[int, int]] = field(default_factory=dict)
    style_num: dict[str, str] = field(default_factory=dict)  # numbering style id -> num id it carries

    @classmethod
    def parse(cls, xml: bytes | None, styles: _Styles) -> _Numbering:
        numbering = cls()
        for style_id, style in styles.by_id.items():
            if style.kind == "numbering":
                num_id = _attr(style.element.find(f"{_W}pPr/{_W}numPr/{_W}numId"), "val")
                if num_id:
                    numbering.style_num[style_id] = num_id
        if xml is None:
            return numbering
        root = ET.fromstring(xml)
        for abstract in root.iter(f"{_W}abstractNum"):
            abstract_id = _attr(abstract, "abstractNumId") or ""
            numbering.abstract_levels[abstract_id] = {
                int(_attr(lvl, "ilvl") or "0"): _parse_level(lvl) for lvl in abstract.findall(f"{_W}lvl")
            }
            link = _attr(abstract.find(f"{_W}numStyleLink"), "val")
            if link:
                numbering.abstract_link[abstract_id] = link
        for num in root.iter(f"{_W}num"):
            num_id = _attr(num, "numId") or ""
            numbering.abstract_of[num_id] = _attr(num.find(f"{_W}abstractNumId"), "val") or ""
            for override in num.findall(f"{_W}lvlOverride"):
                ilvl = int(_attr(override, "ilvl") or "0")
                start = _attr(override.find(f"{_W}startOverride"), "val")
                if start is not None:
                    numbering.start_override[(num_id, ilvl)] = int(start)
                lvl = override.find(f"{_W}lvl")
                if lvl is not None:
                    numbering.level_override.setdefault(num_id, {})[ilvl] = _parse_level(lvl)
        return numbering

    def _levels(self, num_id: str) -> dict[int, _Level]:
        abstract_id = self.abstract_of.get(num_id, "")
        seen: set[str] = set()
        while abstract_id in self.abstract_link and abstract_id not in seen:
            seen.add(abstract_id)
            linked_num = self.style_num.get(self.abstract_link[abstract_id], "")
            abstract_id = self.abstract_of.get(linked_num, "")
        return self.abstract_levels.get(abstract_id, {}) | self.level_override.get(num_id, {})

    def _counter_key(self, num_id: str) -> str:
        if num_id in self.level_override or any(k[0] == num_id for k in self.start_override):
            return f"num:{num_id}"
        return f"abstract:{self.abstract_of.get(num_id, '')}"

    def level_of_style(self, num_id: str, style_id: str) -> int | None:
        """The ilvl whose lvl/pStyle names style_id in num_id's numbering; None when no level is bound to that style."""
        return next((ilvl for ilvl, level in self._levels(num_id).items() if level.style == style_id), None)

    def label(self, num_id: str, ilvl: int) -> tuple[str, str]:
        """(number, suffix) of the next paragraph at (num_id, ilvl); ("", "") when the level shows no number."""
        levels = self._levels(num_id)
        if ilvl not in levels:
            return "", ""
        counters = self.counters.setdefault(self._counter_key(num_id), {})
        level = levels[ilvl]
        counters[ilvl] = counters[ilvl] + 1 if ilvl in counters else self.start_override.get((num_id, ilvl), level.start)
        for deeper in [k for k in counters if k > ilvl]:
            restart = levels[deeper].restart if deeper in levels else None
            if restart is None or (restart > 0 and ilvl < restart):
                del counters[deeper]
        if level.fmt == "none":
            return "", ""
        if level.fmt == "bullet":
            bullet = level.text.strip()
            return (bullet if bullet and not 0xE000 <= ord(bullet[0]) <= 0xF8FF else "-"), level.suffix

        def render(match: re.Match[str]) -> str:
            at = int(match.group(1)) - 1
            spec = levels.get(at)
            value = counters.get(at, spec.start if spec else 1)
            return _format_number(value, "decimal" if level.legal or spec is None else spec.fmt)

        return re.sub(r"%(\d)", render, level.text), level.suffix


def _format_number(value: int, fmt: str) -> str:
    if fmt in ("lowerLetter", "upperLetter"):
        letters = ""
        n = value
        while n > 0:
            n, rem = divmod(n - 1, 26)
            letters = chr(ord("a") + rem) + letters
        return letters if fmt == "lowerLetter" else letters.upper()
    if fmt in ("lowerRoman", "upperRoman"):
        numerals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
        out, n = "", value
        for amount, numeral in numerals:
            while n >= amount:
                out, n = out + numeral, n - amount
        return out if fmt == "lowerRoman" else out.upper()
    if fmt == "decimalZero":
        return f"{value:02d}"
    return str(value)


def _wrap(math: str) -> str:
    return math if len(math) <= 1 or re.fullmatch(r"[\w.,]+", math) else f"({math})"


class _WordDocument:
    def __init__(self, source: str, data: bytes) -> None:
        self._source = source
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            parts = {name.replace("\\", "/"): name for name in archive.namelist()}
            if "word/document.xml" not in parts:
                raise ValueError(f"{source}: not a Word document, word/document.xml is missing")
            self._document = ET.fromstring(archive.read(parts["word/document.xml"]))
            styles_xml = archive.read(parts["word/styles.xml"]) if "word/styles.xml" in parts else None
            numbering_xml = archive.read(parts["word/numbering.xml"]) if "word/numbering.xml" in parts else None
        self._styles = _Styles(ET.fromstring(styles_xml) if styles_xml is not None else None)
        self._numbering = _Numbering.parse(numbering_xml, self._styles)
        self._consumed: set[int] = set()
        self._excluded: set[int] = set()
        self._fields: list[list[str]] = []  # open complex fields, each holding its instruction text

    # ---- coverage

    def _exclude(self, element: ET.Element) -> None:
        self._excluded.update(id(t) for t in element.iter() if t.tag in _TEXT_TAGS)

    def _check_coverage(self, body: ET.Element) -> None:
        missed = [
            t for t in body.iter() if t.tag in _TEXT_TAGS and (t.text or "").strip() and id(t) not in self._consumed | self._excluded
        ]
        if not missed:
            return
        parent = {child: node for node in body.iter() for child in node}
        construct, node = "", missed[0]
        while node in parent and not construct:
            node = parent[node]
            if node.tag not in (f"{_W}r", f"{_W}p", f"{_M}r"):
                construct = node.tag.split("}")[-1]
        raise ExtractionGapError(
            f"{self._source}: {len(missed)} text run(s) not consumed, e.g. inside w:{construct or 'body'}: '{(missed[0].text or '').strip()[:60]}'"
        )

    # ---- blocks

    def blocks(self) -> list[Block]:
        body = self._document.find(f"{_W}body")
        if body is None:
            raise ValueError(f"{self._source}: Word document has no body")
        blocks = list(self._walk(body, furniture=False))
        self._check_coverage(body)
        return blocks

    def _walk(self, container: ET.Element, furniture: bool) -> Iterator[Block]:
        carried = ""  # text of paragraphs whose mark was deleted, joined to the next paragraph
        for child in container:
            tag = child.tag
            if tag == f"{_W}p":
                kind, text, boxes = self._paragraph(child, furniture)
                if self._mark_deleted(child):
                    carried = f"{carried} {text}".strip()
                    continue
                text = f"{carried} {text}".strip()
                carried = ""
                if text:
                    yield Block(kind, text)
                for box in boxes:
                    yield from self._walk(box, furniture)
            elif tag == f"{_W}tbl":
                yield from self._table(child, furniture)
            elif tag == f"{_W}sdt":
                content = child.find(f"{_W}sdtContent")
                gallery = _attr(child.find(f"{_W}sdtPr/{_W}docPartObj/{_W}docPartGallery"), "val")
                if content is not None:
                    yield from self._walk(content, furniture or gallery == "Table of Contents")
            elif tag in (f"{_W}customXml", f"{_W}ins", f"{_W}moveTo"):
                yield from self._walk(child, furniture)
            elif tag in (f"{_W}del", f"{_W}moveFrom"):
                self._exclude(child)
            elif tag in (f"{_M}oMath", f"{_M}oMathPara"):
                math = self._math(child).strip()
                if math:
                    yield Block("furniture" if furniture else "text", math)
            elif tag == f"{_W}altChunk":
                raise ExtractionGapError(f"{self._source}: w:altChunk imports content from another part, which is not read")
        if carried:
            yield Block("furniture" if furniture else "text", carried)

    @staticmethod
    def _mark_deleted(paragraph: ET.Element) -> bool:
        return paragraph.find(f"{_W}pPr/{_W}rPr/{_W}del") is not None

    def _paragraph(self, paragraph: ET.Element, furniture: bool) -> tuple[BlockKind, str, list[ET.Element]]:
        p_pr = paragraph.find(f"{_W}pPr")
        style = _attr(p_pr.find(f"{_W}pStyle"), "val") if p_pr is not None else None
        in_toc_field = self._in_toc_field()
        boxes: list[ET.Element] = []
        text = "".join(self._runs(paragraph, style, boxes)).strip()
        in_toc_field = in_toc_field or self._in_toc_field()
        mark_hidden = p_pr is not None and bool(_on(p_pr.find(f"{_W}rPr/{_W}vanish")))
        counted = not self._mark_deleted(paragraph) and not (mark_hidden and not text)
        number, suffix = self._label(p_pr, style) if counted else ("", "")
        if number and text:
            text = f"{number}{suffix}{text}"
        kind: BlockKind = "furniture" if furniture or in_toc_field or self._styles.is_toc(style) else "text"
        return kind, text, boxes

    def _label(self, p_pr: ET.Element | None, style: str | None) -> tuple[str, str]:
        num_pr = p_pr.find(f"{_W}numPr") if p_pr is not None else None
        style_num, style_ilvl = self._styles.numbering_of(style)
        num_id = _attr(num_pr.find(f"{_W}numId"), "val") if num_pr is not None else None
        ilvl_value = _attr(num_pr.find(f"{_W}ilvl"), "val") if num_pr is not None else None
        num_id = num_id or style_num
        if not num_id or num_id == "0":
            return "", ""
        if ilvl_value is not None:
            ilvl = int(ilvl_value)
        elif style is not None and (bound := self._numbering.level_of_style(num_id, style)) is not None:
            ilvl = bound
        else:
            ilvl = style_ilvl or 0
        return self._numbering.label(num_id, ilvl)

    def _in_toc_field(self) -> bool:
        return any("".join(instr).strip().upper().startswith("TOC") for instr in self._fields)

    # ---- runs

    def _runs(self, element: ET.Element, style: str | None, boxes: list[ET.Element]) -> Iterator[str]:
        for child in element:
            tag = child.tag
            if tag in (f"{_W}pPr", f"{_W}rPr", f"{_W}sdtPr"):
                continue
            if tag == f"{_W}r":
                run_style = self._styles.run_style(child, style)
                if run_style.hidden:
                    self._exclude(child)
                    continue
                for part in self._run_content(child, run_style, boxes):
                    yield part.upper() if run_style.upper else part
            elif tag in (f"{_W}del", f"{_W}moveFrom"):
                self._exclude(child)
            elif tag in (f"{_M}oMath", f"{_M}oMathPara"):
                yield f" {self._math(child).strip()} "
            else:
                yield from self._runs(child, style, boxes)

    def _run_content(self, run: ET.Element, style: _RunStyle, boxes: list[ET.Element]) -> Iterator[str]:
        for child in run:
            tag = child.tag
            if tag == f"{_W}t":
                self._consumed.add(id(child))
                text = child.text or ""
                if symbol_table(style.font) is not None:
                    text = "".join(decode_symbol(self._source, style.font, ord(ch)) for ch in text)
                else:
                    check_legacy_encoding(self._source, style.font, text)
                yield text
            elif tag in (f"{_W}tab", f"{_W}ptab", f"{_W}br", f"{_W}cr"):
                yield " "
            elif tag == f"{_W}noBreakHyphen":
                yield "-"
            elif tag == f"{_W}sym":
                code = _attr(child, "char")
                if code:
                    yield decode_symbol(self._source, _attr(child, "font") or "Symbol", int(code, 16))
            elif tag == f"{_W}fldChar":
                kind = _attr(child, "fldCharType")
                if kind == "begin":
                    self._fields.append([])
                elif kind == "end" and self._fields:
                    self._fields.pop()
            elif tag == f"{_W}instrText":
                if self._fields:
                    self._fields[-1].append(child.text or "")
            elif tag == f"{_W}object":
                ole = child.find(f".//{_O}OLEObject")
                prog_id = ole.get("ProgID", "") if ole is not None else ""
                if prog_id.startswith("Equation."):
                    raise ExtractionGapError(f"{self._source}: an equation object ({prog_id}) has no text to read")
                boxes.extend(self._text_boxes(child))
            elif tag in (f"{_W}drawing", f"{_W}pict", f"{_MC}AlternateContent"):
                boxes.extend(self._text_boxes(child))

    def _text_boxes(self, element: ET.Element) -> Iterator[ET.Element]:
        """Text-box contents under `element`, outermost only, never from an AlternateContent fallback."""
        for child in element:
            if child.tag == f"{_MC}Fallback":
                self._exclude(child)
            elif child.tag == f"{_W}txbxContent":
                yield child
            else:
                yield from self._text_boxes(child)

    def _math(self, element: ET.Element) -> str:
        tag = element.tag
        if tag == f"{_M}t":
            self._consumed.add(id(element))
            return element.text or ""
        if tag.endswith("Pr"):
            return ""
        part = {child.tag.split("}")[-1]: child for child in element}

        def sub(name: str) -> str:
            return self._math(part[name]) if name in part else ""

        if tag == f"{_M}f":
            return f"{_wrap(sub('num'))}/{_wrap(sub('den'))}"
        if tag == f"{_M}sSup":
            return f"{sub('e')}^{_wrap(sub('sup'))}"
        if tag == f"{_M}sSub":
            return f"{sub('e')}_{_wrap(sub('sub'))}"
        if tag == f"{_M}sSubSup":
            return f"{sub('e')}_{_wrap(sub('sub'))}^{_wrap(sub('sup'))}"
        if tag == f"{_M}rad":
            return f"√({sub('e')})"
        if tag == f"{_M}d":
            props = element.find(f"{_M}dPr")
            begin = (props.find(f"{_M}begChr") if props is not None else None)
            end = (props.find(f"{_M}endChr") if props is not None else None)
            opening = begin.get(f"{_M}val", "(") if begin is not None else "("
            closing = end.get(f"{_M}val", ")") if end is not None else ")"
            return opening + ", ".join(self._math(e) for e in element.findall(f"{_M}e")) + closing
        return "".join(self._math(child) for child in element)

    # ---- tables

    @staticmethod
    def _unwrap(element: ET.Element, tag: str) -> Iterator[ET.Element]:
        """`tag` children of `element`, looking through content controls and custom XML."""
        for child in element:
            if child.tag == tag:
                yield child
            elif child.tag in (f"{_W}sdt", f"{_W}customXml"):
                inner = child.find(f"{_W}sdtContent") if child.tag == f"{_W}sdt" else child
                if inner is not None:
                    yield from _WordDocument._unwrap(inner, tag)

    def _table(self, table: ET.Element, furniture: bool) -> Iterator[Block]:
        row_elements = list(self._unwrap(table, f"{_W}tr"))
        rows = [list(self._unwrap(row, f"{_W}tc")) for row in row_elements]
        width = max((sum(self._span(cell) for cell in cells) for cells in rows), default=0)
        if width <= 1 or not self._is_data(table, row_elements, rows):
            for cells in rows:
                for cell in cells:
                    yield from self._walk(cell, furniture)
            return
        matrix: list[list[str]] = []
        nested: list[ET.Element] = []
        above: dict[int, str] = {}
        for cells in rows:
            line: list[str] = []
            for cell in cells:
                column = len(line)
                v_merge = cell.find(f"{_W}tcPr/{_W}vMerge")
                text = self._cell_text(cell, nested)
                if v_merge is not None and _attr(v_merge, "val") != "restart":
                    text = above.get(column, "")
                above[column] = text
                line.append(text)
                line.extend([""] * (self._span(cell) - 1))
            matrix.append(line)
        rendered = markdown_table(matrix)
        if rendered:
            yield Block("furniture" if furniture else "table", rendered)
        for inner in nested:
            yield from self._table(inner, furniture)

    @staticmethod
    def _span(cell: ET.Element) -> int:
        return int(_attr(cell.find(f"{_W}tcPr/{_W}gridSpan"), "val") or "1")

    def _cell_text(self, cell: ET.Element, nested: list[ET.Element]) -> str:
        texts: list[str] = []
        for child in cell:
            if child.tag == f"{_W}tbl":
                nested.append(child)
            elif child.tag in (f"{_W}p", f"{_W}sdt", f"{_W}customXml"):
                texts += [block.text for block in self._walk(_single(child), furniture=False)]
        return " ".join(texts)

    def _is_data(self, table: ET.Element, row_elements: list[ET.Element], rows: list[list[ET.Element]]) -> bool:
        """A table whose cells are drawn as a grid of boxes holds data; otherwise it only lays out text.

        Each edge of a cell is decided, nearest first, by the cell's own `tcBorders`, the cell
        borders of the table style, then its row's property exceptions (`tblPrEx`) or the
        table's borders (direct, style chain, default table style): outer edges from
        top/left/bottom/right, inner ones from insideH/insideV. An edge shared by two cells is
        drawn when either draws it. A cell is boxed when all four of its edges are drawn, and
        the table is data when its boxed cells span at least two rows and two columns: a lone
        framed photo box, or a rule under a heading, is decoration.
        """
        tbl_pr = table.find(f"{_W}tblPr")
        table_borders = self._styles.table_borders(tbl_pr)
        style_cells = self._styles.cell_borders(tbl_pr)
        width = max((sum(self._span(cell) for cell in cells) for cells in rows), default=0)
        horizontal: set[tuple[int, int]] = set()  # (row boundary, grid column) segments drawn
        vertical: set[tuple[int, int]] = set()  # (row, column boundary) segments drawn
        placed: list[tuple[int, int, int]] = []  # (row, first grid column, span)

        def drawn(own: ET.Element | None, level: ET.Element | None, names: tuple[str, ...], level_name: str) -> bool:
            for borders in (own, style_cells):
                if (value := _edge(borders, *names)) is not None:
                    return value
            return bool(_edge(level, level_name))

        for r, (row, cells) in enumerate(zip(row_elements, rows, strict=True)):
            row_borders = row.find(f"{_W}tblPrEx/{_W}tblBorders")
            level = row_borders if row_borders is not None else table_borders
            column = 0
            for cell in cells:
                span = self._span(cell)
                own = cell.find(f"{_W}tcPr/{_W}tcBorders")
                columns = range(column, column + span)
                if drawn(own, level, ("top",), "top" if r == 0 else "insideH"):
                    horizontal.update((r, c) for c in columns)
                if drawn(own, level, ("bottom",), "bottom" if r == len(rows) - 1 else "insideH"):
                    horizontal.update((r + 1, c) for c in columns)
                if drawn(own, level, ("left", "start"), "left" if column == 0 else "insideV"):
                    vertical.add((r, column))
                if drawn(own, level, ("right", "end"), "right" if column + span == width else "insideV"):
                    vertical.add((r, column + span))
                placed.append((r, column, span))
                column += span
        boxed = [
            (r, column)
            for r, column, span in placed
            if all((r, c) in horizontal and (r + 1, c) in horizontal for c in range(column, column + span))
            and (r, column) in vertical
            and (r, column + span) in vertical
        ]
        return len({r for r, _ in boxed}) >= 2 and len({c for _, c in boxed}) >= 2


def _single(element: ET.Element) -> ET.Element:
    """A container holding just `element`, so the block walker can read one child."""
    holder = ET.Element("holder")
    holder.append(element)
    return holder


# --------------------------------------------------------------------------- PDF


@dataclass(frozen=True)
class _Line:
    top: float
    x0: float
    x1: float
    size: float
    text: str
    starts_with_small_digit: bool
    marker_only: bool  # a superscript footnote number set on a row of its own


def extract_pdf(path: Path) -> list[Block]:
    """Reads a text-layer PDF, labelling footnotes and page furniture by type size and position."""
    with pdfplumber.open(path) as pdf:
        pages = list(pdf.pages)
        body_size = _mode([round(c["size"], 1) for page in pages for c in page.chars])
        laid_out = [_page_lines(path.name, page) for page in pages]
        furniture = _running_edges([lines for lines, _ in laid_out])
        blocks: list[Block] = []
        paragraph: list[str] = []
        body_lines = [line for lines, _ in laid_out for line in lines if line.size >= body_size and not line.marker_only]
        margin = _mode([round(line.x0) for line in body_lines])
        right = _mode([round(line.x1) for line in body_lines])
        pitch = _mode(
            [round(b.top - a.top) for lines, _ in laid_out for a, b in itertools.pairwise(lines) if b.top > a.top]
        )
        em = body_size
        previous: _Line | None = None

        def starts_paragraph(line: _Line) -> bool:
            if previous is None or not paragraph:
                return True
            indented = line.x0 >= margin + em / 2
            previous_short = previous.x1 < right - 2 * em
            spaced = line.top > previous.top and line.top - previous.top > pitch + em / 2
            return indented or previous_short or spaced

        def flush() -> None:
            if paragraph:
                blocks.append(Block("text", " ".join(paragraph)))
                paragraph.clear()

        for lines, tables in laid_out:
            notes_from = _footnote_start(lines, body_size)
            items: list[tuple[float, _Line | str]] = [(line.top, line) for line in lines] + [(top, table) for top, table in tables]
            for _, item in sorted(items, key=lambda pair: pair[0]):
                if isinstance(item, str):
                    flush()
                    blocks.append(Block("table", item))
                    continue
                if _edge_key(item.text) in furniture and (item is lines[0] or item is lines[-1]):
                    blocks.append(Block("furniture", item.text))
                    continue
                if notes_from is not None and item.top >= notes_from:
                    flush()
                    blocks.append(Block("footnote", item.text))
                    continue
                if item.marker_only:
                    continue
                if _is_corrupt(item.text):
                    flush()
                    blocks.append(Block("corrupt", item.text))
                    continue
                if starts_paragraph(item):
                    flush()
                paragraph.append(item.text)
                previous = item
        flush()
    return blocks


def _mode(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("PDF has no text layer")
    return collections.Counter(values).most_common(1)[0][0]


def _font_family(fontname: str) -> str:
    """A PDF font's family: the name without its subset tag ("ABCDEF+") and style suffix."""
    return re.split(r"[,-]", fontname.split("+")[-1])[0]


def _decoded(source: str, char: dict) -> dict:
    """The char with a symbol-font glyph replaced by the Unicode character it shows."""
    family = _font_family(str(char.get("fontname", "")))
    if symbol_table(family) is None or not char["text"]:
        return char
    return {**char, "text": decode_symbol(source, family, ord(str(char["text"])[0]))}


def _page_lines(source: str, page: Page) -> tuple[list[_Line], list[tuple[float, str]]]:
    tables: list[tuple[float, str]] = []
    boxes: list[tuple[float, float, float, float]] = []
    for table in page.find_tables(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"}):
        rows = [[str(cell or "") for cell in row] for row in table.extract()]
        if sum(1 for row in rows if sum(1 for cell in row if cell.strip()) >= 2) >= 2:
            rendered = markdown_table(rows)
            if rendered:
                x0, top, x1, bottom = (float(v) for v in table.bbox)
                tables.append((top, rendered))
                boxes.append((x0, top, x1, bottom))
    lines: list[_Line] = []
    for raw in page.extract_text_lines(return_chars=True):
        chars = [c for c in raw["chars"] if c["text"].strip()]
        if not chars:
            continue
        mid_y = (float(raw["top"]) + float(raw["bottom"])) / 2
        if any(x0 <= float(raw["x0"]) <= x1 and top <= mid_y <= bottom for x0, top, x1, bottom in boxes):
            continue
        size = _mode([round(float(c["size"]), 1) for c in chars])
        baseline = statistics.median(float(c["bottom"]) for c in chars if round(float(c["size"]), 1) == size)
        superscript = [
            c for c in raw["chars"] if float(c["size"]) < size and float(c["bottom"]) < baseline - 1 and str(c["text"]).isdigit()
        ]
        line_top, line_bottom = float(raw["top"]), float(raw["bottom"])
        band = [
            c
            for c in page.chars
            if float(c["top"]) < line_bottom and float(c["bottom"]) > line_top and c not in superscript
            and float(raw["x0"]) - size <= float(c["x0"]) <= float(raw["x1"]) + size
        ]
        band = [_decoded(source, c) for c in band]
        text = " ".join(chars_to_text(sorted(band, key=lambda c: float(c["x0"])), keep_blank_chars=True).split())
        for family in {_font_family(str(c.get("fontname", ""))) for c in band}:
            check_legacy_encoding(source, family, text)
        first = chars[0]
        lines.append(
            _Line(
                top=float(raw["top"]),
                x0=float(raw["x0"]),
                x1=float(raw["x1"]),
                size=size,
                text=text or "".join(str(c["text"]) for c in chars),
                starts_with_small_digit=str(first["text"]).isdigit() and (float(first["size"]) < size or not text),
                marker_only=not text,
            )
        )
    return lines, tables


_DIACRITIC = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]")
_OCR_JUNK = re.compile(r"[\\~${}|]")


def _is_corrupt(text: str) -> bool:
    """A long line with OCR junk and no Vietnamese diacritics: the text layer of a scanned page."""
    return len(text) > 40 and _OCR_JUNK.search(text) is not None and _DIACRITIC.search(text.lower()) is None


def _edge_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.strip())


def _running_edges(pages: Sequence[Sequence[_Line]]) -> set[str]:
    """Page-edge lines that recur across pages (running headers, footers, page numbers)."""
    seen = collections.Counter(
        key for lines in pages if lines for key in {_edge_key(lines[0].text), _edge_key(lines[-1].text)}
    )
    return {key for key, count in seen.items() if count >= 2 or key == "#"}


def _footnote_start(lines: Sequence[_Line], body_size: float) -> float | None:
    """Top of the page's footnote area: a trailing run of smaller type that opens with a small footnote number."""
    start: float | None = None
    for line in reversed(lines):
        if line.size >= body_size:
            break
        if line.starts_with_small_digit:
            start = line.top
    return start
