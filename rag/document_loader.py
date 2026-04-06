"""
Load and chunk guideline documents for RAG ingestion.

Fix: sentence-aware chunking replaces character-based splitting.
Chunks always start and end at sentence boundaries — no more mid-sentence
truncation. Chunks are built by accumulating complete sentences until the
target size is reached, then overlapping by carrying forward the last
sentence(s) into the next chunk.
"""
from __future__ import annotations
import hashlib, re
from pathlib import Path
from app.core.config import settings

MIN_CHUNK_CHARS = 100


def _extract_pdf(path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(path))
    pages  = []
    for page in reader.pages:
        text = page.extract_text() or ""
        # Normalise whitespace — PDFs often have broken line endings
        text = re.sub(r"-\n", "", text)          # join hyphenated line breaks
        text = re.sub(r"\n+", " ", text)          # collapse newlines to spaces
        text = re.sub(r"\s{2,}", " ", text)       # collapse multiple spaces
        pages.append(text.strip())
    return " ".join(pages)


def _extract_plain(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using punctuation boundaries.
    Handles abbreviations like 'et al.' and 'vs.' to avoid false splits.
    """
    # Protect common abbreviations from being split
    protected = re.sub(
        r"\b(et al|vs|Dr|Mr|Mrs|Ms|Prof|Fig|No|Vol|pp|cf|i\.e|e\.g|approx|avg|min|max)\.",
        r"\1<DOT>",
        text,
        flags=re.IGNORECASE,
    )
    # Split on sentence-ending punctuation followed by space + capital letter
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\[\(])", protected)
    # Restore protected dots
    sentences = [s.replace("<DOT>", ".").strip() for s in raw if s.strip()]
    return sentences


def _chunk_sentences(sentences: list[str], target_size: int, overlap: int) -> list[str]:
    """
    Build chunks by accumulating complete sentences up to target_size characters.
    Overlap is achieved by carrying the last sentence(s) of each chunk into the next.

    This guarantees:
    - Every chunk starts at a sentence boundary
    - Every chunk ends at a sentence boundary
    - No sentence is split across chunks
    """
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len: int   = 0

    i = 0
    while i < len(sentences):
        sent     = sentences[i]
        sent_len = len(sent)

        # If a single sentence exceeds target size, keep it as its own chunk
        if not current and sent_len > target_size:
            chunks.append(sent)
            i += 1
            continue

        # Adding this sentence would exceed the target — finalise current chunk
        if current and current_len + sent_len + 1 > target_size:
            chunk_text = " ".join(current).strip()
            if len(chunk_text) >= MIN_CHUNK_CHARS:
                chunks.append(chunk_text)

            # Overlap: carry back sentences until we've covered `overlap` chars
            overlap_sents: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len >= overlap:
                    break
                overlap_sents.insert(0, s)
                overlap_len += len(s) + 1

            current     = overlap_sents
            current_len = overlap_len

        current.append(sent)
        current_len += sent_len + 1
        i += 1

    # Final chunk
    if current:
        chunk_text = " ".join(current).strip()
        if len(chunk_text) >= MIN_CHUNK_CHARS:
            chunks.append(chunk_text)

    return chunks


def load_and_chunk(
    file_path: Path,
    source_document: str,
    guideline_version: str,
    publication_year: int,
) -> tuple[list[str], list[dict]]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(file_path)
    elif suffix in {".txt", ".md"}:
        text = _extract_plain(file_path)
    else:
        raise ValueError(f"Unsupported format: {suffix}")

    sentences = _split_sentences(text)
    chunks    = _chunk_sentences(sentences, settings.chunk_size, settings.chunk_overlap)

    texts:    list[str]  = []
    payloads: list[dict] = []

    for i, chunk in enumerate(chunks):
        h = hashlib.sha256(chunk.encode()).hexdigest()
        texts.append(chunk)
        payloads.append({
            "source_document":   source_document,
            "guideline_version": guideline_version,
            "publication_year":  publication_year,
            "chunk_index":       i,
            "chunk_hash":        h,
        })

    return texts, payloads