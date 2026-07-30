from pathlib import Path
import gc
import json
import subprocess

import torch
from diffusers import (
    AutoencoderKLCogVideoX,
    CogVideoXDPMScheduler,
    CogVideoXPipeline,
    CogVideoXTransformer3DModel,
)
from diffusers.utils import export_to_video
from torchao.quantization import int8_weight_only, quantize_
from transformers import T5EncoderModel

REPO = Path('/content/skyreels')
OUT = Path('/content/legadia/output')
OUT.mkdir(parents=True, exist_ok=True)
CONFIG = json.loads((REPO / 'prompts/legadia_video_request.json').read_text(encoding='utf-8'))
MODEL_ID = CONFIG['model']
BASE_VIDEO = OUT / 'legadia_base_6s.mp4'
PREP_VIDEO = OUT / 'legadia_base_16x9_25fps.mp4'
LIPS_VIDEO = OUT / 'legadia_visual_8_2s.mp4'


def quantize_int8(module):
    quantize_(module, int8_weight_only())
    return module


def run(args):
    subprocess.run(args, check=True)


def main():
    if not torch.cuda.is_available():
        raise RuntimeError('Active una GPU T4 en Google Colab antes de ejecutar.')

    dtype = torch.float16

    print('Cargando codificador de texto...')
    text_encoder = T5EncoderModel.from_pretrained(
        MODEL_ID,
        subfolder='text_encoder',
        torch_dtype=dtype,
    )
    quantize_int8(text_encoder)

    print('Cargando transformador...')
    transformer = CogVideoXTransformer3DModel.from_pretrained(
        MODEL_ID,
        subfolder='transformer',
        torch_dtype=dtype,
    )
    quantize_int8(transformer)

    print('Cargando VAE...')
    vae = AutoencoderKLCogVideoX.from_pretrained(
        MODEL_ID,
        subfolder='vae',
        torch_dtype=dtype,
    )
    quantize_int8(vae)

    pipe = CogVideoXPipeline.from_pretrained(
        MODEL_ID,
        text_encoder=text_encoder,
        transformer=transformer,
        vae=vae,
        torch_dtype=dtype,
    )
    pipe.scheduler = CogVideoXDPMScheduler.from_config(
        pipe.scheduler.config,
        timestep_spacing='trailing',
    )
    pipe.enable_sequential_cpu_offload()
    pipe.vae.enable_slicing()
    pipe.vae.enable_tiling()

    result = pipe(
        prompt=CONFIG['prompt'],
        negative_prompt=CONFIG['negative_prompt'],
        num_videos_per_prompt=1,
        num_inference_steps=40,
        num_frames=49,
        guidance_scale=6.0,
        use_dynamic_cfg=True,
        generator=torch.Generator(device='cuda').manual_seed(246801),
    )
    export_to_video(result.frames[0], str(BASE_VIDEO), fps=8)

    del pipe, transformer, text_encoder, vae, result
    gc.collect()
    torch.cuda.empty_cache()

    speed_factor = 8.2 / (49 / 8)
    video_filter = (
        'crop=iw:iw*9/16:0:(ih-iw*9/16)/2,'
        'scale=1280:720:flags=lanczos,'
        'minterpolate=fps=25:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,'
        f'setpts={speed_factor:.9f}*PTS,'
        'fps=25'
    )

    run([
        'ffmpeg', '-y', '-i', str(BASE_VIDEO),
        '-vf', video_filter,
        '-t', '8.2',
        '-an',
        '-c:v', 'libx264',
        '-preset', 'slow',
        '-crf', '16',
        '-pix_fmt', 'yuv420p',
        str(PREP_VIDEO),
    ])

    run([
        'ffmpeg', '-y', '-i', str(PREP_VIDEO),
        '-t', '8.2',
        '-an',
        '-c:v', 'libx264',
        '-preset', 'slow',
        '-crf', '16',
        '-pix_fmt', 'yuv420p',
        str(LIPS_VIDEO),
    ])

    print('Vídeo base preparado:', PREP_VIDEO)


if __name__ == '__main__':
    main()
