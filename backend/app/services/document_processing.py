from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.core.config import get_settings


@dataclass(frozen=True)
class ParsedPage:
    text: str
    page_number: int | None


@dataclass(frozen=True)
class TextChunk:
    content: str
    chunk_index: int
    page_number: int | None


def parse_document(path: Path) -> list[ParsedPage]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(ParsedPage(text=text, page_number=index + 1))
        return pages
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8").strip()
        return [ParsedPage(text=text, page_number=None)] if text else []
    raise ValueError("仅支持 PDF、Markdown 和 TXT 文档")


def split_pages(pages: list[ParsedPage]) -> list[TextChunk]:
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        length_function=len,
    )
    chunks: list[TextChunk] = []
    for page in pages:
        for content in splitter.split_text(page.text):
            normalized = content.strip()
            if normalized:
                chunks.append(
                    TextChunk(
                        content=normalized,
                        chunk_index=len(chunks),
                        page_number=page.page_number,
                    )
                )
    return chunks
