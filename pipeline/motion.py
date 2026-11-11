"""Scene motion: free Ken Burns zoom, or real AI video (OpenAI video API) with automatic fallback."""
import os
import time
from pathlib import Path

import requests

from .video import kenburns_clip, run

ZOOM_MODE = "Smooth zoom (free, fast)"
AI_MODE = "AI video (OpenAI, slower and costs more)"
API = "https://api.openai.com/v1/videos"


def _openai_clip(image, motion, out: Path, api_key) -> Path:
    headers = {"Authorization": f"Bearer {api_key}"}
    ref, raw = out.with_suffix(".ref.png"), out.with_suffix(".raw.mp4")
    # The video API wants 1280x720: centre the square image, animate, then crop the centre back out.
    run(["-i", str(image), "-vf", "scale=720:720,pad=1280:720:(ow-iw)/2:0", str(ref)])
    prompt = f"{motion}. Keep the characters and art style exactly as in the reference image. No text."
    with open(ref, "rb") as f:
        r = requests.post(API, headers=headers, timeout=120,
                          data={"model": os.getenv("SORA_MODEL", "sora-2"), "prompt": prompt,
                                "size": "1280x720", "seconds": "4"},
                          files={"input_reference": ("ref.png", f, "image/png")})
    r.raise_for_status()
    vid, deadline = r.json()["id"], time.time() + 600
    while time.time() < deadline:
        info = requests.get(f"{API}/{vid}", headers=headers, timeout=30).json()
        if info.get("status") == "completed":
            break
        if info.get("status") == "failed":
            raise RuntimeError("AI video generation failed")
        time.sleep(5)
    else:
        raise TimeoutError("AI video timed out")
    raw.write_bytes(requests.get(f"{API}/{vid}/content", headers=headers, timeout=120).content)
    run(["-i", str(raw), "-vf", "crop=720:720:(iw-720)/2:0,scale=1024:1024,format=yuv420p", "-an", str(out)])
    return out


def make_clip(image, motion, dur, mode, out, api_key):
    """Returns (clip_path, 'ai' | 'zoom'). Any AI failure falls back to the zoom so the run still finishes."""
    out = Path(out)
    if mode == AI_MODE:
        try:
            return _openai_clip(image, motion, out, api_key), "ai"
        except Exception:
            pass
    return kenburns_clip(image, out, dur), "zoom"
