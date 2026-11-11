"""AI quality control: a vision model checks each generated image against its scene."""
import base64
import json
import os

from .planner import MODELS

PASS_SCORE = 7


def check_image(png: bytes, visual: str, characters: str, api_key=None) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    instruction = (
        "You are a strict quality reviewer for illustrated videos. Check this image against the brief.\n"
        f"Scene it must show: {visual}\nCharacter looks: {characters or 'none specified'}\n"
        "Look for: scene mismatch, wrong or inconsistent character looks, distorted hands/faces/limbs, "
        "any text or lettering in the image, unsafe or confusing content.\n"
        'Reply ONLY with JSON: {"score": integer 0-10, "issues": [short strings]}. Use an empty list if fine.')
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    for model in [m for m in MODELS if m]:
        try:
            resp = client.chat.completions.create(
                model=model, response_format={"type": "json_object"},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": url}}]}])
            data = json.loads(resp.choices[0].message.content)
            score = int(data.get("score", 0))
            issues = [str(i) for i in (data.get("issues") or [])][:4]
            return {"score": score, "issues": issues, "pass": score >= PASS_SCORE}
        except Exception:
            continue
    return {"score": None, "issues": ["Quality check unavailable"], "pass": True}
