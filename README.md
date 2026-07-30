# Legadia — generación de vídeo sin API de pago

[![Abrir en Google Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/uptobe8/skyreels/blob/main/notebooks/LEGADIA_CogVideoX_Colab.ipynb)

Repositorio preparado para producir el anuncio de Legadia sin Runway, Higgsfield ni APIs de vídeo de pago.

## Pipeline

1. **CogVideoX-5B INT8** genera 49 fotogramas, el máximo oficial del modelo de seis segundos.
2. **FFmpeg** adapta el plano a 16:9, interpola a 25 fps y aplica una extensión temporal hasta 8,2 segundos.
3. **Edge TTS** genera la locución masculina de España sin clave API.
4. **LatentSync 1.5** intenta sincronizar la boca del hombre de la marquesina. Si la cara generada no resulta detectable, el pipeline continúa y conserva el vídeo base.
5. **FFmpeg + Pillow** incorporan el sonido, el texto español exacto y el cierre, y exportan el MP4 final de diez segundos en 1080p.

## Ejecutar

Pulse **Abrir en Google Colab**, seleccione **Entorno de ejecución > Cambiar tipo de entorno de ejecución > T4 GPU** y ejecute las cinco celdas en orden.

El notebook descarga este repositorio, instala las dependencias, ejecuta el pipeline, muestra el resultado y descarga automáticamente:

`/content/legadia/output/LEGADIA_FINAL_1080P.mp4`

## Sin pagos

No requiere claves de API de vídeo ni suscripciones. Utiliza la GPU gratuita de Google Colab, sujeta a disponibilidad y límites de sesión de Google.

## Control del resultado

El texto final no se delega al modelo generativo. Pillow lo compone con estas frases exactas:

- USTED AÚN NO LO SABE.
- PERO LE ESTAMOS BUSCANDO.
- PUEDE TENER PARTE DE UNA HERENCIA.
- DESCUBRA SU CASO AHORA

## Licencias

- CogVideoX: código Apache 2.0 y licencia específica de los pesos.
- LatentSync: código y pesos sujetos a sus licencias publicadas.
- Código original de este repositorio: MIT.
