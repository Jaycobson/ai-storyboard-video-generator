import base64

import pytest

from pipeline import studio
from pipeline.subtitles import write_subtitles
from pipeline.util import retry
from pipeline.video import ffmpeg_available, kenburns_clip

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
PLAN = {"title": "T", "style": "storybook", "characters": {"Ife": "orange dress"},
        "scenes": [{"text": "Ife runs.", "visual": "Ife runs in a park", "motion": "push in"}]}


class FakeBackend:
    supports_reference = True

    def __init__(self):
        self.calls = []

    def generate(self, prompt, reference=None):
        self.calls.append(prompt)
        return PNG


def test_qc_failure_triggers_fix_with_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "plan_story", lambda story, key: PLAN)
    verdicts = iter([{"score": 3, "issues": ["extra fingers"], "pass": False},
                     {"score": 9, "issues": [], "pass": True}])
    monkeypatch.setattr(studio, "check_image", lambda *a, **k: next(verdicts))
    backend, proj = FakeBackend(), studio.new_project("story", "key", tmp_path)
    studio.render_scene(proj, 0, backend, "key")
    sc = proj["scenes"][0]
    assert len(sc["versions"]) == 2 and sc["qc"]["pass"] and "extra fingers" in backend.calls[1]
    assert proj["usage"]["images"] == 2 and proj["usage"]["qc_checks"] == 2


def test_regeneration_note_and_project_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "plan_story", lambda story, key: PLAN)
    monkeypatch.setattr(studio, "check_image", lambda *a, **k: {"score": 9, "issues": [], "pass": True})
    backend, proj = FakeBackend(), studio.new_project("story", "key", tmp_path)
    studio.render_scene(proj, 0, backend, "key", note="make the dress blue")
    assert "make the dress blue" in backend.calls[0]
    studio.save_project(proj)
    loaded = studio.load_project(tmp_path)
    assert loaded["plan"]["title"] == "T" and loaded["usage"]["images"] == 1


def test_subtitles_are_timed_with_pause(tmp_path):
    files = write_subtitles(["One.", "Two."], [2.0, 3.0], tmp_path)
    srt = open(files["srt"], encoding="utf-8").read()
    assert "00:00:00,000 --> 00:00:02,000" in srt and "00:00:02,600 --> 00:00:05,600" in srt


def test_retry_recovers_but_not_on_client_errors():
    calls = {"n": 0}

    @retry(times=3, delay=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    assert flaky() == "ok"

    class Bad(Exception):
        status_code = 400

    @retry(times=3, delay=0)
    def rejected():
        calls["n"] += 1
        raise Bad()

    calls["n"] = 0
    with pytest.raises(Bad):
        rejected()
    assert calls["n"] == 1


@pytest.mark.skipif(not ffmpeg_available(), reason="FFmpeg not installed")
def test_kenburns_clip_is_created(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(PNG)
    assert kenburns_clip(img, tmp_path / "c.mp4", 1, size=64).stat().st_size > 0
