from studyrag.ingestion.sources import SOURCES


def test_source_filenames_are_unique_and_valid():
    names = [fname for items in SOURCES.values() for fname, _, _ in items]
    assert len(names) == len(set(names))
    for items in SOURCES.values():
        for fname, url, note in items:
            assert url.startswith("https://"), fname
            assert note, f"{fname} needs a licence note"
