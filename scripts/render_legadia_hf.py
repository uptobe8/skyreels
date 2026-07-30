from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import edge_tts
import numpy as np
from gradio_client import Client, handle_file
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
WORK = ROOT / ".render-work"
CONFIG = json.loads((ROOT / "prompts" / "legadia_video_request.json").read_text(encoding="utf-8"))
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)
STATUS_PATH = OUT / "render_status.json"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(str(x) for x in args), flush=True)
    return subprocess.run(args, check=check, text=True)


def duration(path: Path) -> float:
    value = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ]).decode().strip()
    return float(value)


def find_media(value: Any, suffix: str) -> Path | None:
    if isinstance(value, str):
        p = Path(value)
        if p.exists() and p.suffix.lower() == suffix:
            return p
    if isinstance(value, dict):
        for key in ("path", "name", "video", "url", "value"):
            if key in value:
                found = find_media(value[key], suffix)
                if found:
                    return found
        for nested in value.values():
            found = find_media(nested, suffix)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        for nested in value:
            found = find_media(nested, suffix)
            if found:
                return found
    return None


def call_cogvideox(prompt: str) -> Path:
    client = Client("zai-org/CogVideoX-2B-Space")
    attempts = [
        {"api_name": "/generate"},
        {"api_name": "/predict"},
        {"fn_index": 0},
    ]
    errors: list[str] = []
    for route in attempts:
        try:
            print("CogVideoX route:", route, flush=True)
            result = client.predict(prompt, 40, 6.0, **route)
            media = find_media(result, ".mp4")
            if media:
                target = WORK / "cogvideox_base.mp4"
                shutil.copy2(media, target)
                return target
            errors.append(f"No MP4 in response using {route}: {result!r}")
        except Exception as exc:
            errors.append(f"{route}: {type(exc).__name__}: {exc}")
    raise RuntimeError("CogVideoX failed:\n" + "\n".join(errors))


async def synthesize_voice() -> Path:
    raw = WORK / "voice_raw.mp3"
    fitted = WORK / "voice_8s.wav"
    text = CONFIG["voice"]["text"]
    voice = CONFIG["voice"]["voice_id"]
    await edge_tts.Communicate(text, voice, rate="-2%", pitch="-2Hz").save(str(raw))
    original = duration(raw)
    tempo = original / 8.0
    filters: list[str] = []
    while tempo > 2.0:
        filters.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        filters.append("atempo=0.5")
        tempo /= 0.5
    filters.append(f"atempo={tempo:.7f}")
    filters.append("apad=pad_dur=8")
    run([
        "ffmpeg", "-y", "-i", str(raw), "-filter:a", ",".join(filters),
        "-t", "8", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(fitted),
    ])
    return fitted


def prepare_video(base: Path) -> Path:
    prepared = WORK / "visual_8s_25fps.mp4"
    source_duration = duration(base)
    factor = 8.0 / max(source_duration, 0.1)
    vf = (
        "crop=iw:iw*9/16:0:(ih-iw*9/16)/2,"
        "scale=1280:720:flags=lanczos,"
        f"setpts={factor:.9f}*PTS,"
        "minterpolate=fps=25:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        "fps=25"
    )
    run([
        "ffmpeg", "-y", "-i", str(base), "-vf", vf, "-t", "8", "-an",
        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
        str(prepared),
    ])
    return prepared


def call_latentsync(video: Path, audio: Path) -> tuple[Path, bool, str | None]:
    client = Client("fffiloni/LatentSync")
    attempts = [
        {"api_name": "/generate_lip_sync_video"},
        {"api_name": "/predict"},
        {"fn_index": 0},
    ]
    errors: list[str] = []
    for route in attempts:
        try:
            print("LatentSync route:", route, flush=True)
            result = client.predict(handle_file(str(video)), handle_file(str(audio)), **route)
            media = find_media(result, ".mp4")
            if media:
                target = WORK / "visual_lipsynced_8s.mp4"
                shutil.copy2(media, target)
                return target, True, None
            errors.append(f"No MP4 in response using {route}: {result!r}")
        except Exception as exc:
            errors.append(f"{route}: {type(exc).__name__}: {exc}")
    fallback = WORK / "visual_lipsynced_8s.mp4"
    shutil.copy2(video, fallback)
    return fallback, False, "\n".join(errors)


