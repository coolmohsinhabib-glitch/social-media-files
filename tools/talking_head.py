"""Talking-head Reel template (style: Elevate Commerce / podcast clips) for Mohsin's own recorded clips.

Usage:
  python3 talking_head.py spec.json out.mp4

spec.json:
{
  "clip": "path/to/mohsin-talking.mp4",      # his recording (any orientation; cropped to 9:16)
  "start": 0, "seconds": null,                 # optional trim
  "pill": "eBay TIP #04",                      # small orange label above the title (optional)
  "title": ["eBay par sale", "*nahi* ho rahi?"],   # 1-3 lines, *word* = yellow
  "reply": {"name": "ayeshanazar21", "text": "Sir ..."},   # optional: TikTok-style "Reply to comment" bubble (REAL comments only)
  "captions": [[0.0, 2.5, "Listing hai, *views* bhi hain"], ...],  # optional burned-in captions (start, end, text)
  "music": "rising" | "classic" | null,       # optional soft bed under his voice (approved tracks only)
  "music_db": -22                              # bed level relative to voice
}
Bottom bar always shows the IDB logo, his name/title and both phone numbers.
"""
import json, os, subprocess, sys, tempfile, re
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
FONTS = os.path.join(ROOT, "assets", "fonts")
ANTON = os.path.join(FONTS, "Anton-Regular.ttf")
PEB = os.path.join(FONTS, "Poppins-ExtraBold.ttf")
PB = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
PM = "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf"
LOGO = os.path.join(ROOT, "assets", "idb-logo-badge.png")
W, H = 1080, 1920
YELLOW, WHITE, ORANGE = (255, 212, 0), (255, 255, 255), (242, 112, 54)


def segs(text):
    """'a *b* c' -> [('a ', False), ('b', True), (' c', False)]"""
    out = []
    for i, p in enumerate(re.split(r"\*", text)):
        if p:
            out.append((p, i % 2 == 1))
    return out


def draw_rich(d, x_center, y, text, font, stroke=6, upper=False):
    parts = [(t.upper() if upper else t, hi) for t, hi in segs(text)]
    widths = [d.textlength(t, font=font) for t, _ in parts]
    x = x_center - sum(widths) / 2
    for (t, hi), w in zip(parts, widths):
        d.text((x, y), t, font=font, fill=YELLOW if hi else WHITE, stroke_width=stroke, stroke_fill=(0, 0, 0))
        x += w


def fit(d, lines, path, max_w, start):
    size = start
    while size > 40:
        f = ImageFont.truetype(path, size)
        if all(d.textlength(re.sub(r"\*", "", l).upper(), font=f) <= max_w for l in lines):
            return f
        size -= 4
    return ImageFont.truetype(path, size)


