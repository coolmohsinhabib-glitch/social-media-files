"""Turn one or more 1080x1350 images (carousel slides / cards) into a 1080x1920 Reel with music.

Usage: python3 image_reel.py out.mp4 --music classic|rising [--seconds-per 4] [--seed 7] img1.jpg [img2.jpg ...]
Each image sits on a blurred, darkened copy of itself, with a slow zoom; slides cross-fade.
Music: only Mohsin's approved tracks ("classic" = first-video music, "rising" = inspiring -> motivational),
with the builds/hits lined up to the slide changes. Loudness normalised to -14 LUFS.
"""
import argparse, os, subprocess, sys, tempfile
from PIL import Image, ImageFilter, ImageEnhance

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from music_classic import make_classic
from cinematic import make_cinematic

W, H, FPS = 1080, 1920, 30

def background(img):
    s = max(W / img.width, H / img.height)
    bg = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    l, t = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(40))
    return ImageEnhance.Brightness(bg).enhance(0.55)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("images", nargs="+")
    ap.add_argument("--music", default="classic", choices=["classic", "rising"])
    ap.add_argument("--seconds-per", type=float, default=4.0)
    ap.add_argument("--min-seconds", type=float, default=12.0)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    imgs = [Image.open(p).convert("RGB") for p in a.images]
    per = max(a.seconds_per, a.min_seconds / len(imgs))
    total = per * len(imgs); n = int(total * FPS); fade = int(0.4 * FPS)
    bgs = [background(im) for im in imgs]
    fw = 1000; fh = int(imgs[0].height * fw / imgs[0].width)
    tmp = tempfile.mkdtemp(); silent = os.path.join(tmp, "v.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", silent],
                         stdin=subprocess.PIPE)
    def frame(i, f):
        k = f / (per * FPS)                      # 0..1 within this slide
        z = 1.0 + 0.06 * k
        im = imgs[i].resize((int(fw * z), int(fh * z)), Image.LANCZOS)
        fr = bgs[i].copy(); fr.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        return fr
    for g in range(n):
        i = min(int(g / (per * FPS)), len(imgs) - 1); f = g - int(i * per * FPS)
        fr = frame(i, f)
        if i + 1 < len(imgs) and int((i + 1) * per * FPS) - g <= fade:   # cross-fade into the next slide
            t = 1 - (int((i + 1) * per * FPS) - g) / fade
            fr = Image.blend(fr, frame(i + 1, 0), t)
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    wav = os.path.join(tmp, "m.wav")
    cuts = [per * j for j in range(1, len(imgs))] or [min(3.0, total / 3), total * 0.6]
    if a.music == "classic": make_classic(total, wav)
    else: make_cinematic(total, wav, "rising", cuts=cuts, seed=a.seed)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=9", "-ar", "44100", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", a.out], check=True)
    print(f"Rendered {a.out}: {total:.1f}s, {len(imgs)} image(s), music={a.music}")

if __name__ == "__main__":
    main()
