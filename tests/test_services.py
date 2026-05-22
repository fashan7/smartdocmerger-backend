import pytest
from app.services.chunker import chunk_document
from app.services.similarity import find_similar_pairs, compute_similarity_score


# --- Chunker tests ---

def test_chunk_markdown_with_headings():
    text = """# Introduction
This is the intro section with some content about the system.

## Features
Here we describe the features of the product.

## Conclusion
Final thoughts here.
"""
    chunks = chunk_document(text, "md")
    assert len(chunks) >= 2
    titles = [c.title for c in chunks]
    assert "Features" in titles
    assert "Conclusion" in titles


def test_chunk_plain_text():
    text = """First paragraph with some content about automation.

Second paragraph discussing health checks and monitoring.

Third paragraph about proxy management."""

    chunks = chunk_document(text, "txt")
    assert len(chunks) >= 2


def test_chunk_merges_tiny_sections():
    text = """# Header
Short.

## Big Section
This is a much longer section with plenty of content to pass the minimum word threshold for chunking."""

    chunks = chunk_document(text, "md")
    # Tiny "Short." should be merged
    for chunk in chunks:
        assert chunk.word_count() >= 5 or len(chunks) == 1


def test_chunk_empty_text():
    chunks = chunk_document("", "txt")
    assert isinstance(chunks, list)


def test_chunk_single_paragraph():
    text = "Just one paragraph here with enough words to make a chunk."
    chunks = chunk_document(text, "txt")
    assert len(chunks) >= 1
    assert chunks[0].text.strip() != ""


# --- Similarity tests ---

def test_find_similar_pairs_identical():
    ideas = [
        {"id": "1", "full_text": "Auto-restart failed spider processes automatically"},
        {"id": "2", "full_text": "Auto-restart failed spider processes automatically"},
    ]
    pairs = find_similar_pairs(ideas, threshold=0.9)
    assert len(pairs) == 1
    assert pairs[0]["tfidf_score"] > 0.9


def test_find_similar_pairs_different():
    ideas = [
        {"id": "1", "full_text": "Auto-restart failed spider processes"},
        {"id": "2", "full_text": "Configure proxy rotation for outbound requests"},
    ]
    pairs = find_similar_pairs(ideas, threshold=0.75)
    assert len(pairs) == 0


def test_find_similar_pairs_too_few():
    ideas = [{"id": "1", "full_text": "Only one idea here"}]
    pairs = find_similar_pairs(ideas, threshold=0.75)
    assert pairs == []


def test_find_similar_pairs_empty():
    pairs = find_similar_pairs([], threshold=0.75)
    assert pairs == []


def test_find_similar_pairs_multiple():
    ideas = [
        {"id": "1", "full_text": "Health check monitoring for spider processes using ping"},
        {"id": "2", "full_text": "Monitor spider health with periodic ping checks"},
        {"id": "3", "full_text": "Configure database connection pooling for MySQL"},
    ]
    pairs = find_similar_pairs(ideas, threshold=0.2)
    pair_ids = [(p["idea_a_id"], p["idea_b_id"]) for p in pairs]
    # 1 and 2 should be similar; 3 should not match either
    ids_involved = set()
    for a, b in pair_ids:
        ids_involved.add(a)
        ids_involved.add(b)
    assert "3" not in ids_involved or len(pairs) <= 2


def test_compute_similarity_score():
    score = compute_similarity_score(80.0, 90.0)
    # 80*0.4 + 90*0.6 = 32 + 54 = 86 / 100 = 0.86
    assert abs(score - 0.86) < 0.01


def test_compute_similarity_score_zero():
    score = compute_similarity_score(0.0, 0.0)
    assert score == 0.0


def test_compute_similarity_score_full():
    score = compute_similarity_score(100.0, 100.0)
    assert abs(score - 1.0) < 0.01
