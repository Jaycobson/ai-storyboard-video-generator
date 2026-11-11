import io
import os
import time
import zipfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from pipeline.backends import OpenAIBackend
from pipeline.motion import ZOOM_MODE
from pipeline.studio import (finalize, list_projects, load_project, new_project, render_all,
                             render_scene, save_project)
from pipeline.video import ffmpeg_available

load_dotenv()
st.set_page_config(page_title="Story Studio", page_icon="🎬", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1150px; padding-top: 2rem;}
.hero {padding: 2.2rem 2.4rem; border-radius: 18px; color: #fff; margin-bottom: 1.5rem;
       background: linear-gradient(120deg, #4a1d96 0%, #c026d3 50%, #fb923c 100%);
       box-shadow: 0 6px 20px rgba(74, 29, 150, .28);}
.hero h1 {color: #ffffff; margin: 0 0 .3rem 0; font-size: 2.3rem;}
.hero p {color: #f6e8ff; margin: 0 0 1rem 0; font-size: 1.05rem; max-width: 70%;}
.chip {display: inline-block; padding: .25rem .8rem; margin: 0 .4rem .3rem 0; border-radius: 999px;
       background: rgba(255,255,255,.2); font-size: .85rem;}
.stButton > button {height: 3rem; font-weight: 600; border-radius: 10px;}
.stButton > button[kind="primary"] {background: linear-gradient(120deg, #c026d3, #fb923c); color: #fff; border: none;}
video::cue {font-size: 28px; color: #ffffff; background: rgba(0, 0, 0, 0.65);}
</style>
<div class="hero">
  <h1>🎬 Story Studio</h1>
  <p>AI plans the story, draws every scene, checks its own work, animates and narrates it. You review and approve.</p>
</div>
""", unsafe_allow_html=True)

EXAMPLE = ("Two children, Ife and Chidi, spend a sunny Saturday at a community playground in Lagos, "
           "learning to share, take turns and stay safe while they play.")
api_key = os.getenv("OPENAI_API_KEY")

story = st.text_area("💡 Your story, description or idea", EXAMPLE, height=130)
mode = ZOOM_MODE


def get_backend():
    return OpenAIBackend(api_key)


previous = list_projects()
if previous:
    with st.expander("📂 Open a previous project"):
        choice = st.selectbox("Project", previous, format_func=lambda p: f"{p[1]}  ({p[0].name})")
        if st.button("Open project"):
            st.session_state["proj"] = load_project(choice[0])
            st.rerun()

if st.button("✨ Create storyboard", type="primary", use_container_width=True):
    if not story.strip():
        st.warning("Please enter a story or idea first.")
    elif not api_key:
        st.error("OPENAI_API_KEY not found. Add it to your .env file.")
    elif not ffmpeg_available():
        st.error("FFmpeg/ffprobe not found. Install FFmpeg and make sure it is on your PATH.")
    else:
        try:
            t0 = time.time()
            with st.status("Planning and drawing your storyboard...", expanded=True) as status:
                bar = st.progress(0.0, text="Planning the story...")
                proj = new_project(story, api_key, Path("outputs") / time.strftime("%Y%m%d_%H%M%S"))
                render_all(proj, get_backend(), api_key,
                           lambda k, n: bar.progress(k / n, text=f"Drawing and checking scenes ({k}/{n})"))
                status.update(label="Storyboard ready for review", state="complete", expanded=False)
            proj["timings"]["storyboard"] = time.time() - t0
            st.session_state["proj"] = proj
        except Exception as e:
            st.error(f"Generation failed: {e}")

proj = st.session_state.get("proj")
if proj:
    plan, scenes, pid = proj["plan"], proj["scenes"], Path(proj["dir"]).name
    st.divider()
    st.subheader(plan["title"])
    with st.expander("🧠 AI plan: style and characters"):
        st.markdown(f"**Visual style:** {plan['style']}")
        for name, desc in plan["characters"].items():
            st.markdown(f"- **{name}:** {desc}")

    u = proj["usage"]
    m = st.columns(5)
    m[0].metric("Images made", u["images"])
    m[1].metric("QC checks", u["qc_checks"])
    m[2].metric("Narration clips", u["narration_clips"])
    m[3].metric("AI video clips", u["ai_video_clips"])
    approved = sum(s["approved"] for s in scenes)
    m[4].metric("Approved", f"{approved}/{len(scenes)}")
    t = proj.get("timings", {})
    st.caption("Usage counts show billable API calls. " + " · ".join(f"{k}: {v:.0f}s" for k, v in t.items()))

    st.markdown("### 🧑‍⚖️ Review each scene")
    if st.button("✅ Approve all scenes"):
        for i, s in enumerate(scenes):
            st.session_state[f"ap_{pid}_{i}_{len(s['versions'])}"] = True

    cols = st.columns(2, gap="large")
    for i, s in enumerate(scenes):
        ver = len(s["versions"])
        with cols[i % 2].container(border=True):
            st.markdown(f"**Scene {s['index']}**")
            st.image(s["image"], use_container_width=True)
            qc = s["qc"]
            if qc["score"] is None:
                st.caption("🔍 Quality check unavailable")
            else:
                icon = "🟢" if qc["pass"] else "🟠"
                st.caption(f"{icon} AI quality score {qc['score']}/10 · {qc['attempts']} attempt(s)")
                for issue in qc["issues"]:
                    st.caption(f"⚠️ {issue}")
            s["text"] = st.text_area("Narration", s["text"], key=f"tx_{pid}_{i}", height=90)
            key = f"ap_{pid}_{i}_{ver}"
            st.session_state.setdefault(key, s["approved"])
            s["approved"] = st.checkbox("Approved", key=key)
            note = st.text_input("Change request", key=f"nt_{pid}_{i}",
                                 placeholder="e.g. make Ife's dress orange and add a blue sky")
            if st.button("🔄 Regenerate this scene", key=f"rg_{pid}_{i}"):
                try:
                    with st.spinner("Redrawing..."):
                        ref = scenes[0]["image"] if i > 0 else None
                        render_scene(proj, i, get_backend(), api_key, note, ref)
                    st.rerun()
                except Exception as e:
                    st.error(f"Regeneration failed: {e}")
            if ver > 1:
                with st.expander(f"Version history ({ver})"):
                    st.image(s["versions"], width=110, caption=[f"v{k + 1}" for k in range(ver)])

    st.divider()
    ready = all(s["approved"] for s in scenes)
    if not ready:
        st.info("Approve every scene to unlock the final video.")
    if st.button("🎞️ Produce final video", type="primary", use_container_width=True, disabled=not ready):
        try:
            with st.status("Producing your video...", expanded=True) as status:
                bar = st.progress(0.0)
                w = {"narration": (0, .3, "Recording narration"), "motion": (.3, .5, "Animating scenes"),
                     "assemble": (.8, .2, "Assembling video")}

                def on_progress(stage, done, total):
                    a, span, label = w[stage]
                    bar.progress(min(a + span * done / total, 1.0), text=f"{label} ({done}/{total})")

                finalize(proj, mode, api_key, on_progress)
                status.update(label="Done", state="complete", expanded=False)
            st.rerun()
        except Exception as e:
            st.error(f"Video production failed: {e}")

    if proj["video"]:
        st.markdown("### 🎬 Final video")
        st.video(proj["video"], subtitles=(proj.get("subs") or {}).get("vtt"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in Path(proj["dir"]).iterdir():
                z.write(f, f.name)
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ Download video (MP4)", Path(proj["video"]).read_bytes(),
                           "story_video.mp4", "video/mp4", use_container_width=True)
        d2.download_button("📦 Download everything (ZIP)", buf.getvalue(),
                           "story_package.zip", "application/zip", use_container_width=True)
        if proj.get("subs"):
            d3.download_button("💬 Subtitles (SRT)", Path(proj["subs"]["srt"]).read_bytes(),
                               "story_subtitles.srt", "text/plain", use_container_width=True)

    save_project(proj)