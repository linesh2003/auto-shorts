"""Pipeline state: state/state.json (committed back to the repo by Actions)."""
import datetime as _dt
import json
from pathlib import Path

from .config import state_dir

STATE_FILE = Path(__file__).resolve().parent.parent / "state" / "state.json"


def load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"tg_offset": 0, "drafts": [], "uploads_by_date": {}}


def save(state: dict) -> None:
    state_dir().mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def next_draft_id() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("d%Y%m%d-%H%M%S")


def uploads_today(state: dict) -> int:
    today = _dt.date.today().isoformat()
    return int(state.get("uploads_by_date", {}).get(today, 0))


def count_upload(state: dict) -> None:
    today = _dt.date.today().isoformat()
    by_date = state.setdefault("uploads_by_date", {})
    by_date[today] = int(by_date.get(today, 0)) + 1
    # keep only the last 14 days so the file stays small
    keys = sorted(by_date)
    for old in keys[:-14]:
        by_date.pop(old, None)
