from pathlib import Path
import json
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path('/content/skyreels')
OUT = Path('/content/legadia/output')
CONFIG = json.loads((REPO / 'prompts/legadia_video_request.json').read_text(encoding='utf-8'))
PREP_VIDEO = OUT / 'legadia_base_16x9_25fps.mp4'
LIPSYNCED = OUT / 'legadia_lipsynced_8_2s.mp4'
VOICE_1 = OUT / 'voice_part_1_8s.wav'
VOICE_2 = OUT / 'voice_part_2_1_5s.wav'
AMBIENCE = OUT / 'airport_ambience_original.wav'
FINAL_LINES = CONFIG['billboard_text']
CTA = CONFIG['cta']


def run(args):
    subprocess.run(args, check=True)


frame = OUT / 'end_frame.jpg'
run([
    'ffmpeg', '-y', '-ss', '8.1', '-i', str(PREP_VIDEO),
    '-frames:v', '1', str(frame)
])

img = Image.open(frame).convert('RGB').resize((1920, 1080))
img = img.filter(ImageFilter.GaussianBlur(radius=4))
overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)
draw.rectangle((0, 0, 1920, 1080), fill=(2, 11, 25, 150))
panel = (245, 115, 1675, 965)
draw.rounded_rectangle(
    panel, radius=28, fill=(4, 19, 42, 225),
    outline=(226, 177, 76, 235), width=5
)

font_bold = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
headline = ImageFont.truetype(font_bold, 72)
body = ImageFont.truetype(font_bold, 58)
cta_font = ImageFont.truetype(font_bold, 38)

draw.text((330, 200), FINAL_LINES[0], font=headline, fill=(255, 255, 255, 255))
draw.text((330, 350), FINAL_LINES[1], font=body, fill=(255, 255, 255, 255))
draw.text((330, 465), FINAL_LINES[2], font=body, fill=(226, 177, 76, 255))

button = (530, 720, 1390, 835)
draw.rounded_rectangle(button, radius=20, fill=(226, 177, 76, 255))
bbox = draw.textbbox((0, 0), CTA, font=cta_font)
tx = (button[0] + button[2] - (bbox[2] - bbox[0])) / 2
ty = (button[1] + button[3] - (bbox[3] - bbox[1])) / 2 - 5
draw.text((tx, ty), CTA, font=cta_font, fill=(3, 16, 35, 255))

end_card = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
end_card_path = OUT / 'legadia_end_card.png'
end_card.save(end_card_path, quality=95)

end_video = OUT / 'end_card_1_8s.mp4'
run([
    'ffmpeg', '-y', '-loop', '1', '-i', str(end_card_path),
    '-t', '1.8', '-r', '25',
    '-vf', "zoompan=z='min(zoom+0.0008,1.035)':d=45:s=1920x1080:fps=25",
    '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '14',
    '-pix_fmt', 'yuv420p', str(end_video)
])

voice_cta_delayed = OUT / 'voice_cta_delayed.wav'
run([
    'ffmpeg', '-y', '-i', str(VOICE_2),
    '-filter_complex', 'adelay=8200|8200,apad=pad_dur=10',
    '-t', '10', '-ar', '48000', '-ac', '1', str(voice_cta_delayed)
])

voice_main_delayed = OUT / 'voice_main_delayed.wav'
run([
    'ffmpeg', '-y', '-i', str(VOICE_1),
    '-filter_complex', 'adelay=200|200,apad=pad_dur=10',
    '-t', '10', '-ar', '48000', '-ac', '1', str(voice_main_delayed)
])

visual_master = OUT / 'legadia_visual_master_10s.mp4'
run([
    'ffmpeg', '-y', '-i', str(LIPSYNCED), '-i', str(end_video),
    '-filter_complex',
    '[0:v]scale=1920:1080:flags=lanczos,trim=duration=8.2,setpts=PTS-STARTPTS[v0];'
    '[1:v]trim=duration=1.8,setpts=PTS-STARTPTS[v1];'
    '[v0][v1]concat=n=2:v=1:a=0[v]',
    '-map', '[v]', '-t', '10',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '15',
    '-pix_fmt', 'yuv420p', str(visual_master)
])

final = OUT / 'LEGADIA_FINAL_1080P.mp4'
run([
    'ffmpeg', '-y',
    '-i', str(visual_master),
    '-i', str(AMBIENCE),
    '-i', str(voice_main_delayed),
    '-i', str(voice_cta_delayed),
    '-filter_complex',
    '[1:a]volume=0.62[a1];'
    '[2:a]volume=1.25[a2];'
    '[3:a]volume=1.30[a3];'
    '[a1][a2][a3]amix=inputs=3:duration=longest:normalize=0,'
    'alimiter=limit=0.95[a]',
    '-map', '0:v', '-map', '[a]', '-t', '10',
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k',
    '-movflags', '+faststart', str(final)
])

print('ARCHIVO FINAL:', final)
