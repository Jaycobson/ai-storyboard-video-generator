"""Subtitle files (WebVTT for the in-app player, SRT for download) timed to the narration."""
from pathlib import Path


def _ts(sec: float, comma: bool) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{',' if comma else '.'}{ms:03d}"


def write_subtitles(texts, durations, out_dir, pad=0.6) -> dict:
    cues, t = [], 0.0
    for text, dur in zip(texts, durations):
        cues.append((t, t + dur, text))
        t += dur + pad  # matches the pause FFmpeg adds after each scene
    vtt = "WEBVTT\n\n" + "".join(f"{_ts(a, False)} --> {_ts(b, False)}\n{x}\n\n" for a, b, x in cues)
    srt = "".join(f"{i}\n{_ts(a, True)} --> {_ts(b, True)}\n{x}\n\n" for i, (a, b, x) in enumerate(cues, 1))
    out = Path(out_dir)
    (out / "subtitles.vtt").write_text(vtt, encoding="utf-8")
    (out / "subtitles.srt").write_text(srt, encoding="utf-8")
    return {"vtt": str(out / "subtitles.vtt"), "srt": str(out / "subtitles.srt")}
