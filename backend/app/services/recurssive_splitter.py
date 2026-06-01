def chunk_full_claim(
    claim_text: str,
    chunk_size: int = 1500,
    chunk_overlap: int = 250,
    max_words_without_chunking: int = 900,
) -> list[str]:

    word_count = len(claim_text.split())
    if word_count <= max_words_without_chunking:
        return [claim_text]

    separators = ["; wherein", "; and", ";", ", wherein", ", and", ",", ". ", " "]

    chunks = []
    remaining = claim_text

    while len(remaining) > chunk_size:
        split_at = -1
        for sep in separators:
            idx = remaining.rfind(sep, 0, chunk_size)
            if idx != -1:
                split_at = idx + len(sep)
                break

        if split_at == -1:
            split_at = chunk_size

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[max(0, split_at - chunk_overlap):]

    if remaining.strip():
        chunks.append(remaining.strip())

    return chunks