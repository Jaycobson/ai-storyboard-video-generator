"""FFmpeg helpers: Ken Burns clips and final assembly with narration."""
import shutil
import subprocess
import tempfile
from pathlib import Path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def run(cmd):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cmd], check=True)


def audio_duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def kenburns_clip(image, out, dur, fps=25, size=1024) -> Path:
    frames = int(dur * fps)
    vf = (f"scale={size*2}:{size*2}:force_original_aspect_ratio=increase,crop={size*2}:{size*2},"
          f"zoompan=z='min(zoom+0.0012,1.2)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"s={size}x{size}:fps={fps},format=yuv420p")
    run(["-i", str(image), "-vf", vf, "-t", f"{dur:.2f}", "-c:v", "libx264", "-r", str(fps), str(out)])
    return Path(out)


def assemble(clips, audios, out_path, size=1024, pad=0.6, fps=25) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        segs = []
        for i, (clip, audio) in enumerate(zip(clips, audios)):
            seg = Path(tmp) / f"seg_{i:03d}.mp4"
            dur = audio_duration(audio) + pad
            run(["-stream_loop", "-1", "-i", str(clip), "-i", str(audio), "-t", f"{dur:.2f}",
                 "-vf", f"scale={size}:{size},format=yuv420p", "-r", str(fps), "-af", "apad",
                 "-ar", "44100", "-ac", "2", "-c:v", "libx264", "-c:a", "aac", str(seg)])
            segs.append(seg)
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs))
        run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out_path)])
    return Path(out_path)
