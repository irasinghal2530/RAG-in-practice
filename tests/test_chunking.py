from docling_core.types.doc import DocItemLabel, DoclingDocument

from studyrag.chunking.pipeline import chunk_document


def test_chunks_have_text_and_embed_text():
    doc = DoclingDocument(name="test")
    doc.add_heading("Bearing maintenance")
    doc.add_text(label=DocItemLabel.TEXT, text="Grease the bearings every 2000 hours. " * 50)
    chunks = chunk_document(doc)
    assert chunks
    for c in chunks:
        assert c["text"].strip()
        assert "Bearing maintenance" in c["embed_text"]
