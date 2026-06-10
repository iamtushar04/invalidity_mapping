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
        
        # Prevent infinite loop: remaining MUST shrink!
        next_start = split_at - chunk_overlap
        if next_start <= 0:
            next_start = split_at  # Force it to shrink by the exact chunk we extracted
            
        remaining = remaining[next_start:]

    if remaining.strip():
        chunks.append(remaining.strip())

    return chunks