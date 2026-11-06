"""Validation tests for step 1 (raw PDFs -> DoclingDocument JSON + Markdown in data/parsed/).

Three layers:
  1. converter config + parse_pdf wiring        fast, no models are loaded
  2. `studyrag parse` CLI stage                 fast, parse_pdf is replaced by a fake
  3. quality of every parsed doc in data/parsed  fast, reads the saved JSON; one test per doc per check
  4. end to end on the smallest real PDF        slow, runs Docling (deselect with -m 'not slow')

The quality checks in (3) target what breaks retrieval downstream: lost pages, garbled text,
warnings detected as headings, tables without headers, TOC dot leaders and running headers
leaking into body text, formulas dropped. Thresholds are constants below: tighten them as the
parser improves.

    pytest tests/test_parsing.py -m "not slow"                  # everything but the real Docling run
    pytest tests/test_parsing.py -k baldor_mn431_iom            # one document
"""


# from pathlib import Path
# import re

# import pytest
# import pypdfium2

# from docling_core.types.doc import (
#     DoclingDocument,
#     DocItemLabel,
#     ContentLayer,
# )

# from studyrag import config


# # ==================================================
# # CONFIGURATION
# # ==================================================

# PARSED_DOCS = sorted(
#     p for p in config.PARSED_DIR.rglob("*.json")
#     if p.name != "manifest.json"
# )

# ALL_LAYERS = set(ContentLayer)

# HEADINGS = {
#     DocItemLabel.TITLE,
#     DocItemLabel.SECTION_HEADER,
# }

# FURNITURE = {
#     DocItemLabel.PAGE_HEADER,
#     DocItemLabel.PAGE_FOOTER,
# }

# MIN_CHARS_PER_PAGE = 200
# MAX_EMPTY_PAGE_FRACTION = 0.10
# MAX_GARBLED_CHAR_FRACTION = 0.001


# # ==================================================
# # LOAD PARSED DOCUMENTS
# # ==================================================

# @pytest.fixture(
#     scope="module",
#     params=PARSED_DOCS or [None],
#     ids=lambda p: p.stem if p else "no-documents",
# )
# def parsed(request):

#     if request.param is None:
#         pytest.skip("No parsed documents. Run studyrag parse first.")

#     path = request.param
#     doc = DoclingDocument.load_from_json(path)

#     return path, doc


# # ==================================================
# # HELPER FUNCTIONS
# # ==================================================

# def get_items(doc):
#     """Return all document items in reading order."""

#     return [
#         item
#         for item, _ in doc.iterate_items(
#             included_content_layers=ALL_LAYERS
#         )
#     ]


# def get_body_texts(doc):
#     """Return body text, excluding headers and footers."""

#     return [
#         item for item in doc.texts
#         if item.content_layer == ContentLayer.BODY
#         and item.label not in FURNITURE
#     ]


# def get_pages(item):
#     """Return page numbers associated with an item."""

#     return {
#         prov.page_no
#         for prov in getattr(item, "prov", [])
#     }


# def has_content(item):
#     """Check whether a document item contains content."""

#     if item.label == DocItemLabel.TABLE:
#         return any(
#             cell.text.strip()
#             for cell in item.data.table_cells
#         )

#     return bool(
#         getattr(item, "text", "").strip()
#     )


# # ==================================================
# # 1. PAGE VALIDATION
# # ==================================================

# def test_page_count(parsed):

#     path, doc = parsed

#     pdf_path = (
#         config.RAW_DIR
#         / path.relative_to(config.PARSED_DIR).with_suffix(".pdf")
#     )

#     if not pdf_path.exists():
#         pytest.skip("Original PDF not found")

#     original_pages = len(
#         pypdfium2.PdfDocument(pdf_path)
#     )

#     assert doc.num_pages() == original_pages, (
#         f"Original: {original_pages}, "
#         f"Parsed: {doc.num_pages()}"
#     )


# def test_page_references(parsed):

#     _, doc = parsed

#     assert doc.num_pages() > 0

#     assert sorted(doc.pages) == list(
#         range(1, doc.num_pages() + 1)
#     ), "Page numbers are missing or discontinuous"

#     for item in get_items(doc):

#         for page in get_pages(item):

#             assert 1 <= page <= doc.num_pages(), (
#                 f"Invalid page reference: {page}"
#             )


# def test_empty_pages(parsed):

#     _, doc = parsed

#     pages_with_content = set()

#     for item in get_items(doc):

#         if item.label in FURNITURE:
#             continue

#         if has_content(item):
#             pages_with_content.update(get_pages(item))

#     empty_pages = (
#         set(range(1, doc.num_pages() + 1))
#         - pages_with_content
#     )

#     empty_fraction = (
#         len(empty_pages) / max(doc.num_pages(), 1)
#     )

#     assert empty_fraction <= MAX_EMPTY_PAGE_FRACTION, (
#         f"Too many pages without extracted body content: "
#         f"{sorted(empty_pages)}"
#     )


# # ==================================================
# # 2. TEXT EXTRACTION VALIDATION
# # ==================================================

# def test_text_extraction(parsed):

#     _, doc = parsed

#     texts = get_body_texts(doc)

#     combined_text = "\n".join(
#         item.text for item in texts
#     )

#     assert combined_text.strip(), (
#         "No body text extracted"
#     )

#     average_chars = (
#         len(combined_text) / max(doc.num_pages(), 1)
#     )

#     assert average_chars >= MIN_CHARS_PER_PAGE, (
#         f"Only {average_chars:.0f} characters per page on average"
#     )


# def test_garbled_text(parsed):

#     _, doc = parsed

#     text = "\n".join(
#         item.text for item in get_body_texts(doc)
#     )

