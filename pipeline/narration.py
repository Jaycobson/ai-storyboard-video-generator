"""AI narration with a Nigerian-English delivery (OpenAI text-to-speech)."""
import os
from pathlib import Path

from .util import retry

INSTRUCTIONS = (
    "Speak as a warm, friendly narrator with a natural Nigerian English accent. "
    "Clear, calm and reassuring, at a gentle pace suited to a health education video."
)


@retry()
def synthesize(text, out_path, api_key=None, voice="coral"):
    from openai import OpenAI

    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    try:  # gpt-4o-mini-tts accepts style/accent instructions
        resp = client.audio.speech.create(model="gpt-4o-mini-tts", voice=voice, input=text,
                                          instructions=INSTRUCTIONS, response_format="mp3")
    except Exception:  # fallback: plain TTS without accent steering
        resp = client.audio.speech.create(model="tts-1", voice="nova", input=text, response_format="mp3")
    Path(out_path).write_bytes(resp.content)
    return Path(out_path)
