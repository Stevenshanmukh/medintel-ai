def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """
    Split text into overlapping character chunks.

    Designed to work on conversation transcripts where natural breakpoints
    (newlines, periods) are preferred over hard character cuts.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            search_zone = text[max(start, end - 100):end]
            local_break = -1
            for sep in ["\n\n", "\n", ". ", "? ", "! "]:
                idx = search_zone.rfind(sep)
                if idx > local_break:
                    local_break = idx + len(sep)
                    break
            if local_break > 0:
                end = max(start, end - 100) + local_break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - overlap

    return chunks
