"""Renderer: cut a moment from the source VOD into a vertical Short,
burning in the karaoke captions and the hook banner with ffmpeg/libass."""
import shutil
import subprocess
from pathlib import Path

from .captions import build_ass
from .config import Config, work_dir
from .utils import ffprobe_duration, log, run_ffmpeg


def _video_filters(cfg: Config, src_label: str = "0:v") -> str:
    """Landscape -> vertical conversion filters (input: the pre-cut clip)."""
    w, h = cfg.width, cfg.height
    if cfg.crop_mode == "center":
        return (
            f"[{src_label}]crop=ih*{w}/{h}:ih,scale={w}:{h}:flags=bicubic,setsar=1,fps={cfg.fps}[base]"
        )
    # blur_pad (default): full frame over a blurred background
    return (
        f"[{src_label}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"boxblur=24:6[bg];"
        f"[{src_label}]scale=-2:{h}:flags=bicubic[fg];"
        f"[bg][fg]overlay=(W-w)/2:0,setsar=1,fps={cfg.fps}[base]"
    )


def _keyframe_before(video: Path, t: float) -> float:
    """Find the last keyframe at or before t — lets pass 1 fast-seek there
    while the output-side -ss still lands frame-accurately on t."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-skip_frame", "nokey", "-show_entries", "frame=pts_time",
            "-of", "csv=p=0",
            "-read_intervals", f"{max(0.0, t - 30):.3f}%{t + 0.1:.3f}",
            str(video),
        ],
        capture_output=True, text=True, check=True,
    )
    kfs = []
    for line in out.stdout.strip().splitlines():
        try:
            k = float(line.strip().rstrip(","))
        except ValueError:
            continue
        if k <= t:
            kfs.append(k)
    return max(kfs) if kfs else 0.0


def render_moment(
    source_video: Path,
    moment: dict,
    all_words: list[dict],
    cfg: Config,
    out_path: Path,
    draft_id: str,
) -> Path:
    """Two passes (both proven-stable, no trim/atrim filters):

      pass 1 "cut":  exact window -> near-lossless intermediate, 0-based pts
                     (input -ss = fast keyframe pre-seek, output -ss = precise)
      pass 2 "style": vertical conversion + karaoke captions burn-in

    The ass file's event times are relative to the clip start, and pass 2's
    input starts exactly at the clip start — so everything lines up.
    """
    start = float(moment["start"])
    dur = float(moment["duration"])
    words_window = [
        w for w in all_words if w["start"] >= start and w["end"] <= start + dur
    ]

    work = work_dir()
    ass_path = build_ass(words_window, moment.get("hook", ""), cfg, work / f"{draft_id}.ass", offset=start)
    safe_path = (
        ass_path.as_posix()
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )

    cut_path = work / f"{draft_id}.cut.mp4"
    seek_in = _keyframe_before(source_video, start)
    log.info("rendering %s (%.1fs from %.1fs)", draft_id, dur, start)

    # pass 1 — exact cut, high-quality intermediate
    run_ffmpeg(
        [
            "-ss", f"{seek_in:.3f}", "-i", str(source_video),
            "-ss", f"{start - seek_in:.3f}", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(cut_path),
        ]
    )

    # pass 2 — vertical conversion + captions on the clean 0-based clip
    filter_complex = f"{_video_filters(cfg)};[base]ass='{safe_path}'[vout]"
    run_ffmpeg(
        [
            "-i", str(cut_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", "-shortest",
            str(out_path),
        ]
    )
    cut_path.unlink(missing_ok=True)

    _enforce_telegram_size(out_path)
    return out_path


def _enforce_telegram_size(out_path: Path, limit_mb: float = 47.0) -> None:
    """Telegram bot API rejects videos > 50 MB — re-encode smaller if needed."""
    size_mb = out_path.stat().st_size / 1e6
    if size_mb <= limit_mb:
        return
    log.info("draft is %.1f MB — re-encoding at lower bitrate", size_mb)
    tmp = out_path.with_suffix(".small.mp4")
    run_ffmpeg(
        [
            "-i", str(out_path),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "29",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            str(tmp),
        ]
    )
    shutil.move(str(tmp), str(out_path))


def probe_ok(path: Path) -> bool:
    """Sanity check a rendered draft: real duration, not corrupted."""
    try:
        dur = ffprobe_duration(path)
        return dur > 1.0
    except (subprocess.CalledProcessError, KeyError, ValueError):
        return False
