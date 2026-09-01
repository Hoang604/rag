"""PDF Layout and Table Extractor for Vietnamese Statutory Documents.

Isolates table bounding boxes to eliminate table text duplication and formats tables
into clean Markdown pipe tables embedded into the document stream in reading order.
"""

from __future__ import annotations

import logging
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
                    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                    text = " ".join(text.split())
                    text = text.replace("|", "\\|")
                    clean_row.append(text)
            if any(cell for cell in clean_row):
                clean_rows.append(clean_row)

        if not clean_rows:
            return ""

        max_cols = max(len(row) for row in clean_rows)
        # Pad shorter rows
        padded_rows = [row + [""] * (max_cols - len(row)) for row in clean_rows]

        lines: list[str] = []
        # Header row
        header = padded_rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        # Data rows
        for row in padded_rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def extract_blocks_from_page(self, page: Any, page_number: int) -> list[LayoutBlock]:
        """Extracts non-overlapping text and table blocks from a single PDF page."""
        blocks: list[LayoutBlock] = []

        try:
            found_tables = page.find_tables(table_settings=self.table_settings)
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.debug("Failed finding tables with custom settings on page %d: %s", page_number, exc)
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

        # Sort tables by top coordinate (top-to-bottom reading order)
        sorted_tables = sorted(found_tables, key=lambda t: t.bbox[1])
        page_width = float(page.width)
        page_height = float(page.height)

        current_y = 0.0

        for table in sorted_tables:
            _, t_top, _, t_bottom = (
                float(table.bbox[0]),
                float(table.bbox[1]),
                float(table.bbox[2]),
                float(table.bbox[3]),
            )

            # Extract text section above the current table if height is significant
            if t_top > current_y + 2.0:
                try:
                    above_crop = page.crop((0.0, current_y, page_width, max(current_y, t_top - 1.0)))
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
                    logger.debug("Crop error above table on page %d: %s", page_number, exc)

            # Extract and format the table itself
            try:
                table_data = table.extract()
                if table_data:
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
            except (ValueError, RuntimeError) as exc:
                logger.debug("Table extraction error on page %d: %s", page_number, exc)

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
                logger.debug("Crop error below last table on page %d: %s", page_number, exc)

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
