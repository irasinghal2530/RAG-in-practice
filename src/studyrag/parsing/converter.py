"""
Docling converter configured for accuracy on technical manuals and standards.

  - TableFormer in ACCURATE mode with cell matching, so troubleshooting / fault-code tables
    keep their rows and columns instead of becoming word soup.
  - Heading hierarchy reconstruction, so chunks carry the real section path
    (e.g. "7 Maintenance > 7.2 Bearings > Lubrication intervals").
  - RapidOCR on the ONNX Runtime backend (the PyTorch backend is ~10x slower on CPU).
    With force_ocr every page is re-OCRed, for scans whose embedded text layer is bad;
    otherwise the native PDF text is used and only bitmap regions are OCRed.
"""

import os

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (HeadingHierarchyOptions, PdfPipelineOptions,
                                                RapidOcrOptions, TableFormerMode,
                                                TableStructureOptions)
from docling.document_converter import DocumentConverter, PdfFormatOption


def build_converter(force_ocr: bool = False, threads: int | None = None) -> DocumentConverter:
    opts = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=RapidOcrOptions(backend="onnxruntime", force_full_page_ocr=force_ocr),
        do_table_structure=True,
        # cell matching fills table cells from the text/OCR cells; without it ~35% of the
        # cells in the IS 12615 efficiency tables come out empty, even with full-page OCR
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE,
                                                      do_cell_matching=True),
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
        accelerator_options=AcceleratorOptions(num_threads=threads or os.cpu_count() or 4,
                                               device="auto"),
    )
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
