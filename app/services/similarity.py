import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def find_similar_pairs(
    ideas: list[dict],
    threshold: float = 0.75,
) -> list[dict]:
    """
    Run TF-IDF cosine similarity across all ideas.
    Returns list of candidate pairs above threshold.

    Each idea dict must have: {id, full_text}
    Returns: [{idea_a_id, idea_b_id, tfidf_score}]
    """
    if len(ideas) < 2:
        return []

    texts = [idea["full_text"] for idea in ideas]
    ids = [idea["id"] for idea in ideas]

    # TF-IDF vectorization
    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            min_df=1,
            ngram_range=(1, 2),  # unigrams + bigrams for better matching
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # Happens if all texts are empty after stop word removal
        return []

    similarity_matrix = cosine_similarity(tfidf_matrix)

    pairs = []
    for i in range(len(ideas)):
        for j in range(i + 1, len(ideas)):
            score = float(similarity_matrix[i][j])
            if score >= threshold:
                pairs.append({
                    "idea_a_id": ids[i],
                    "idea_b_id": ids[j],
                    "tfidf_score": round(score, 4),
                })

    # Sort by score descending
    pairs.sort(key=lambda x: x["tfidf_score"], reverse=True)
    return pairs


def compute_similarity_score(wording_match: float, concept_match: float) -> float:
    """
    Combine Claude's wording and concept scores into a single display score.
    Concept match is weighted higher (0.6) than wording (0.4).
    """
    return round((wording_match * 0.4 + concept_match * 0.6) / 100, 4)
