from pathlib import Path
import asyncio
import json
import subprocess

import edge_tts
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

REPO = Path('/content/skyreels')
OUT = Path('/content/legadia/output')
CONFIG = json.loads((REPO / 'prompts/legadia_video_request.json').read_text(encoding='utf-8'))
VOICE = CONFIG['voice']['voice_id']
TEXT_1 = 'Usted aún no lo sabe, pero le estamos buscando porque puede tener parte de una herencia.'
TEXT_2 = 'Descubra su caso ahora.'


def media_duration(path):
    return float(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1', str(path)
    ]).decode().strip())


def fit_audio(source, target, seconds):
    tempo = media_duration(source) / seconds
    if not 0.5 <= tempo <= 2.0:
        raise RuntimeError(f'No se puede ajustar el tempo automáticamente: {tempo:.3f}')
    subprocess.run([
        'ffmpeg', '-y', '-i', str(source),
        '-filter:a', f'atempo={tempo:.6f},apad=pad_dur={seconds}',
        '-t', str(seconds), '-ar', '16000', '-ac', '1',
        '-c:a', 'pcm_s16le', str(target)
    ], check=True)


async def synthesize():
    await edge_tts.Communicate(TEXT_1, VOICE, rate='-2%', pitch='-2Hz').save(
        str(OUT / 'voice_part_1_raw.mp3')
    )
    await edge_tts.Communicate(TEXT_2, VOICE, rate='-2%', pitch='-2Hz').save(
        str(OUT / 'voice_part_2_raw.mp3')
    )


def create_ambience():
    sr = 48000
    duration = 10.0
    n = int(sr * duration)
    t = np.arange(n) / sr
    rng = np.random.default_rng(20260730)

    noise = rng.normal(0, 1, n)
    terminal = sosfilt(
        butter(4, 1400, btype='lowpass', fs=sr, output='sos'), noise
    ) * 0.022
    rumble = (np.sin(2*np.pi*46*t) + 0.45*np.sin(2*np.pi*73*t)) * 0.012
    signal = terminal + rumble

    for when in np.arange(0.4, 7.8, 0.42):
        idx = int(when * sr)
        length = int(0.045 * sr)
        env = np.exp(-np.linspace(0, 8, length))
        signal[idx:idx+length] += rng.normal(0, 1, length) * env * 0.05

    def impact(when, amp=0.22, length=0.7):
        idx = int(when * sr)
        count = min(int(length * sr), len(signal) - idx)
        x = np.arange(count) / sr
        env = np.exp(-5*x/length)
        signal[idx:idx+count] += (
            np.sin(2*np.pi*58*x) + 0.5*np.sin(2*np.pi*93*x)
        ) * env * amp

    def whoosh(start, length=0.9, amp=0.10):
        idx = int(start * sr)
        count = min(int(length * sr), len(signal) - idx)
        x = np.linspace(0, 1, count)
        sweep = rng.normal(0, 1, count)
        sweep = sosfilt(
            butter(2, [300, 7000], btype='bandpass', fs=sr, output='sos'),
            sweep
        )
        signal[idx:idx+count] += sweep * (np.sin(np.pi*x) ** 2) * amp

    impact(1.25, 0.18)
    whoosh(3.1, 1.2, 0.10)
    impact(4.2, 0.20)
    whoosh(5.3, 1.0, 0.08)
    impact(9.55, 0.22)
    signal[int(6.0*sr):int(6.45*sr)] *= 0.10
    signal = np.clip(signal, -0.95, 0.95)
    wavfile.write(
        OUT / 'airport_ambience_original.wav', sr,
        (signal * 32767).astype(np.int16)
    )


asyncio.run(synthesize())
fit_audio(OUT / 'voice_part_1_raw.mp3', OUT / 'voice_part_1_8s.wav', 8.0)
fit_audio(OUT / 'voice_part_2_raw.mp3', OUT / 'voice_part_2_1_5s.wav', 1.5)
create_ambience()
print('Voz y ambiente creados.')
