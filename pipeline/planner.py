"""Story planner: an OpenAI model turns a free-form idea into a storyboard (max 8 scenes)."""
import json
import os

MAX_SCENES = 8
MODELS = [os.getenv("OPENAI_PLANNER_MODEL"), "gpt-5.6", "gpt-4.1", "gpt-4o-mini"]  # tried in order

SYSTEM = f"""You are a storyboard director for short illustrated, narrated videos.
Given the user's story idea, reply with ONLY a JSON object:
{{"title": str, "visual_style": str, "characters": [{{"name": str, "description": str}}],
  "scenes": [{{"narration": str, "visual": str, "motion": str}}]}}
Rules:
- Choose the number of scenes the story needs: at least 3, never more than {MAX_SCENES}.
- narration: 1-2 short, warm sentences written to be read aloud. Use each character's first name exactly.
- visual: one sentence describing exactly what the image shows (setting, action, framing), naming the characters present.
- motion: a short phrase describing how the image should move if animated, e.g. "slow push-in as the children laugh".
- visual_style: one sentence of art direction that suits the story's mood and audience, used for every image.
- characters: recurring characters only (people, animals or creatures). Give each a concrete, fixed look
  (age, skin tone or fur, hair, clothing with colours) so they look identical in every scene.
- No text, captions or lettering inside the images. Keep content suitable for a general audience."""


def normalize_plan(data: dict, max_scenes: int = MAX_SCENES) -> dict:
    scenes = []
    for s in (data.get("scenes") or [])[:max_scenes]:
        narration = str(s.get("narration", "")).strip()
        if narration:
            scenes.append({"text": narration, "visual": str(s.get("visual", "")).strip() or narration,
                           "motion": str(s.get("motion", "")).strip()})
    if not scenes:
        raise ValueError("The planner returned no scenes.")
    chars = {}
    for c in data.get("characters") or []:
        name, desc = str(c.get("name", "")).strip(), str(c.get("description", "")).strip()
        if name and desc:
            chars[name] = desc
    return {"title": str(data.get("title") or "Untitled story").strip(),
            "style": str(data.get("visual_style") or "").strip() or "colourful illustration",
            "characters": chars, "scenes": scenes}


def plan_story(story: str, api_key=None) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    last = None
    for model in [m for m in MODELS if m]:
        try:
            resp = client.chat.completions.create(
                model=model, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": story}])
            return normalize_plan(json.loads(resp.choices[0].message.content))
        except Exception as e:
            last = e
    raise RuntimeError(f"Story planning failed: {last}")
