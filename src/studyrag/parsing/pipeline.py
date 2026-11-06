# from functools import cache
# from pathlib import Path

# from docling.document_converter import (
#     DocumentConverter,
#     PdfFormatOption,
# )

# from docling.datamodel.base_models import InputFormat
# from docling.datamodel.pipeline_options import (
#     PdfPipelineOptions,
#     RapidOcrOptions,
#     TableStructureOptions,
#     TableFormerMode,
# )

# from studyrag.config import RAW_DIR, PARSED_DIR


# @cache
# def build_converter():

#     options = PdfPipelineOptions()

#     # OCR
#     options.do_ocr = True
#     options.ocr_options = RapidOcrOptions(
#         backend="onnxruntime",
#         force_full_page_ocr=False
#     )

#     # Tables
#     options.do_table_structure = True
#     options.table_structure_options = TableStructureOptions(
#         mode=TableFormerMode.ACCURATE,
#         do_cell_matching=True
#     )

#     # Formulas
#     options.do_formula_enrichment = True

#     # Pictures and diagrams
#     options.generate_picture_images = True
#     options.images_scale = 2.0

#     # Picture understanding
#     options.do_picture_classification = True
#     options.do_picture_description = True

#     # Charts
#     options.do_chart_extraction = True

#     # Page images for inspection
#     options.generate_page_images = True

#     converter = DocumentConverter(
#         format_options={
#             InputFormat.PDF: PdfFormatOption(
#                 pipeline_options=options
#             )
#         }
#     )

#     return converter


# def parse_pdf(pdf_path, converter=None):

#     converter = converter or build_converter()

#     result = converter.convert(pdf_path)

#     return result.document



from functools import cache

from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
    TableStructureOptions,
    TableFormerMode,
)

from studyrag.config import RAW_DIR, PARSED_DIR


@cache
def build_converter():

    options = PdfPipelineOptions()

    # OCR
    options.do_ocr = True
    options.ocr_options = RapidOcrOptions(
        backend="onnxruntime",
        force_full_page_ocr=False
    )

    # Tables
    options.do_table_structure = True
    options.table_structure_options = TableStructureOptions(
        mode=TableFormerMode.ACCURATE,
        do_cell_matching=True
    )

    # Disable expensive visual AI processing
    options.do_formula_enrichment = False
    options.do_picture_classification = False
    options.do_picture_description = False
    options.do_chart_extraction = False

    # Keep figure images for later inspection
    options.generate_picture_images = True
    options.images_scale = 1.0

    # Avoid rendering every page
    options.generate_page_images = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=options
            )
        }
    )

    return converter


def parse_pdf(pdf_path, converter=None):

    converter = converter or build_converter()

    result = converter.convert(pdf_path)

    return result.document
