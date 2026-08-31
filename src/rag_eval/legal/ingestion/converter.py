"""PDF text extraction and automated noise sanitation for Vietnamese legal instruments.

Strips Công Báo headers/footers, gazette issue numbers, page numbers, preamble metadata,
and signatory trailers while unwrapping paragraphs and preserving 6-tier statutory hierarchies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


def sanitize_legal_text(raw_lines: list[str]) -> str:
    """Sanitizes raw lines extracted from legal PDF documents.

    Removes Công Báo repeating headers, standalone page numbers, preambles, and trailers,
    then unwraps soft line breaks within paragraphs while strictly preserving structural headings.
    """
    cong_bao_re = re.compile(r"^(?:\d+\s+)?(?:CÔNG\s+BÁO/Số|CONG\s+BAO/So).*$", re.IGNORECASE)
    page_num_re = re.compile(r"^\d+$")
    gazette_meta_re = re.compile(r"^\(Tiếp\s+theo\s+Công\s+báo\s+số.*\)$", re.IGNORECASE)
    preamble_headers_re = re.compile(
        r"^(?:VĂN\s+BẢN\s+QUY\s+PHẠM\s+PHÁP\s+LUẬT|CỘNG\s+HÒA\s+XÃ\s+HỘI\s+CHỦ\s+NGHĨA\s+VIỆT\s+NAM|Độc\s+lập\s+-\s+Tự\s+do\s+-\s+Hạnh\s+phúc|CHỦ\s+TỊCH\s+NƯỚC\s+-\s+QUỐC\s+HỘI)$",
        re.IGNORECASE,
    )
    signatory_title_re = re.compile(
        r"^(?:CHỦ\s+TỊCH\s+QUỐC\s+HỘI|THỦ\s+TƯỚNG(?:\s+CHÍNH\s+PHỦ)?|KT\.\s+THỦ\s+TƯỚNG|PHÓ\s+THỦ\s+TƯỚNG|BỘ\s+TRƯỞNG|KT\.\s+BỘ\s+TRƯỞNG|THỨ\s+TRƯỞNG|CHỦ\s+TỊCH\s+NƯỚC)\s*$",
        re.IGNORECASE,
    )

    in_signatory_block = False
    filtered_lines: list[str] = []
    for line in raw_lines:
        clean = line.strip()
        if not clean:
            continue
        if cong_bao_re.match(clean):
            continue
        if page_num_re.match(clean):
            continue
        if gazette_meta_re.match(clean):
            continue
        if preamble_headers_re.match(clean):
            continue
        if signatory_title_re.match(clean):
            in_signatory_block = True
            continue
        if in_signatory_block:
            if (
                re.match(r"^Chương\s+[IVXLCDM0-9]+", clean, re.IGNORECASE)
                or re.match(r"^Mục\s+[0-9]+", clean, re.IGNORECASE)
                or re.match(r"^Điều\s+[0-9]+\.\s+[A-ZÀ-ỸĐ]", clean)
            ):
                in_signatory_block = False
            else:
                continue
        filtered_lines.append(clean)

    chap_re = re.compile(r"^Chương\s+[IVXLCDM0-9]+", re.IGNORECASE)
    sec_re = re.compile(r"^Mục\s+[0-9]+", re.IGNORECASE)
    art_re = re.compile(r"^Điều\s+[0-9]+\.\s+[A-ZÀ-ỸĐ]")
    clause_re = re.compile(r"^[0-9]+\.\s+")
    point_re = re.compile(r"^[a-zđ]\)\s+")

    blocks: list[str] = []
    current_block: list[str] = []

    for line in filtered_lines:
        is_heading = (
            chap_re.match(line)
            or sec_re.match(line)
            or art_re.match(line)
            or clause_re.match(line)
            or point_re.match(line)
        )
        if is_heading:
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            current_block.append(line)
        else:
            if not current_block:
                current_block.append(line)
            else:
                if chap_re.match(current_block[-1]) and line.isupper():
                    blocks.append(" ".join(current_block))
                    current_block = [line]
                else:
                    current_block.append(line)

    if current_block:
        blocks.append(" ".join(current_block))

    return "\n".join(blocks)


def convert_pdf_to_text(pdf_path: str | Path, txt_path: str | Path | None = None) -> str:
    """Converts a Vietnamese legal PDF document into clean sanitized statutory text.

    Args:
        pdf_path: Path to source PDF file.
        txt_path: Optional destination path to write sanitized text file.

    Returns:
        Sanitized statutory text string.
    """
    path_obj = Path(pdf_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")

    raw_lines: list[str] = []
    with pdfplumber.open(path_obj) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if not page_text:
                continue
            raw_lines.extend(page_text.splitlines())

    sanitized_text = sanitize_legal_text(raw_lines)

    if txt_path is not None:
        out_path = Path(txt_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sanitized_text, encoding="utf-8")

    return sanitized_text