#     garbled = re.findall(
#         r"�|GLYPH<[^>]*>|/uni[0-9A-Fa-f]{4}",
#         text
#     )

#     fraction = len(garbled) / max(len(text), 1)

#     assert fraction <= MAX_GARBLED_CHAR_FRACTION, (
#         f"Found {len(garbled)} suspicious characters "
#         f"in {len(text)} characters"
#     )


# # ==================================================
# # 3. HEADING AND CONTENT VALIDATION
# # ==================================================

# def test_heading_extraction(parsed):

#     _, doc = parsed

#     headings = [
#         item for item in doc.texts
#         if item.label in HEADINGS
#     ]

#     assert headings, "No headings detected"


# def test_heading_content_association(parsed):

#     _, doc = parsed

#     items = list(
#         doc.iterate_items(
#             included_content_layers=ALL_LAYERS
#         )
#     )

#     problems = []

#     for i, (item, level) in enumerate(items):

#         if item.label not in HEADINGS:
#             continue

#         content_found = False

#         # Search until the next heading at the same
#         # or higher hierarchy level.

#         for next_item, next_level in items[i + 1:]:

#             if (
#                 next_item.label in HEADINGS
#                 and next_level <= level
#             ):
#                 break

#             if has_content(next_item):
#                 content_found = True
#                 break

#         if not content_found:
#             problems.append(
#                 f"Heading without following content: "
#                 f"{item.text[:100]!r}"
#             )

#     assert not problems, "\n".join(problems)


# def test_heading_order(parsed):

#     _, doc = parsed

#     headings = [
#         item for item in get_items(doc)
#         if item.label in HEADINGS
#     ]

#     pages = [
#         min(get_pages(item))
#         for item in headings
#         if get_pages(item)
#     ]

#     assert pages == sorted(pages), (
#         "Heading page order is incorrect"
#     )


# # ==================================================
# # 4. TABLE VALIDATION
# # ==================================================

# def test_table_extraction(parsed):

#     _, doc = parsed

#     for i, table in enumerate(doc.tables):

#         data = table.data
#         cells = data.table_cells

#         assert data.num_rows > 0, (
#             f"Table {i}: no rows"
#         )

#         assert data.num_cols > 0, (
#             f"Table {i}: no columns"
#         )

#         assert cells, (
#             f"Table {i}: no cells"
#         )

#         filled_cells = sum(
#             bool(cell.text.strip())
#             for cell in cells
#         )

#         assert filled_cells > 0, (
#             f"Table {i}: all cells are empty"
#         )


# def test_table_headers(parsed):

#     _, doc = parsed

#     tables_without_headers = []

#     for i, table in enumerate(doc.tables):

#         has_header = any(
#             cell.column_header or cell.row_header
#             for cell in table.data.table_cells
#         )

#         if not has_header:
#             tables_without_headers.append(i)

#     # Informational review: not every engineering table
#     # necessarily has a conventional header.

#     if tables_without_headers:
#         print(
#             "\nTables requiring header review:",
#             tables_without_headers
#         )


# # ==================================================
# # 5. FORMULA VALIDATION
# # ==================================================

# def test_formula_extraction(parsed):

#     _, doc = parsed

#     formulas = [
#         item for item in doc.texts
#         if item.label == DocItemLabel.FORMULA
#     ]

#     problems = []

#     for formula in formulas:

#         if not formula.text.strip():
#             problems.append(
#                 f"Formula text missing on pages "
#                 f"{sorted(get_pages(formula))}: "
#                 f"{formula.orig[:100]!r}"
#             )

#     markdown = doc.export_to_markdown()

#     assert "formula-not-decoded" not in markdown, (
#         "Undecoded formula placeholders found in Markdown"
#     )

#     assert not problems, "\n".join(problems)


# # ==================================================
# # 6. JSON AND MARKDOWN VALIDATION
# # ==================================================

# def test_markdown_exists(parsed):

#     path, _ = parsed

#     md_path = path.with_suffix(".md")

#     assert md_path.exists(), (
#         f"Markdown missing: {md_path}"
#     )

#     assert md_path.stat().st_size > 0, (
#         "Markdown file is empty"
#     )


# def test_markdown_consistency(parsed):

#     path, doc = parsed

#     md_path = path.with_suffix(".md")

#     assert md_path.exists(), "Markdown file missing"

#     saved_markdown = md_path.read_text(
#         encoding="utf-8"
#     )

#     generated_markdown = doc.export_to_markdown()

#     assert saved_markdown == generated_markdown, (
#         "Saved Markdown differs from Docling export"
#     )


# def test_json_round_trip(parsed, tmp_path):

#     _, doc = parsed

#     output = tmp_path / "test.json"

#     doc.save_as_json(output)

#     loaded_doc = DoclingDocument.load_from_json(output)

#     assert loaded_doc.num_pages() == doc.num_pages()

#     assert (
#         loaded_doc.export_to_markdown()
#         == doc.export_to_markdown()
#     )



from docling_core.types.doc import (
    DoclingDocument,
    ContentLayer,
)

doc = DoclingDocument.load_from_json(
    r"C:\personal-projects\StudyRag\data\parsed\manuals\baldor_mn431_iom.json"
)

TARGET_PAGE = 6

print(f"\n========== PAGE {TARGET_PAGE} ==========\n")

for index, (item, level) in enumerate(
    doc.iterate_items(
        included_content_layers=set(ContentLayer)
    )
):

    pages = {
        p.page_no
        for p in getattr(item, "prov", [])
    }

    if 6 not in pages:
        continue

    if index < 39 or index > 64:
        continue

    print(f"\nOrder: {index}")
    print(f"Type: {item.label}")
    print(f"Text: {getattr(item, 'text', '')!r}")

    for prov in getattr(item, "prov", []):
        print("Bounding box:", prov.bbox)