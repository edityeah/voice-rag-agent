"""Extract plain text from uploaded files."""
import io


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if name.endswith((".txt", ".md", ".markdown")):
        try:
            return data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="ignore").strip()
    raise ValueError(f"Unsupported file type: {filename}")
