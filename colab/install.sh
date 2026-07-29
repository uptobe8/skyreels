#!/usr/bin/env bash
set -euo pipefail

apt-get -qq update
apt-get -qq install -y ffmpeg fonts-dejavu-core libgl1

python -m pip install -q \
  "torch==2.5.1" "torchvision==0.20.1" \
  "diffusers==0.32.2" "transformers==4.48.0" \
  "accelerate==1.2.1" "huggingface-hub==0.30.2" \
  "torchao==0.7.0" sentencepiece imageio imageio-ffmpeg \
  edge-tts pillow scipy uv

mkdir -p /content/legadia/output
nvidia-smi