def create_ambience() -> Path:
    sr = 48000
    seconds = 10.0
    n = int(sr * seconds)
    t = np.arange(n) / sr
    rng = np.random.default_rng(20260730)
    noise = rng.normal(0, 1, n)
    signal = sosfilt(butter(4, 1400, btype="lowpass", fs=sr, output="sos"), noise) * 0.020
    signal += (np.sin(2 * np.pi * 46 * t) + 0.45 * np.sin(2 * np.pi * 73 * t)) * 0.011

    for when in np.arange(0.35, 7.7, 0.43):
        idx = int(when * sr)
        length = min(int(0.045 * sr), n - idx)
        env = np.exp(-np.linspace(0, 8, length))
        signal[idx:idx + length] += rng.normal(0, 1, length) * env * 0.045

    def impact(when: float, amp: float, length: float = 0.7) -> None:
        idx = int(when * sr)
        count = min(int(length * sr), n - idx)
        x = np.arange(count) / sr
        env = np.exp(-5 * x / length)
        signal[idx:idx + count] += (
            np.sin(2 * np.pi * 58 * x) + 0.5 * np.sin(2 * np.pi * 93 * x)
        ) * env * amp

    def whoosh(start: float, length: float, amp: float) -> None:
        idx = int(start * sr)
        count = min(int(length * sr), n - idx)
        x = np.linspace(0, 1, count)
        sweep = sosfilt(
            butter(2, [300, 7000], btype="bandpass", fs=sr, output="sos"),
            rng.normal(0, 1, count),
        )
        signal[idx:idx + count] += sweep * (np.sin(np.pi * x) ** 2) * amp

    impact(1.15, 0.16)
    whoosh(2.9, 1.3, 0.09)
    impact(4.15, 0.20)
    whoosh(5.15, 1.1, 0.08)
    signal[int(5.9 * sr):int(6.35 * sr)] *= 0.08
    impact(9.55, 0.22)
    signal = np.clip(signal, -0.95, 0.95)
    path = WORK / "airport_ambience.wav"
    wavfile.write(path, sr, (signal * 32767).astype(np.int16))
    return path


def create_end_card(source_video: Path) -> Path:
    frame = WORK / "end_frame.jpg"
    run(["ffmpeg", "-y", "-ss", "7.7", "-i", str(source_video), "-frames:v", "1", str(frame)])
    img = Image.open(frame).convert("RGB").resize((1920, 1080))
    img = img.filter(ImageFilter.GaussianBlur(radius=4))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1920, 1080), fill=(2, 11, 25, 158))
    draw.rounded_rectangle((245, 115, 1675, 965), radius=28, fill=(4, 19, 42, 230), outline=(226, 177, 76, 240), width=5)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    headline = ImageFont.truetype(font_path, 72)
    body = ImageFont.truetype(font_path, 58)
    cta_font = ImageFont.truetype(font_path, 38)
    lines = CONFIG["billboard_text"]
    draw.text((330, 200), lines[0], font=headline, fill=(255, 255, 255, 255))
    draw.text((330, 350), lines[1], font=body, fill=(255, 255, 255, 255))
    draw.text((330, 465), lines[2], font=body, fill=(226, 177, 76, 255))
    button = (530, 720, 1390, 835)
    draw.rounded_rectangle(button, radius=20, fill=(226, 177, 76, 255))
    cta = CONFIG["cta"]
    bbox = draw.textbbox((0, 0), cta, font=cta_font)
    tx = (button[0] + button[2] - (bbox[2] - bbox[0])) / 2
    ty = (button[1] + button[3] - (bbox[3] - bbox[1])) / 2 - 5
    draw.text((tx, ty), cta, font=cta_font, fill=(3, 16, 35, 255))
    final_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    card = WORK / "end_card.png"
    final_img.save(card)
    video = WORK / "end_card_2s.mp4"
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(card), "-t", "2", "-r", "25",
        "-vf", "zoompan=z='min(zoom+0.0008,1.035)':d=50:s=1920x1080:fps=25",
        "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", str(video),
    ])
    return video


def master(video8: Path, voice: Path, ambience: Path, end_card: Path) -> Path:
    visual = WORK / "visual_master_10s.mp4"
    run([
        "ffmpeg", "-y", "-i", str(video8), "-i", str(end_card),
        "-filter_complex",
        "[0:v]scale=1920:1080:flags=lanczos,trim=duration=8,setpts=PTS-STARTPTS[v0];"
        "[1:v]trim=duration=2,setpts=PTS-STARTPTS[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-t", "10", "-c:v", "libx264", "-preset", "slow", "-crf", "15",
        "-pix_fmt", "yuv420p", str(visual),
    ])
    final = OUT / "LEGADIA_FINAL_1080P.mp4"
    run([
        "ffmpeg", "-y", "-i", str(visual), "-i", str(ambience), "-i", str(voice),
        "-filter_complex",
        "[1:a]volume=0.58[a1];[2:a]adelay=150|150,apad=pad_dur=10,volume=1.28[a2];"
        "[a1][a2]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]",
        "-map", "0:v", "-map", "[a]", "-t", "10", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
        "-movflags", "+faststart", str(final),
    ])
    return final


def write_status(status: str, **extra: Any) -> None:
    payload = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


def main() -> int:
    write_status("starting", stage="initialization")
    try:
        prompt = CONFIG["prompt"]
        base = call_cogvideox(prompt)
        write_status("running", stage="voice")
        voice = asyncio.run(synthesize_voice())
        prepared = prepare_video(base)
        write_status("running", stage="lipsync")
        lip_video, lip_ok, lip_error = call_latentsync(prepared, voice)
        ambience = create_ambience()
        end_card = create_end_card(prepared)
        final = master(lip_video, voice, ambience, end_card)
        write_status(
            "completed" if lip_ok else "completed_without_lipsync",
            stage="done",
            output=str(final.relative_to(ROOT)),
            size_bytes=final.stat().st_size,
            lip_sync=lip_ok,
            lip_sync_error=lip_error,
        )
        return 0
    except Exception as exc:
        write_status(
            "failed",
            stage="exception",
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
