from dataclasses import dataclass

from app.services.transcription import TranscriptSegment


@dataclass(slots=True)
class TranscriptChunk:
    chunk_index: int
    segment_start_index: int
    segment_end_index: int
    start_time: float
    end_time: float
    text: str


def chunk_segments(
    segments: list[TranscriptSegment],
    chunk_size: int,
    overlap: int,
) -> list[TranscriptChunk]:
    """
    Group consecutive Whisper segments into timestamped chunks.

    Example with chunk_size=10 and overlap=2:
      Chunk 0 -> segments 0..9
      Chunk 1 -> segments 8..17
      Chunk 2 -> segments 16..25

    The chunk timestamp range is:
      start_time = first segment's start
      end_time   = last segment's end
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not segments:
        return []

    step = chunk_size - overlap
    chunks: list[TranscriptChunk] = []

    for start_index in range(0, len(segments), step):
        group = segments[start_index : start_index + chunk_size]
        if not group:
            break

        text = " ".join(segment.text for segment in group).strip()
        if not text:
            continue

        end_index = start_index + len(group) - 1

        chunks.append(
            TranscriptChunk(
                chunk_index=len(chunks),
                segment_start_index=start_index,
                segment_end_index=end_index,
                start_time=group[0].start,
                end_time=group[-1].end,
                text=text,
            )
        )

        if end_index >= len(segments) - 1:
            break

    return chunks
