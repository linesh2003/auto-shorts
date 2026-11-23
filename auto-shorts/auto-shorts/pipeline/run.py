"""Orchestrator — two commands:

  python -m pipeline.run produce   # find hype moments, render drafts, send to Telegram
  python -m pipeline.run publish   # read Telegram approvals, upload to YouTube

Local testing:
  python -m pipeline.run produce --count 1 --local path/to/video.mp4 --dry-run
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import moments, state as state_mod, telegram
from .config import Config, drafts_dir, work_dir
from .download import prepare
from .render import probe_ok, render_moment
from .upload import upload_video
from .utils import ffprobe_duration, log, setup_logging, slugify


# ---------------------------------------------------------------- produce
def cmd_produce(cfg: Config, count: int, local_file: str | None, dry_run: bool) -> int:
    state = state_mod.load()
    run_id = os.environ.get("GITHUB_RUN_ID", "local")

    sources = cfg.sources
    if local_file:
        sources = [{"type": "local_path", "path": local_file, "credit": "local"}]
    if not sources:
        print("no sources configured — edit config.yaml (see README step 5)")
        return 1

    candidates = []
    for src in sources:
        try:
            video, audio = prepare(src)
        except Exception as exc:  # keep going if one source fails
            log.error("source failed (%s): %s", src.get("url", src.get("path")), exc)
            continue
        duration = ffprobe_duration(video)
        log.info("source ready: %s (%.0fs)", video.name, duration)

        words = moments.transcribe(audio, cfg.whisper_model)
        energy = moments.audio_energy(audio)
        chat_json = work_dir() / (video.stem + ".json")  # optional, see README
        found = moments.find_moments(
            words, energy, cfg.keywords, duration,
            cfg.min_clip, cfg.max_clip, chat_json, top_k=count + 2,
        )
        for m in found:
            m["video"] = str(video)
            m["credit"] = src.get("credit", "")
            m["_words"] = words
        candidates.extend(found)

    if not candidates:
        print("no hype moments found — try more sources or loosen keywords")
        return 1

    candidates.sort(key=lambda m: m["score"], reverse=True)
    chosen = candidates[:count]

    produced = []
    for i, m in enumerate(chosen):
        draft_id = f"{state_mod.next_draft_id()}-{slugify(m['hook'] or 'clip', 20)}-{i}"
        out_path = drafts_dir() / f"{draft_id}.mp4"
        try:
            render_moment(Path(m["video"]), m, m["_words"], cfg, out_path, draft_id)
        except Exception as exc:
            log.error("render failed for %s: %s", draft_id, exc)
            continue
        if not probe_ok(out_path):
            log.error("render output invalid: %s", out_path)
            continue

        title = cfg.title_for(m["hook"])
        draft = {
            "id": draft_id,
            "run_id": run_id,
            "artifact": f"drafts-{run_id}",
            "status": "pending",
            "hook": m["hook"],
            "title": title,
            "credit": m.get("credit", ""),
            "source": m.get("video", ""),
            "created": state_mod.next_draft_id(),
        }
        state["drafts"].append(draft)
        produced.append((draft, out_path))

        caption = (
            f"🎬 DRAFT {draft_id}\n"
            f"Hook: {m['hook']}\n"
            f"Title: {title}\n"
            f"Score: {m['score']} | {m['duration']:.0f}s\n"
            f"→ reply  approve {draft_id}  to post"
        )
        if not dry_run:
            telegram.send_video(out_path, caption)

    state_mod.save(state)
    print(f"\n{len(produced)} draft(s) ready in drafts/:")
    for d, _p in produced:
        print(f"  {d['id']}  status={d['status']}  hook=\"{d['hook']}\"")
    print("next: reply 'approve <id>' in Telegram (or run publish locally with env set)")
    return 0


# ---------------------------------------------------------------- publish
APPROVE_RE = re.compile(r"approve\s+([a-z0-9\-]+)", re.IGNORECASE)
REJECT_RE = re.compile(r"reject\s+([a-z0-9\-]+)", re.IGNORECASE)


def _fetch_artifact(draft: dict) -> Path | None:
    """Download the draft mp4 from the produce run's artifacts via gh CLI."""
    target = drafts_dir() / f"{draft['id']}.mp4"
    if target.exists():
        return target
    tmp = work_dir() / f"art-{draft['id']}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["gh", "run", "download", str(draft["run_id"]),
             "-n", draft["artifact"], "-D", str(tmp)],
            check=True, capture_output=True, text=True, timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log.error("artifact download failed for %s: %s", draft["id"], exc)
        return None
    matches = list(tmp.rglob(f"{draft['id']}.mp4")) or list(tmp.rglob("*.mp4"))
    if not matches:
        log.error("artifact had no mp4 for %s", draft["id"])
        return None
    shutil.copy2(matches[0], target)
    return target


