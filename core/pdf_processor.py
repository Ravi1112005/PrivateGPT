"""
core/pdf_processor.py — Robust multi-strategy PDF extraction.

Handles all PDF types: digital (selectable text), scanned/image PDFs,
tables, invoices, ebooks, and mixed-content documents.

3-tier extraction strategy per page:
  Tier 1: PyMuPDF text extraction (fast, for digital PDFs)
  Tier 2: Table detection → Markdown (preserves structure for LLM)
  Tier 3: OCR via pytesseract (for scanned/image-only pages)

Text cleaning pipeline:
  - Remove page numbers (isolated numbers at page top/bottom)
  - Remove repeated headers/footers (cross-page comparison)
  - Remove boilerplate (copyright, ISBN, "All rights reserved")
  - Collapse excessive whitespace
  - Skip junk pages (TOC, blank, copyright-only)

Dependencies:
  Required: PyMuPDF (fitz)
  Optional: pytesseract + Tesseract binary, Pillow (for OCR)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Extract clean, structured text from any PDF type.

    Usage::

        processor = PDFProcessor(ocr_dpi=300)
        documents = processor.extract("/path/to/file.pdf")
        # Returns list of LangChain-compatible Document objects
    """

    # Minimum characters for a page to be considered "has text"
    MIN_TEXT_CHARS = 30

    # Boilerplate patterns to strip
    _BOILERPLATE_PATTERNS = [
        re.compile(r"(?i)^\s*copyright\s*©?\s*\d{4}.*$", re.MULTILINE),
        re.compile(r"(?i)^\s*all\s+rights\s+reserved\.?\s*$", re.MULTILINE),
        re.compile(r"(?i)^\s*isbn[\s:\-]*[\d\-]+\s*$", re.MULTILINE),
        re.compile(r"(?i)^\s*printed\s+in\s+the\s+united\s+states.*$", re.MULTILINE),
        re.compile(r"(?i)^\s*published\s+by\s+.*$", re.MULTILINE),
    ]

    # Page number patterns (isolated number at start/end of text)
    _PAGE_NUM_PATTERNS = [
        re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$", re.MULTILINE),  # "1", "- 42 -"
        re.compile(r"^\s*page\s+\d{1,4}\s*(of\s+\d{1,4})?\s*$", re.MULTILINE | re.IGNORECASE),
    ]

    # Junk page signals
    _JUNK_SIGNALS = [
        "table of contents",
        "list of figures",
        "list of tables",
        "acknowledgements",
        "acknowledgments",
    ]

    def __init__(
        self,
        ocr_dpi: int = 300,
        tesseract_path: str = "",
    ) -> None:
        self._ocr_dpi = ocr_dpi
        self._tesseract_path = tesseract_path
        self._tesseract_available: Optional[bool] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def extract(self, pdf_path: str) -> List:
        """
        Extract all pages from a PDF as LangChain Document objects.

        Each Document has:
          - ``page_content``: cleaned text (or Markdown table)
          - ``metadata``: {source, page, content_type, ...}

        Parameters
        ----------
        pdf_path : str
            Path to the PDF file.

        Returns
        -------
        list of Document
            One Document per page (junk pages excluded).
        """
        from langchain_core.documents import Document  # noqa: PLC0415

        try:
            import fitz  # PyMuPDF  # noqa: PLC0415
        except ImportError:
            logger.warning(
                "PyMuPDF not installed — falling back to PyPDFLoader. "
                "Install with: pip install PyMuPDF"
            )
            return self._fallback_pypdf(pdf_path)

        path = Path(pdf_path)
        doc = fitz.open(str(path))
        total_pages = len(doc)

        # Phase 1: Extract raw text from all pages for header/footer detection
        raw_texts: List[str] = []
        for page in doc:
            raw_texts.append(page.get_text("text") or "")

        # Phase 2: Detect repeated headers and footers across pages
        headers, footers = self._detect_repeated_lines(raw_texts)

        # Phase 3: Process each page with the 3-tier strategy
        documents: List = []
        for page_num, page in enumerate(doc):
            page_docs = self._extract_page(
                page=page,
                page_num=page_num + 1,  # 1-indexed
                source_file=path.name,
                headers=headers,
                footers=footers,
            )
            documents.extend(page_docs)

        doc.close()

        if not documents:
            logger.warning("No extractable content found in %s", path.name)

        logger.info(
            "Extracted %d page(s) from %s (%d total pages, %d skipped)",
            len(documents), path.name, total_pages, total_pages - len(documents),
        )
        return documents

    # ── Per-page extraction (3-tier) ───────────────────────────────────────

    def _extract_page(
        self,
        page,
        page_num: int,
        source_file: str,
        headers: set,
        footers: set,
    ) -> List:
        """
        Extract content from a single page using the 3-tier strategy.

        Returns 0-N Document objects (tables get separate documents).
        """
        from langchain_core.documents import Document  # noqa: PLC0415

        results: List = []
        base_meta = {"source": source_file, "source_file": source_file, "page": page_num}

        # ── Tier 2: Table extraction ──────────────────────────────────────
        table_docs = self._extract_tables(page, base_meta)
        if table_docs:
            results.extend(table_docs)

        # ── Tier 1: Text extraction ───────────────────────────────────────
        raw_text = page.get_text("text") or ""
        cleaned = self._clean_text(raw_text, page_num, headers, footers)

        if len(cleaned) >= self.MIN_TEXT_CHARS:
            if not self._is_junk_page(cleaned):
                results.append(Document(
                    page_content=cleaned,
                    metadata={**base_meta, "content_type": "text"},
                ))
        elif not table_docs:
            # ── Tier 3: OCR (only if no text AND no tables found) ─────────
            ocr_text = self._ocr_page(page)
            if ocr_text and len(ocr_text) >= self.MIN_TEXT_CHARS:
                ocr_cleaned = self._clean_text(ocr_text, page_num, headers, footers)
                if len(ocr_cleaned) >= self.MIN_TEXT_CHARS and not self._is_junk_page(ocr_cleaned):
                    results.append(Document(
                        page_content=ocr_cleaned,
                        metadata={**base_meta, "content_type": "ocr"},
                    ))

        return results

    # ── Tier 2: Table extraction ───────────────────────────────────────────

    def _extract_tables(self, page, base_meta: Dict) -> List:
        """
        Detect and extract tables from a page as Markdown.

        Uses PyMuPDF's ``page.find_tables()`` for structure detection.
        Each table becomes a separate Document with content_type="table".
        """
        from langchain_core.documents import Document  # noqa: PLC0415

        try:
            tables = page.find_tables()
        except Exception:  # noqa: BLE001
            return []

        results = []
        for i, table in enumerate(tables):
            try:
                # Extract as pandas-like list of lists
                data = table.extract()
                if not data or len(data) < 2:  # Need at least header + 1 row
                    continue

                # Convert to Markdown table
                md = self._table_to_markdown(data)
                if md and len(md) >= self.MIN_TEXT_CHARS:
                    results.append(Document(
                        page_content=md,
                        metadata={
                            **base_meta,
                            "content_type": "table",
                            "table_index": i,
                        },
                    ))
            except Exception:  # noqa: BLE001
                continue

        return results

    @staticmethod
    def _table_to_markdown(data: List[List]) -> str:
        """Convert a list-of-lists table to Markdown format."""
        if not data:
            return ""

        # Clean cells: replace None with empty string, strip whitespace
        cleaned = []
        for row in data:
            cleaned.append([
                str(cell).strip() if cell is not None else ""
                for cell in row
            ])

        # Build Markdown table
        header = cleaned[0]
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in cleaned[1:]:
            # Pad/truncate row to match header length
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[:len(header)]) + " |")

        return "\n".join(lines)

    # ── Tier 3: OCR ────────────────────────────────────────────────────────

    def _ocr_page(self, page) -> str:
        """
        OCR a page by rendering to image and running Tesseract.

        Returns empty string if Tesseract is not available.
        """
        if not self._check_tesseract():
            return ""

        try:
            import pytesseract  # noqa: PLC0415
            from PIL import Image  # noqa: PLC0415
            import io  # noqa: PLC0415

            # Render page to high-DPI image
            pix = page.get_pixmap(dpi=self._ocr_dpi)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))

            # Run OCR
            text = pytesseract.image_to_string(image, lang="eng")
            return text.strip()

        except Exception as exc:  # noqa: BLE001
            logger.debug("OCR failed for page: %s", exc)
            return ""

    def _check_tesseract(self) -> bool:
        """Check if Tesseract OCR is available (cached result)."""
        if self._tesseract_available is not None:
            return self._tesseract_available

        try:
            import pytesseract  # noqa: PLC0415

            # Set custom path if provided
            if self._tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_path
            else:
                # Auto-detect common Windows install paths
                common_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                ]
                for p in common_paths:
                    if Path(p).exists():
                        pytesseract.pytesseract.tesseract_cmd = p
                        break

            # Test that Tesseract works
            pytesseract.get_tesseract_version()
            self._tesseract_available = True
            logger.info("Tesseract OCR available")

        except Exception:  # noqa: BLE001
            self._tesseract_available = False
            logger.info(
                "Tesseract OCR not available — scanned pages will be skipped. "
                "Install from: https://github.com/UB-Mannheim/tesseract/wiki"
            )

        return self._tesseract_available

    # ── Text cleaning ──────────────────────────────────────────────────────

    def _clean_text(
        self,
        text: str,
        page_num: int,
        headers: set,
        footers: set,
    ) -> str:
        """
        Clean extracted text by removing noise.

        Pipeline:
          1. Remove repeated headers/footers
          2. Remove page numbers
          3. Remove boilerplate
          4. Collapse whitespace
        """
        lines = text.split("\n")

        # Remove repeated header lines (first 3 lines of page)
        cleaned_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if i < 3 and stripped in headers:
                continue
            if i >= len(lines) - 3 and stripped in footers:
                continue
            cleaned_lines.append(line)

        text = "\n".join(cleaned_lines)

        # Remove page number patterns
        for pattern in self._PAGE_NUM_PATTERNS:
            text = pattern.sub("", text)

        # Remove boilerplate
        for pattern in self._BOILERPLATE_PATTERNS:
            text = pattern.sub("", text)

        # Collapse excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)  # Max 2 newlines
        text = re.sub(r"[ \t]{2,}", " ", text)  # Collapse horizontal space
        text = text.strip()

        return text

    def _detect_repeated_lines(
        self,
        raw_texts: List[str],
    ) -> Tuple[set, set]:
        """
        Detect repeated headers and footers by comparing first/last lines
        across all pages.

        A line appearing on ≥40% of pages at the top → header.
        A line appearing on ≥40% of pages at the bottom → footer.
        """
        if len(raw_texts) < 3:
            return set(), set()

        threshold = max(3, int(len(raw_texts) * 0.4))

        first_lines: Counter = Counter()
        last_lines: Counter = Counter()

        for text in raw_texts:
            lines = [l.strip().lower() for l in text.split("\n") if l.strip()]
            if not lines:
                continue

            # Check first 2 lines
            for line in lines[:2]:
                if len(line) > 5:  # Skip very short lines
                    first_lines[line] += 1

            # Check last 2 lines
            for line in lines[-2:]:
                if len(line) > 5:
                    last_lines[line] += 1

        headers = {line for line, count in first_lines.items() if count >= threshold}
        footers = {line for line, count in last_lines.items() if count >= threshold}

        if headers:
            logger.debug("Detected %d repeated header(s)", len(headers))
        if footers:
            logger.debug("Detected %d repeated footer(s)", len(footers))

        return headers, footers

    def _is_junk_page(self, text: str) -> bool:
        """
        Detect junk pages: TOC, copyright-only, blank pages, etc.

        A page is junk if it matches ≥2 junk signals or has very little
        meaningful content.
        """
        lower = text.strip().lower()

        if len(lower) < self.MIN_TEXT_CHARS:
            return True

        junk_count = sum(1 for signal in self._JUNK_SIGNALS if signal in lower)

        # Also check for boilerplate-heavy pages
        boilerplate_signals = [
            "copyright ©", "all rights reserved", "isbn",
            "printed in the united states",
        ]
        boilerplate_count = sum(1 for s in boilerplate_signals if s in lower)

        return (junk_count >= 2) or (boilerplate_count >= 2 and len(lower) < 200)

    # ── Fallback: PyPDFLoader ──────────────────────────────────────────────

    @staticmethod
    def _fallback_pypdf(pdf_path: str) -> List:
        """
        Fallback extraction using PyPDFLoader when PyMuPDF is not installed.

        Returns basic text extraction without table or OCR support.
        """
        try:
            from langchain_community.document_loaders import PyPDFLoader  # noqa: PLC0415
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()
            for page in pages:
                page.metadata["source_file"] = Path(pdf_path).name
                page.metadata["content_type"] = "text"
                raw_page = page.metadata.get("page", 0)
                page.metadata["page"] = (raw_page + 1) if isinstance(raw_page, int) else raw_page
            return pages
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallback PyPDFLoader also failed: %s", exc)
            return []

    # ── Convenience ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        ocr = "available" if self._tesseract_available else "unavailable"
        return f"PDFProcessor(ocr_dpi={self._ocr_dpi}, tesseract={ocr})"
