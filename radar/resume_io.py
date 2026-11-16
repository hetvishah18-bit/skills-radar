"""Read resume text from PDF / DOCX / TXT bytes (used by the dashboard and the email digest)."""
import io
import os
from pathlib import Path


def read_resume_bytes(name: str, data: bytes) -> str:
    name = name.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        import docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    return data.decode("utf-8", errors="ignore")


def load_resume(path: str | Path | None) -> str:
    """Resume text from the RESUME_TEXT environment variable (handy for GitHub secrets) or a file."""
    if os.environ.get("RESUME_TEXT", "").strip():
        return os.environ["RESUME_TEXT"]
    if path and Path(path).exists():
        return read_resume_bytes(str(path), Path(path).read_bytes())
    return ""
