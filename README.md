# Legadia — generación de vídeo sin API de pago

[![Abrir en Google Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/uptobe8/skyreels/blob/main/notebooks/LEGADIA_CogVideoX_Colab.ipynb)

Este repositorio contiene un notebook de Google Colab para producir el anuncio de Legadia sin Runway, Higgsfield ni APIs de vídeo de pago.

## Pipeline

1. **CogVideoX-5B INT8** genera el plano cinematográfico en una GPU T4 gratuita de Colab.
2. **Edge TTS** genera la locución masculina española sin clave API.
3. **LatentSync 1.5** sincroniza la boca del hombre de la marquesina con la locución.
4. **FFmpeg + Pillow** crean el diseño final, mezclan el sonido y exportan un MP4 de 10 segundos a 1080p.

## Ejecutar

Pulse el botón **Abrir en Google Colab**, seleccione **Entorno de ejecución > Cambiar tipo de entorno de ejecución > T4 GPU** y ejecute las celdas en orden.

Archivo final:

`/content/legadia/output/LEGADIA_FINAL_1080P.mp4`

## Sin pagos

No requiere claves de API de vídeo ni suscripciones. La única infraestructura es la GPU gratuita de Google Colab, sujeta a disponibilidad y límites de sesión.

## Calidad y control

El texto final no se deja al modelo generativo: se compone mediante Pillow para conservar exactamente el mensaje español y el CTA. La sincronización labial usa LatentSync 1.5, cuya inferencia publicada requiere 8 GB de VRAM. CogVideoX-5B se cuantiza a INT8 para adaptarse a la T4.

## Licencias

- Código CogVideoX: Apache 2.0; consulte también la licencia específica de sus pesos 5B.
- LatentSync: Apache 2.0.
- Código original de este repositorio: MIT.
