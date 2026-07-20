from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import settings


@dataclass(slots=True)
class DownloadedVideo:
    audio_path: Path
    title: str | None
    channel_name: str | None
    duration: float | None


def download_youtube_audio(video_id: str, youtube_url: str) -> DownloadedVideo:
    video_dir = Path(settings.data_dir) / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(video_dir / "source.%(ext)s")

    ydl_options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(youtube_url, download=True)

    audio_path = video_dir / "source.wav"
    if not audio_path.exists():
        matches = list(video_dir.glob("source.*"))
        if not matches:
            raise RuntimeError("yt-dlp completed but no audio file was produced.")
        audio_path = matches[0]

    return DownloadedVideo(
        audio_path=audio_path,
        title=info.get("title"),
        channel_name=info.get("channel") or info.get("uploader"),
        duration=float(info["duration"]) if info.get("duration") is not None else None,
    )
