"""Project logic for the review studio: plan, render with QC, regenerate with notes, finalise."""
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .motion import make_clip
from .narration import synthesize
from .planner import plan_story
from .qc import check_image
from .script_parser import Scene, build_prompt
from .subtitles import write_subtitles
from .video import assemble, audio_duration

MAX_FIXES = 2  # automatic regenerations when QC fails
_lock = threading.Lock()


def _count(project, key, n=1):
    with _lock:
        project["usage"][key] += n


def new_project(story, api_key, out_dir):
    plan = plan_story(story, api_key)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = []
    for i, s in enumerate(plan["scenes"], 1):
        prompt = build_prompt(Scene(i, s["text"], visual=s["visual"]), plan["characters"], plan["style"])
        scenes.append({"index": i, "text": s["text"], "visual": s["visual"], "motion": s["motion"],
                       "prompt": prompt, "versions": [], "image": None, "qc": None, "approved": False})
    return {"plan": plan, "scenes": scenes, "dir": str(out_dir), "usage": Counter(planning=1), "video": None,
            "timings": {}, "subs": None}


def render_scene(project, i, backend, api_key, note="", ref_path=None):
    """Generate scene i, let the AI reviewer check it, and auto-fix up to MAX_FIXES times."""
    sc = project["scenes"][i]
    base = sc["prompt"] + (f" Director's revision request: {note}." if note else "")
    prompt = base
    ref = Path(ref_path).read_bytes() if ref_path and backend.supports_reference else None
    chars = "; ".join(f"{n}: {d}" for n, d in project["plan"]["characters"].items())
    for attempt in range(MAX_FIXES + 1):
        png = backend.generate(prompt, reference=ref)
        _count(project, "images")
        path = Path(project["dir"]) / f"scene_{sc['index']:02d}_v{len(sc['versions']) + 1}.png"
        path.write_bytes(png)
        sc["versions"].append(str(path))
        sc["image"] = str(path)
        sc["qc"] = check_image(png, sc["visual"], chars, api_key)
        sc["qc"]["attempts"] = attempt + 1
        _count(project, "qc_checks")
        if sc["qc"]["pass"]:
            break
        prompt = base + " Fix these problems: " + "; ".join(sc["qc"]["issues"]) + "."
    sc["approved"] = False


def render_all(project, backend, api_key, on_progress=None):
    n = len(project["scenes"])
    render_scene(project, 0, backend, api_key)  # scene 1 becomes the reference for the rest
    if on_progress:
        on_progress(1, n)
    ref = project["scenes"][0]["image"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(render_scene, project, i, backend, api_key, "", ref) for i in range(1, n)]
        for k, f in enumerate(futures, 2):
            f.result()
            if on_progress:
                on_progress(k, n)


def finalize(project, mode, api_key, on_progress=None):
    notify = on_progress or (lambda stage, done, total: None)
    d, scenes = Path(project["dir"]), project["scenes"]
    n, t = len(scenes), time.time()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(synthesize, s["text"], d / f"scene_{s['index']:02d}.mp3", api_key) for s in scenes]
        for k, (s, f) in enumerate(zip(scenes, futures), 1):
            s["audio"] = str(f.result())
            notify("narration", k, n)
    _count(project, "narration_clips", n)
    project["timings"]["narration"] = time.time() - t
    t = time.time()
    talk = [audio_duration(s["audio"]) for s in scenes]
    clips = []
    for k, s in enumerate(scenes, 1):
        clip, used = make_clip(s["image"], s["motion"] or s["visual"], talk[k - 1] + 0.6, mode,
                               d / f"clip_{s['index']:02d}.mp4", api_key)
        s["motion_used"] = used
        if used == "ai":
            _count(project, "ai_video_clips")
        clips.append(clip)
        notify("motion", k, n)
    project["timings"]["motion"] = time.time() - t
    t = time.time()
    notify("assemble", 0, 1)
    project["video"] = str(assemble(clips, [s["audio"] for s in scenes], d / "video.mp4"))
    project["subs"] = write_subtitles([s["text"] for s in scenes], talk, d)
    project["timings"]["assemble"] = time.time() - t
    notify("assemble", 1, 1)
    save_project(project)


def save_project(project):
    (Path(project["dir"]) / "project.json").write_text(
        json.dumps({**project, "usage": dict(project["usage"])}, indent=2))


def load_project(path):
    data = json.loads((Path(path) / "project.json").read_text())
    data["usage"] = Counter(data.get("usage", {}))
    data.setdefault("timings", {})
    data.setdefault("subs", None)
    return data


def list_projects(root="outputs"):
    """Saved projects, newest first, as (folder, title)."""
    found = []
    for f in sorted(Path(root).glob("*/project.json"), reverse=True):
        try:
            found.append((f.parent, json.loads(f.read_text())["plan"]["title"]))
        except Exception:
            continue
    return found
