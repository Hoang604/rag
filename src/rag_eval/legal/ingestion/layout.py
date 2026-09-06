"""PDF Layout and Table Extractor for Vietnamese Statutory Documents.

Isolates table bounding boxes to eliminate table text duplication and formats tables
into clean Markdown pipe tables embedded into the document stream in reading order.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutBlock:
    """Represents a discrete structural layout block extracted from a document page."""

    block_type: Literal["PARAGRAPH", "TABLE"]
    content: str
    top_y: float
    page_number: int


MIN_MULTI_COLUMN_ROWS = 2


def is_content_table(table_data: list[list[Any]]) -> bool:
    """True for a detected region that is a real table rather than framed prose.

    Gazette PDFs rule their text column, so `lines` detection reports ordinary
    statutory paragraphs as single-column tables: 119 of 276 detections across
    the corpus. Emitting those as Markdown would turn law into `| kinh doanh
    vận tải... |`, destroying the paragraph and the lexer's view of it.
    """
    multi = 0
    for row in table_data:
        if sum(1 for cell in row if cell and str(cell).strip()) >= 2:
            multi += 1
            if multi >= MIN_MULTI_COLUMN_ROWS:
                return True
    return False


def rotated_cell_text(page: Any, bbox: tuple[float, ...] | None) -> str:
    """Rebuilds a cell typeset bottom-to-top; "" when the cell is upright.

    pdfplumber orders characters left to right, so a rotated header comes out
    reversed: "Biển tròn" as "nòrt nểiB". Lines run along x and characters run
    up the y axis, so sorting the cell by either axis alone interleaves them.
    """
    if bbox is None:
        return ""
    x0, top, x1, bottom = (float(v) for v in bbox)
    chars = [
        c
        for c in page.chars
        if x0 - 1 <= c["x0"]
        and c["x1"] <= x1 + 1
        and top - 1 <= c["top"]
        and c["bottom"] <= bottom + 1
    ]
    if not chars or all(c.get("upright") for c in chars):
        return ""
    columns: dict[int, list[Any]] = {}
    for c in chars:
        columns.setdefault(round(float(c["x0"]) / 4), []).append(c)
    parts = [
        "".join(str(c["text"]) for c in sorted(group, key=lambda c: -float(c["top"])))
        for _, group in sorted(columns.items())
    ]
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def merge_stacked_header(rows: list[list[str]]) -> list[list[str]]:
    """Folds a two-tier header into one row, carrying the spanning label down.

    A merged header cell spans sub-columns -- "Đèn đơn" over "Công suất" and
    "Cường độ sáng" -- and Markdown has no colspan, so the second tier would
    become a data row and every figure under it would lose the group it
    belongs to. Requires the second row to start empty, which a data row in
    these numbered tables never does.
    """
    if len(rows) < 3:
        return rows
    first, second = rows[0], rows[1]
    blanks = [i for i, cell in enumerate(first) if not cell.strip()]
    if not blanks or not second or second[0].strip():
        return rows
    if not all(i < len(second) and second[i].strip() for i in blanks):
        return rows

    spanning: list[str] = []
    carried = ""
    for cell in first:
        if cell.strip():
            carried = cell.strip()
        spanning.append(carried)

    merged = [
        f"{spanning[i]} {second[i].strip()}".strip()
        if i < len(second) and second[i].strip()
        else first[i]
        for i in range(len(first))
    ]
    return [merged, *rows[2:]]


# A gazette PDF places each glyph of a narrow header cell separately, and the
# extractor reads the gaps as spaces: "Cường độ" arrives as "C ư ờ n g độ",
# which no query will ever match. Only runs of three or more single letters are
# joined, so "biển báo, D" keeps its lone label.
_LETTER_SPACED = re.compile(r"(?<!\S)((?:[^\W\d_]\s){2,}[^\W\d_])(?!\S)")


def collapse_letter_spacing(text: str) -> str:
    """Joins runs of space-separated single letters back into words.

    An all-uppercase run is left alone: "A B C" is a legend, not a word whose
    glyphs the PDF happened to place separately.
    """

    def join(match: re.Match[str]) -> str:
        run = match.group(1)
        return run if run.isupper() else run.replace(" ", "")

    return _LETTER_SPACED.sub(join, text)


class PDFLayoutExtractor:
    """Extracts non-overlapping paragraph text and Markdown tables from PDF files."""

    def __init__(
        self,
        table_horizontal_strategy: str = "lines",
        table_vertical_strategy: str = "lines",
    ) -> None:
        self.table_settings = {
            "vertical_strategy": table_vertical_strategy,
            "horizontal_strategy": table_horizontal_strategy,
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 3,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        }

    def _format_markdown_table(self, table_data: list[list[Any]]) -> str:
        """Converts raw 2D cell matrix into a well-formed Markdown pipe table.

        Handles newlines inside cells and escapes raw pipe characters to prevent layout breakage.
        """
        if not table_data:
            return ""

        clean_rows: list[list[str]] = []
        for row in table_data:
            clean_row: list[str] = []
            for cell in row:
                if cell is None:
                    clean_row.append("")
                else:
                    # Flatten multi-line cells to single line with spaces and escape pipe
                    text = str(cell).strip()
                    text = (
                        text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                    )
                    text = " ".join(text.split())
                    text = collapse_letter_spacing(text)
                    text = text.replace("|", "\\|")
                    clean_row.append(text)
            if any(cell for cell in clean_row):
                clean_rows.append(clean_row)

        if not clean_rows:
            return ""

        max_cols = max(len(row) for row in clean_rows)
        # Pad shorter rows
        padded_rows = [row + [""] * (max_cols - len(row)) for row in clean_rows]
        padded_rows = merge_stacked_header(padded_rows)

        lines: list[str] = []
        # Header row
        header = padded_rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        # Data rows
        for row in padded_rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def extract_blocks_from_page(
        self, page: Any, page_number: int
    ) -> list[LayoutBlock]:
        """Extracts non-overlapping text and table blocks from a single PDF page."""
        blocks: list[LayoutBlock] = []

        try:
            found_tables = page.find_tables(table_settings=self.table_settings)
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.debug(
                "Failed finding tables with custom settings on page %d: %s",
                page_number,
                exc,
            )
            found_tables = page.find_tables()

        if not found_tables:
            raw_text = (page.extract_text(layout=False) or "").strip()
            if raw_text:
                blocks.append(
                    LayoutBlock(
                        block_type="PARAGRAPH",
                        content=raw_text,
                        top_y=0.0,
                        page_number=page_number,
                    )
                )
            return blocks

        # Filtered before any region is claimed: a detection that is not a real
        # table has to stay in the paragraph flow, or its text leaves the corpus.
        content_tables = []
        for table in found_tables:
            try:
                data = table.extract()
            except (ValueError, RuntimeError) as exc:
                logger.debug("Table extraction error on page %d: %s", page_number, exc)
                continue
            if data and is_content_table(data):
                content_tables.append((table, data))

        if not content_tables:
            raw_text = (page.extract_text(layout=False) or "").strip()
            if raw_text:
                blocks.append(
                    LayoutBlock(
                        block_type="PARAGRAPH",
                        content=raw_text,
                        top_y=0.0,
                        page_number=page_number,
                    )
                )
            return blocks

        # Sort tables by top coordinate (top-to-bottom reading order)
        sorted_tables = sorted(content_tables, key=lambda pair: pair[0].bbox[1])
        page_width = float(page.width)
        page_height = float(page.height)

        current_y = 0.0

        for table, table_data in sorted_tables:
            _, t_top, _, t_bottom = (
                float(table.bbox[0]),
                float(table.bbox[1]),
                float(table.bbox[2]),
                float(table.bbox[3]),
            )

            # Extract text section above the current table if height is significant
            if t_top > current_y + 2.0:
                try:
                    above_crop = page.crop(
                        (0.0, current_y, page_width, max(current_y, t_top - 1.0))
                    )
                    above_text = (above_crop.extract_text(layout=False) or "").strip()
                    if above_text:
                        blocks.append(
                            LayoutBlock(
                                block_type="PARAGRAPH",
                                content=above_text,
                                top_y=current_y,
                                page_number=page_number,
                            )
                        )
                except (ValueError, RuntimeError) as exc:
                    logger.debug(
                        "Crop error above table on page %d: %s", page_number, exc
                    )

            # Repair rotated cells before formatting: the label a rotated
            # header carries is what classifies every row beneath it.
            for r, row in enumerate(table.rows):
                for c, cell_bbox in enumerate(row.cells):
                    upright = rotated_cell_text(page, cell_bbox)
                    if upright and r < len(table_data) and c < len(table_data[r]):
                        table_data[r][c] = upright

            md_table = self._format_markdown_table(table_data)
            if md_table:
                blocks.append(
                    LayoutBlock(
                        block_type="TABLE",
                        content=md_table,
                        top_y=t_top,
                        page_number=page_number,
                    )
                )
                current_y = max(current_y, t_bottom + 1.0)

        # Extract remaining text below the last table
        if current_y + 2.0 < page_height:
            try:
                below_crop = page.crop((0.0, current_y, page_width, page_height))
                below_text = (below_crop.extract_text(layout=False) or "").strip()
                if below_text:
                    blocks.append(
                        LayoutBlock(
                            block_type="PARAGRAPH",
                            content=below_text,
                            top_y=current_y,
                            page_number=page_number,
                        )
                    )
            except (ValueError, RuntimeError) as exc:
                logger.debug(
                    "Crop error below last table on page %d: %s", page_number, exc
                )

        return blocks

    def extract_document_text(self, pdf_path: Path | str) -> str:
        """Extracts complete document text from PDF with non-duplicated Markdown tables."""
        p = Path(pdf_path)
        if not p.exists():
            raise FileNotFoundError(f"Source PDF file not found: {pdf_path}")

        extracted_page_contents: list[str] = []

        with pdfplumber.open(p) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                blocks = self.extract_blocks_from_page(page, page_number=page_idx)
                if not blocks:
                    continue

                # Sort blocks by vertical position on page
                blocks.sort(key=lambda b: b.top_y)
                page_text = "\n\n".join(b.content for b in blocks if b.content.strip())
                if page_text.strip():
                    extracted_page_contents.append(page_text.strip())

        return "\n\n".join(extracted_page_contents)
