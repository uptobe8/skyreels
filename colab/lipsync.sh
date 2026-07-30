#!/usr/bin/env bash
set -euo pipefail

OUT=/content/legadia/output
LATENT=/content/LatentSync
ENV=/content/latentsync_env
INPUT_VIDEO="$OUT/legadia_visual_8_2s.mp4"
OUTPUT_VIDEO="$OUT/legadia_lipsynced_8_2s.mp4"
AUDIO="$OUT/voice_part_1_8s.wav"

rm -rf "$LATENT" "$ENV"
git clone -q https://github.com/bytedance/LatentSync.git "$LATENT"
cd "$LATENT"
git checkout -q 75a4a1733c7314a8f6bf092f1fbe4ced008cccd7

uv python install 3.10
uv venv --seed --python 3.10 "$ENV"
"$ENV/bin/pip" -q install -r requirements.txt
"$ENV/bin/pip" -q install "huggingface-hub==0.25.2"

"$ENV/bin/python" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='ByteDance/LatentSync-1.5',
    local_dir='/content/LatentSync/checkpoints',
    ignore_patterns=['*.git*', 'README.md'],
)
PY

mkdir -p "$HOME/.cache/torch/hub/checkpoints"
ln -sfn "$LATENT/checkpoints/auxiliary/2DFAN4-cd938726ad.zip" "$HOME/.cache/torch/hub/checkpoints/2DFAN4-cd938726ad.zip"
ln -sfn "$LATENT/checkpoints/auxiliary/s3fd-619a316812.pth" "$HOME/.cache/torch/hub/checkpoints/s3fd-619a316812.pth"
ln -sfn "$LATENT/checkpoints/auxiliary/vgg16-397923af.pth" "$HOME/.cache/torch/hub/checkpoints/vgg16-397923af.pth"

set +e
"$ENV/bin/python" -m scripts.inference \
  --unet_config_path configs/unet/stage2.yaml \
  --inference_ckpt_path checkpoints/latentsync_unet.pt \
  --inference_steps 20 \
  --guidance_scale 1.5 \
  --video_path "$INPUT_VIDEO" \
  --audio_path "$AUDIO" \
  --video_out_path "$OUTPUT_VIDEO"
STATUS=$?
set -e

if [ "$STATUS" -ne 0 ] || [ ! -s "$OUTPUT_VIDEO" ]; then
  cp "$INPUT_VIDEO" "$OUTPUT_VIDEO"
  echo "LatentSync no pudo procesar la cara; se conserva el vídeo para completar el master."
else
  echo "Sincronización labial terminada."
fi