def static_overlay(spec, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # soft dark gradients top and bottom for readability
    g = Image.new("L", (1, H))
    for yy in range(H):
        a = 0
        if yy < 760: a = int(170 * (1 - yy / 760) ** 1.3)
        if yy > 1380: a = int(210 * ((yy - 1380) / 540) ** 1.2)
        g.putpixel((0, yy), a)
    im.paste((0, 0, 0, 255), (0, 0), g.resize((W, H)))
    d = ImageDraw.Draw(im)
    y = 150
    if spec.get("pill"):
        f = ImageFont.truetype(PEB, 40)
        tw = d.textlength(spec["pill"], font=f)
        d.rounded_rectangle(((W - tw) / 2 - 30, y, (W + tw) / 2 + 30, y + 70), 35, fill=ORANGE)
        d.text((W / 2, y + 35), spec["pill"], font=f, fill=WHITE, anchor="mm")
        y += 100
    lines = spec.get("title", [])
    if lines:
        f = fit(d, lines, ANTON, W - 120, 150)
        lh = int(f.size * 1.08)
        for l in lines:
            draw_rich(d, W / 2, y, l, f, stroke=7, upper=True)
            y += lh
        y += 30
    r = spec.get("reply")
    if r:
        fs, fb = ImageFont.truetype(PM, 30), ImageFont.truetype(PB, 40)
        words, rows, cur = r["text"].split(), [], ""
        for w_ in words:
            t = (cur + " " + w_).strip()
            if d.textlength(t, font=fb) > 700: rows.append(cur); cur = w_
            else: cur = t
        rows.append(cur)
        bw = max([d.textlength(x, font=fb) for x in rows] + [d.textlength(f"Reply to {r['name']}'s comment", font=fs) + 70]) + 60
        bh = 80 + 52 * len(rows)
        x0 = (W - bw) / 2
        d.rounded_rectangle((x0, y, x0 + bw, y + bh), 26, fill=(255, 255, 255, 245))
        d.polygon([(x0 + 60, y + bh), (x0 + 100, y + bh), (x0 + 70, y + bh + 30)], fill=(255, 255, 255, 245))
        d.ellipse((x0 + 26, y + 22, x0 + 66, y + 62), fill=(200, 200, 200))
        d.text((x0 + 80, y + 42), f"Reply to {r['name']}'s comment", font=fs, fill=(90, 90, 90), anchor="lm")
        for i, row in enumerate(rows):
            d.text((x0 + 30, y + 78 + 52 * i), row, font=fb, fill=(15, 15, 15))
    # bottom brand bar
    by = 1650
    d.rounded_rectangle((40, by, W - 40, by + 210), 34, fill=(10, 18, 40, 225))
    if os.path.exists(LOGO):
        lg = Image.open(LOGO).convert("RGBA")
        s = 150 / lg.height
        lg = lg.resize((int(lg.width * s), 150))
        im.alpha_composite(lg, (70, by + 30))
        tx = 70 + lg.width + 30
    else:
        tx = 80
    d.text((tx, by + 42), "Mohsin Habib", font=ImageFont.truetype(PEB, 46), fill=WHITE)
    d.text((tx, by + 100), "CFO & Co-Founder, IDB Pakistan", font=ImageFont.truetype(PM, 30), fill=(200, 210, 230))
    d.text((tx, by + 145), "+92 319 3498717  |  Office +92 300 1514327", font=ImageFont.truetype(PB, 29), fill=YELLOW)
    im.save(path)


def caption_png(text, path):
    im = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = fit(d, [text], PEB, W - 140, 74)
    draw_rich(d, W / 2, 80, text, f, stroke=8)
    im.save(path)


def main():
    spec = json.load(open(sys.argv[1])); out = sys.argv[2]
    tmp = tempfile.mkdtemp()
    ov = os.path.join(tmp, "ov.png"); static_overlay(spec, ov)
    clip = spec["clip"]
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip]).decode().strip())
    start = float(spec.get("start", 0)); secs = spec.get("seconds") or (dur - start)
    inputs = ["-ss", str(start), "-t", str(secs), "-i", clip, "-i", ov]
    fc = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[b];[b][1:v]overlay=0:0[v0]"
    last = "v0"
    for i, (a, b, t) in enumerate(spec.get("captions", [])):
        p = os.path.join(tmp, f"c{i}.png"); caption_png(t, p)
        inputs += ["-i", p]
        fc += f";[{last}][{i + 2}:v]overlay=0:1330:enable='between(t,{a},{b})'[v{i + 1}]"; last = f"v{i + 1}"
    has_audio = bool(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", clip]).strip())
    music = spec.get("music")
    aidx = len(inputs) // 2  # every input above is "-i x" plus optional -ss/-t pairs; recount below
    n_inputs = sum(1 for x in inputs if x == "-i")
    if music:
        wav = os.path.join(tmp, "m.wav")
        if music == "classic":
            from music_classic import make_classic; make_classic(secs, wav)
        else:
            from cinematic import make_cinematic; make_cinematic(secs, wav, "rising", cuts=[], seed=spec.get("music_seed", 5))
        inputs += ["-i", wav]
        db = spec.get("music_db", -22)
        if has_audio:
            fc += f";[0:a]volume=1.0[va];[{n_inputs}:a]volume={db}dB[ma];[va][ma]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]"
        else:
            fc += f";[{n_inputs}:a]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    elif has_audio:
        fc += ";[0:a]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", f"[{last}]"]
    if music or has_audio:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
    cmd += ["-t", str(secs), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    print("Rendered", out, f"{secs:.1f}s")


if __name__ == "__main__":
    main()