def cmd_publish(cfg: Config) -> int:
    state = state_mod.load()

    # 1) read approvals from Telegram
    updates, new_offset = telegram.get_updates(int(state.get("tg_offset", 0)))
    state["tg_offset"] = new_offset
    chat_allow = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    for u in updates:
        msg = u.get("message") or {}
        text = str(msg.get("text", ""))
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not text or (chat_allow and chat_id != chat_allow):
            continue
        for regex, new_status in ((APPROVE_RE, "approved"), (REJECT_RE, "rejected")):
            mobj = regex.search(text)
            if not mobj:
                continue
            draft_id = mobj.group(1)
            for d in state["drafts"]:
                if d["id"] == draft_id and d["status"] == "pending":
                    d["status"] = new_status
                    telegram.send_message(f"{draft_id} → {new_status}")
                elif d["id"] == draft_id:
                    telegram.send_message(f"{draft_id} is already {d['status']}")

    # 2) upload approved drafts, respecting the daily YouTube cap
    approved = [d for d in state["drafts"] if d["status"] == "approved"]
    budget = cfg.max_uploads_per_day - state_mod.uploads_today(state)
    for d in approved[: max(0, budget)]:
        path = _fetch_artifact(d)
        if not path:
            telegram.send_message(f"⚠️ could not fetch draft file for {d['id']} — will retry next hour")
            continue
        try:
            video_id = upload_video(
                path,
                title=d["title"],
                description=cfg.description_for(d["hook"], d.get("credit", "")),
                tags=cfg.yt_tags,
                category_id=cfg.yt_category_id,
                privacy=cfg.yt_privacy,
                made_for_kids=cfg.yt_made_for_kids,
            )
        except Exception as exc:
            log.error("upload failed for %s: %s", d["id"], exc)
            telegram.send_message(f"⚠️ upload failed for {d['id']}: {exc}"[:500])
            continue
        d["status"] = "uploaded"
        d["video_id"] = video_id
        state_mod.count_upload(state)
        telegram.send_message(
            f"🚀 LIVE: https://www.youtube.com/shorts/{video_id}\n(draft {d['id']})"
        )
        print(f"uploaded {d['id']} -> {video_id}")

    if not approved:
        print(f"nothing to upload ({state_mod.uploads_today(state)}/{cfg.max_uploads_per_day} used today)")

    state_mod.save(state)
    return 0


# ---------------------------------------------------------------- cli
def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(prog="shorts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_produce = sub.add_parser("produce", help="find moments, render drafts, notify")
    p_produce.add_argument("--count", type=int, default=None)
    p_produce.add_argument("--local", default=None, help="use a local video file instead of config sources")
    p_produce.add_argument("--dry-run", action="store_true", help="skip Telegram delivery")

    sub.add_parser("publish", help="process approvals and upload to YouTube")
    args = parser.parse_args()

    cfg = Config()
    if args.cmd == "produce":
        return cmd_produce(cfg, args.count or cfg.drafts_per_run, args.local, args.dry_run)
    return cmd_publish(cfg)


if __name__ == "__main__":
    sys.exit(main())
