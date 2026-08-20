import logging
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import settings


logger = logging.getLogger(__name__)


class YtDlpLogger:
    """Route yt-dlp messages through the worker's application logger."""

    def debug(self, message: str) -> None:
        if message.startswith("[debug] "):
            logger.debug(message)
        else:
            logger.info(message)

    def info(self, message: str) -> None:
        logger.info(message)

    def warning(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.error(message)


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
        # Progressive mweb streams are more reliable than audio-only CDN URLs on
        # IPs where YouTube rejects large audio-only transfers with HTTP 403.
        # FFmpeg extracts the audio after download, so video quality is irrelevant.
        "format": settings.youtube_format,
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "logger": YtDlpLogger(),
        "retries": settings.youtube_download_retries,
        "fragment_retries": settings.youtube_download_retries,
        "extractor_retries": settings.youtube_download_retries,
        "extractor_args": {
            "youtube": {
                "player_client": [settings.youtube_player_client],
            },
            "youtubepot-bgutilhttp": {
                "base_url": [settings.youtube_pot_provider_url],
            },
        },
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
