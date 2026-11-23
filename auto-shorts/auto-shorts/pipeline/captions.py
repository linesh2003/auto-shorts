"""ASS subtitle builder — the viral "karaoke pop caption" look.

How the look works (libass):
  - lines are UPPERCASE, bold, white with a thick black outline, bottom-centered
  - karaoke \\k tags fill each word from white -> yellow exactly when it is spoken
  - each line pops with a quick scale-down + fade-in
  - a big yellow hook banner sits at the top for the first few seconds
"""
from pathlib import Path

from .utils import log

# ASS colours are &HAABBGGRR (alpha, blue, green, red) — 00 alpha = opaque
YELLOW = "&H0000FFFF"
WHITE = "&H00FFFFFF"
BLACK = "&H00000000"


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def _fmt_words(words: list[dict]) -> str:
    return " ".join(_escape(w["word"]).upper() for w in words)


def _chunk_words(words: list[dict], max_words: int = 3, max_chars: int = 16) -> list[list[dict]]:
    """Split words into short caption lines (2-3 words is the Shorts norm)."""
    lines: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        candidate_len = len(" ".join(x["word"] for x in current + [w]))
        if current and (len(current) >= max_words or candidate_len > max_chars):
            lines.append(current)
            current = []
        current.append(w)
    if current:
        lines.append(current)
    return lines


def _caption_events(words_window: list[dict], cfg, offset: float) -> list[str]:
    """Karaoke caption dialogue lines, times relative to clip start."""
    events: list[str] = []
    margin_v = cfg.caption_margin_bottom

    for line_words in _chunk_words(words_window):
        line_start = line_words[0]["start"] - offset
        line_end = line_words[-1]["end"] - offset + 0.25
        if line_start < 0:
            continue

        # \k durations in centiseconds, incl. silent gaps before each word
        karaoke = ""
        prev_end = line_words[0]["start"]
        for w in line_words:
            dur_cs = max(8, round((w["end"] - prev_end) * 100))
            karaoke += f"{{\\k{dur_cs}}}{_escape(w['word']).upper()} "
            prev_end = w["end"]

        pop = "{\\fad(60,40)\\t(0,110,\\fscx114\\fscy114)\\t(110,210,\\fscx100\\fscy100)}"
        text = f"{pop}{karaoke.strip()}"
        events.append(
            f"Dialogue: 0,{_ass_time(line_start)},{_ass_time(line_end)},"
            f"Caption,,0,0,{margin_v},,{text}"
        )
    return events


def _fit_hook(hook: str, cfg) -> tuple[str, int]:
    """Wrap the hook to <=2 lines and shrink font until it fits the width."""
    text = _escape(hook).upper()
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > 12:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    lines = lines[:2]  # never more than 2 lines

    size = int(cfg.font_size * 1.45)
    longest = max(len(l) for l in lines)
    while size > 44 and longest * size * 0.62 > (cfg.width - 40):
        size -= 4
    return "\\N".join(lines), size


def _hook_event(hook: str, cfg) -> str:
    end = max(1.2, cfg.hook_seconds)
    text, size = _fit_hook(hook, cfg)
    pop = "{\\fad(120,160)\\t(0,150,\\fscx120\\fscy120)\\t(150,300,\\fscx100\\fscy100)}"
    return (
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(end)},"
        f"Hook,,0,0,60,,{pop}{{\\fs{size}}}{text}"
    )


def build_ass(
    words_window: list[dict],
    hook: str,
    cfg,
    out_path: Path,
    offset: float = 0.0,
) -> Path:
    """Write the .ass file for one clip.

    words_window: transcript words whose times are absolute (VOD time)
    offset: clip start time — event times are relative to it
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.width}
PlayResY: {cfg.height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{cfg.font},{cfg.font_size},{YELLOW},{WHITE},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,7,1,2,40,40,{cfg.caption_margin_bottom},1
Style: Hook,{cfg.font},{int(cfg.font_size * 1.45)},{YELLOW},{WHITE},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,9,1,8,30,30,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    if hook:
        events.append(_hook_event(hook, cfg))
    caption_events = _caption_events(words_window, cfg, offset)
    if caption_events:
        events.extend(caption_events)
    else:
        log.info("no words in this window — captions skipped, hook only")

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path
