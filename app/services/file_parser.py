import io
from fastapi import UploadFile, HTTPException

SUPPORTED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/markdown": "md",
    "text/plain": "txt",
    "text/x-markdown": "md",
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


def get_file_type(filename: str, content_type: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == ".doc":
        raise HTTPException(
            status_code=400,
            detail=".doc (old Word format) is not supported. Please save as .docx and re-upload."
        )
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Accepted: .pdf .docx .md .txt"
        )

    type_map = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".txt": "txt"}
    return type_map[ext]


async def parse_file(file: UploadFile) -> tuple[str, str]:
    """Returns (extracted_text, file_type)"""
    content = await file.read()

    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    file_type = get_file_type(file.filename or "unknown.txt", file.content_type or "")

    if file_type == "pdf":
        text = _parse_pdf(content)
    elif file_type == "docx":
        text = _parse_docx(content)
    else:
        text = content.decode("utf-8", errors="replace")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Could not extract text from file. The file may be empty or image-only.")

    return text, file_type


def _parse_pdf(content: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
        return "\n\n".join(pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")


def _parse_docx(content: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse DOCX: {str(e)}")


def count_words(text: str) -> int:
    return len(text.split())
