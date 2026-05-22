import re


class Chunk:
    def __init__(self, title: str, text: str, index: int):
        self.title = title
        self.text = text.strip()
        self.index = index

    def word_count(self) -> int:
        return len(self.text.split())


def chunk_document(text: str, file_type: str) -> list[Chunk]:
    """
    Splits document text into sections/chunks.
    For markdown: splits on headings.
    For plain text/pdf: splits on double newlines (paragraphs).
    Merges chunks that are too small (<30 words) with the next one.
    """
    if file_type == "md":
        chunks = _chunk_markdown(text)
    else:
        chunks = _chunk_paragraphs(text)

    # Merge tiny chunks (only merge if under 10 words — truly empty sections)
    merged = _merge_small_chunks(chunks, min_words=3)

    # Re-index
    return [Chunk(c.title, c.text, i) for i, c in enumerate(merged)]


def _chunk_markdown(text: str) -> list[Chunk]:
    lines = text.split("\n")
    chunks = []
    current_title = "Introduction"
    current_lines: list[str] = []
    index = 0

    for line in lines:
        heading_match = re.match(r"^(#{1,3})\s+(.+)", line)
        if heading_match:
            # Save previous chunk if it has content
            if current_lines and "".join(current_lines).strip():
                chunks.append(Chunk(current_title, "\n".join(current_lines), index))
                index += 1
            current_title = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Last chunk
    if current_lines and "".join(current_lines).strip():
        chunks.append(Chunk(current_title, "\n".join(current_lines), index))

    return chunks if chunks else [Chunk("Content", text, 0)]


def _chunk_paragraphs(text: str) -> list[Chunk]:
    """Split on double newlines — paragraph-based chunking."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks = []
    index = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Try to extract a title from the first line
        lines = para.split("\n")
        first_line = lines[0].strip()

        # Use first line as title if it's short (likely a heading)
        if len(first_line) < 80 and len(lines) > 1:
            title = first_line
            body = "\n".join(lines[1:]).strip()
        else:
            title = f"Section {index + 1}"
            body = para

        if body:
            chunks.append(Chunk(title, body, index))
            index += 1

    return chunks if chunks else [Chunk("Content", text, 0)]


def _merge_small_chunks(chunks: list[Chunk], min_words: int = 3) -> list[Chunk]:
    """Only drop truly empty chunks (under min_words). Never merge sections together."""
    if not chunks:
        return chunks
    filtered = [c for c in chunks if c.word_count() >= min_words]
    return filtered if filtered else chunks[:1]
