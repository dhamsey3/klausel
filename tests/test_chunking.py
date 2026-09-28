from pathlib import Path

import pytest

from klausel.ingest.chunking import chunk_text

SAMPLE = (Path(__file__).parents[1] / "data" / "samples" / "dienstleistungsvertrag.txt").read_text(
    encoding="utf-8"
)


def test_empty_text_gives_no_chunks():
    assert chunk_text("   ") == []


def test_short_text_is_single_chunk():
    chunks = chunk_text("§ 1 Kurz.", chunk_size=200, overlap=20)
    assert [c.text for c in chunks] == ["§ 1 Kurz."]


@pytest.mark.parametrize("size,overlap", [(200, 0), (400, 50), (1000, 150)])
def test_chunks_respect_size(size, overlap):
    chunks = chunk_text(SAMPLE, chunk_size=size, overlap=overlap)
    assert len(chunks) > 1
    assert all(len(c.text) <= size for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_no_content_is_lost():
    chunks = chunk_text(SAMPLE, chunk_size=300, overlap=0)
    joined = " ".join(" ".join(c.text.split()) for c in chunks)
    for word in SAMPLE.split():
        assert word in joined


def test_sections_start_new_chunks_when_possible():
    chunks = chunk_text(SAMPLE, chunk_size=700, overlap=0)
    assert any(c.text.startswith("§ 4 Haftung") for c in chunks)


def test_abbreviations_do_not_split_sentences():
    text = ("Gemäß Abs. 2 gilt Nr. 3 entsprechend. " * 40).strip()
    chunks = chunk_text(text, chunk_size=120, overlap=0)
    assert not any(c.text.endswith("Abs.") or c.text.endswith("Nr.") for c in chunks)


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_text("x", chunk_size=100, overlap=100)
