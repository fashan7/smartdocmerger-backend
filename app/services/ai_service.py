import json
import anthropic
from app.config import settings


def get_client(api_key: str | None = None) -> anthropic.Anthropic:
    key = api_key or settings.ANTHROPIC_API_KEY
    if not key:
        raise ValueError("No Anthropic API key configured. Add one in Settings.")
    return anthropic.Anthropic(api_key=key)


async def extract_ideas_from_chunks(
    chunks: list[dict],
    project_context: str = "",
    api_key: str | None = None,
) -> list[dict]:
    """
    Takes document chunks, returns list of extracted ideas.
    Each idea: {summary, full_text, section_title, section_index}
    """
    client = get_client(api_key)

    context_block = f"\nProject context: {project_context}\n" if project_context else ""

    chunks_text = "\n\n---\n\n".join(
        [f"SECTION {c['index']} — {c['title']}:\n{c['text']}" for c in chunks]
    )

    prompt = f"""You are extracting distinct ideas from a document.{context_block}

Document sections:
{chunks_text}

Extract every distinct idea, concept, feature, problem, or decision from this document.
Each idea should be atomic — one clear thought per idea.
Ignore filler, formatting, and repeated transitions.

Return ONLY a JSON array. No preamble. No markdown. Example format:
[
  {{
    "summary": "Brief one-line summary of the idea (max 100 chars)",
    "full_text": "Full explanation of the idea as a clean paragraph",
    "section_title": "Which section this came from",
    "section_index": 0
  }}
]"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        ideas = json.loads(raw)
        if not isinstance(ideas, list):
            return []
        return ideas
    except json.JSONDecodeError:
        return []


async def verify_similarity_pair(
    idea_a: str,
    idea_b: str,
    api_key: str | None = None,
) -> dict:
    """
    Claude verifies whether two ideas flagged by TF-IDF are truly duplicates.
    Returns: {wording_match, concept_match, recommendation, reason, confidence}
    """
    client = get_client(api_key)

    prompt = f"""Compare these two ideas and determine if they are duplicates.

Idea A:
{idea_a}

Idea B:
{idea_b}

Return ONLY a JSON object. No preamble. No markdown:
{{
  "wording_match": <0-100 integer, how similar the actual wording is>,
  "concept_match": <0-100 integer, how similar the core concept is>,
  "recommendation": "<keep_a|keep_b|merge|keep_both>",
  "reason": "<one sentence explaining your recommendation>",
  "confidence": "<high|medium|low>"
}}

Rules:
- keep_a: A is clearer/more complete, discard B
- keep_b: B is clearer/more complete, discard A  
- merge: both have unique value, combine them
- keep_both: they are actually different ideas despite surface similarity"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
        return {
            "wording_match": float(result.get("wording_match", 0)),
            "concept_match": float(result.get("concept_match", 0)),
            "recommendation": result.get("recommendation", "keep_both"),
            "reason": result.get("reason", ""),
            "confidence": result.get("confidence", "medium"),
        }
    except (json.JSONDecodeError, KeyError):
        return {
            "wording_match": 0.0,
            "concept_match": 0.0,
            "recommendation": "keep_both",
            "reason": "Could not determine similarity",
            "confidence": "low",
        }


async def validate_api_key(api_key: str) -> bool:
    """Test if an API key is valid with a minimal call."""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        return True
    except Exception:
        return False


async def merge_two_ideas(
    idea_a: str,
    idea_b: str,
    api_key: str | None = None,
) -> str:
    """Merge two ideas into one clean paragraph."""
    client = get_client(api_key)

    prompt = f"""Merge these two similar ideas into one clear, concise paragraph.
Remove repetition. Keep all unique points. Be direct and concise.

Idea A:
{idea_a}

Idea B:
{idea_b}

Return only the merged paragraph. No preamble."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()
