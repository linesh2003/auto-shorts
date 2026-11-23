"""Configuration loader: config.yaml + environment."""
import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _template(cfg_text: str, mapping: dict) -> str:
    out = cfg_text
    for key, value in mapping.items():
        out = out.replace("{" + key + "}", str(value))
    return out


class Config:
    """Thin convenience wrapper around config.yaml with sane defaults."""

    def __init__(self, path: Path | None = None):
        cfg_path = path or REPO_ROOT / "config.yaml"
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

        sched = raw.get("schedule", {})
        self.drafts_per_run = int(sched.get("drafts_per_run", 3))
        self.max_uploads_per_day = int(sched.get("max_uploads_per_day", 4))

        self.sources = raw.get("sources", []) or []
        self.keywords = [k.lower() for k in (raw.get("keywords") or [])]

        style = raw.get("style", {})
        self.width = int(style.get("width", 720))
        self.height = int(style.get("height", 1280))
        self.fps = int(style.get("fps", 30))
        self.crop_mode = str(style.get("crop_mode", "blur_pad"))
        self.min_clip = int(style.get("min_clip_seconds", 15))
        self.max_clip = int(style.get("max_clip_seconds", 45))
        self.hook_seconds = float(style.get("hook_seconds", 2.6))
        self.font = str(style.get("font", "DejaVu Sans"))
        self.font_size = int(style.get("font_size", 62))
        self.caption_margin_bottom = int(style.get("caption_margin_bottom", 150))

        self.whisper_model = str(raw.get("whisper_model", "small"))

        yt = raw.get("youtube", {})
        self.yt_privacy = str(yt.get("privacy", "public"))
        self.yt_made_for_kids = bool(yt.get("made_for_kids", False))
        self.yt_category_id = str(yt.get("category_id", "20"))
        self.yt_title_template = str(yt.get("title_template", "{hook} #shorts"))
        self.yt_description_template = str(yt.get("description_template", "{hook}"))
        self.yt_tags = list(yt.get("tags", ["shorts"]))

    def title_for(self, hook: str) -> str:
        return _template(self.yt_title_template, {"hook": hook})

    def description_for(self, hook: str, credit: str) -> str:
        return _template(
            self.yt_description_template, {"hook": hook, "credit": credit}
        ).strip()


def work_dir() -> Path:
    d = REPO_ROOT / "work"
    d.mkdir(exist_ok=True)
    return d


def drafts_dir() -> Path:
    d = REPO_ROOT / "drafts"
    d.mkdir(exist_ok=True)
    return d


def state_dir() -> Path:
    d = REPO_ROOT / "state"
    d.mkdir(exist_ok=True)
    return d
