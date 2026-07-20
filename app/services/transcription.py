from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from app.config import settings


@dataclass(slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@lru_cache
def get_whisper_model() -> WhisperModel:
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        download_root=settings.model_cache_dir,
    )


def transcribe_audio(audio_path: Path) -> list[TranscriptSegment]:
    model = get_whisper_model()

    segments_generator, _info = model.transcribe(
        str(audio_path),
        language=settings.whisper_language,
        beam_size=5,
        vad_filter=True,
    )

    segments: list[TranscriptSegment] = []
    for segment in segments_generator:
        text = segment.text.strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=text,
            )
        )

    return segments
