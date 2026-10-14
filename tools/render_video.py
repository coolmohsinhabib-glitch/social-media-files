#!/usr/bin/env python3
"""Render a branded vertical (1080x1920) graphic video with original music.

Usage: python3 render_video.py scenes.json out.mp4 [--no-music]

Scene JSON:
{
  "brand": {"name": "Mohsin Habib", "title": "CFO & Co-Founder, IDB Pakistan",
            "phone": "+92 319 3498717", "series": "eBay TIP #01"},
  "scenes": [
    {"type": "hook", "seconds": 3.5, "text": "Big hook line", "accent": ["words", "in", "orange"]},
    {"type": "steps", "seconds": 8, "title": "Heading", "note": "optional",
     "lines": [["Label", "value"], ...], "highlight": 4},
    {"type": "cta", "seconds": 4, "text": "Follow for daily eBay tips"}
  ]
}
Music is generated here (original, royalty-free). Pick a style per video with "music": pop | drive | bright | chill | hype.
Optional "intro_clip": {path, start, seconds, hook, accent} opens on real footage with the hook text from frame 1.
"""
import json, math, os, random, subprocess, sys, tempfile, wave
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, BPM = 1080, 1920, 30, 120
BEAT = 60 / BPM
NAVY = (14, 24, 62); NAVY2 = (27, 44, 102); ORANGE = (224, 94, 62); ORANGE2 = (255, 142, 96)
WHITE = (255, 255, 255); MUTED = (170, 184, 224); CARD = (34, 52, 118); CARD_EDGE = (62, 84, 160)
FD = "/usr/share/fonts/truetype/google-fonts/"
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

@lru_cache(maxsize=512)
def font(weight, size):
    size = max(8, int(size))
    for name in (f"Poppins-{weight}.ttf", "Poppins-Bold.ttf"):
        try: return ImageFont.truetype(FD + name, size)
        except OSError: pass
    return ImageFont.truetype(DEJAVU, size)

def clamp(t): return max(0.0, min(1.0, t))
def ease(t): t = clamp(t); return 1 - (1 - t) ** 3
def back(t):  # ease-out with overshoot
    t = clamp(t); c1 = 1.9; c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
def mix(a, b, k): return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
def pulse(gt):  # 1 on each beat, decays fast
    return math.exp(-((gt % BEAT) / BEAT) * 5)

# ---------- static layers ----------
def make_base():
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=mix(NAVY, NAVY2, y / H))
    for y in range(40, H, 60):
        for x in range(30, W, 60):
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=mix(NAVY2, MUTED, 0.18))
    return img

def blob(color, r, alpha):
    s = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0))
    ImageDraw.Draw(s).ellipse([r, r, r * 3, r * 3], fill=color + (alpha,))
    return s.filter(ImageFilter.GaussianBlur(r * 0.45))

_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "idb-logo-badge.png")
LOGO = None
if os.path.exists(_LOGO_PATH):
    _l = Image.open(_LOGO_PATH).convert("RGBA"); LOGO = _l.resize((int(_l.width * 104 / _l.height), 104), Image.LANCZOS)

BASE = make_base()
BLOBS = [(blob(ORANGE, 230, 120), 860, 260, 0.0), (blob((70, 110, 255), 260, 110), 120, 1180, 1.7),
         (blob(ORANGE, 170, 80), 900, 1500, 3.1)]

def background(gt):
    img = BASE.copy()
    for spr, cx, cy, ph in BLOBS:
        x = int(cx + math.sin(gt * 0.5 + ph) * 90 - spr.width / 2)
        y = int(cy + math.cos(gt * 0.4 + ph) * 70 - spr.height / 2)
        img.paste(spr, (x, y), spr)
    return img

# ---------- shared chrome ----------
def phone_icon(d, x, y, s, color):
    d.rounded_rectangle([x, y, x + s * 0.62, y + s], s * 0.14, outline=color, width=max(3, int(s * 0.09)))
    d.line([x + s * 0.22, y + s * 0.82, x + s * 0.40, y + s * 0.82], fill=color, width=max(3, int(s * 0.08)))

def header(d, brand, gt):
    k = 1 + 0.06 * pulse(gt)
    f = font("SemiBold", 34)
    label = brand.get("series", "eBay TIP")
    tw = d.textlength(label, font=f)
    pad = 26 * k
    d.rounded_rectangle([80, 150 - 6 * (k - 1) * 10, 80 + tw + pad * 2, 212 + 6 * (k - 1) * 10], 32, fill=ORANGE)
    d.text((80 + pad, 157), label, font=f, fill=WHITE)
    lw = LOGO.width if LOGO else 0
    if not LOGO: d.text((W - 80, 166), "IDB PAKISTAN", font=font("SemiBold", 30), fill=MUTED, anchor="ra")

def footer(d, brand):
    d.line([80, H - 270, W - 80, H - 270], fill=CARD_EDGE, width=2)
    d.text((80, H - 238), brand["name"], font=font("Bold", 46), fill=WHITE)
    d.text((80, H - 178), brand["title"], font=font("Regular", 32), fill=MUTED)
    if brand.get("phone"):
        f = font("SemiBold", 36)
        tw = d.textlength(brand["phone"], font=f)
        phone_icon(d, W - 80 - tw - 52, H - 228, 40, ORANGE2)
        d.text((W - 80, H - 230), brand["phone"], font=f, fill=WHITE, anchor="ra")

def progress(d, frame, total):
    d.rectangle([0, H - 12, W, H], fill=mix(NAVY, CARD, 0.8))
    d.rectangle([0, H - 12, int(W * frame / max(1, total - 1)), H], fill=ORANGE)

def wipe(d, t):  # orange panel sliding away at scene start
    if t < 0.4:
        x0 = int(-W * ease(t / 0.4))
        d.rectangle([x0, 0, x0 + W, H], fill=ORANGE)

# ---------- scenes ----------
def layout_words(d, text, f, maxw, x0, y0, lh):
    pos = []; y = y0
    for para in text.split("\n"):
        line = []; lw = 0
        for w in para.split():
            ww = d.textlength(w, font=f); sp = d.textlength(" ", font=f) if line else 0
            if line and lw + sp + ww > maxw:
                pos += [(wd, x0 + ox, y) for wd, ox in line]; y += lh; line = []; lw = 0; sp = 0
            line.append((w, lw + sp)); lw += sp + ww
        pos += [(wd, x0 + ox, y) for wd, ox in line]; y += lh
    return pos, y

def draw_hook(d, s, t, gt):
    f = font("Bold", 100)
    words, _ = layout_words(d, s["text"], f, W - 160, 80, 560, 128)
    accent = {a.lower() for a in s.get("accent", [])}
    for i, (w, x, y) in enumerate(words):
        a = (t - 0.15 - i * 0.12) / 0.35
        if a <= 0: continue
        sc = 0.5 + 0.5 * back(a)
        col = ORANGE2 if w.lower().strip(".,?!") in accent else WHITE
        fw = font("Bold", 100 * sc)
        ww = d.textlength(w, font=f)
        d.text((x + ww / 2, y + 60), w, font=fw, fill=mix(NAVY, col, ease(a)), anchor="mm")
    # underline sweeps in after the words
    k = ease((t - 0.25 - len(words) * 0.12) / 0.5)
    if k > 0:
        y = words[-1][2] + 150 if words else 900
        d.rounded_rectangle([80, y, 80 + int(360 * k), y + 14], 7, fill=ORANGE)

def draw_steps(d, s, t, dur, gt):
    a0 = ease((t - 0.25) / 0.4)
    d.text((80 + int(40 * (1 - a0)), 300), s["title"], font=font("Bold", 74), fill=mix(NAVY, WHITE, a0))
    y = 400
    if s.get("note"):
        d.text((80, y), s["note"], font=font("Regular", 32), fill=mix(NAVY, MUTED, a0)); y += 56
    y += 34
    n = len(s["lines"]); step = (dur * 0.62) / n
    lf, vf = font("Medium", 38), font("Bold", 50)
    for i, (label, value) in enumerate(s["lines"]):
        a = (t - 0.45 - i * step) / 0.45
        if a <= 0: break
        hl = s.get("highlight") == i + 1
        x = 80 + int(W * 0.5 * (1 - back(a)))
        words, _ = layout_words(d, value, vf, W - 330, 0, 0, 62)
        rows = max(1, len({p[2] for p in words}))
        bh = 112 + 62 * rows
        glow = pulse(gt) if hl and a > 1 else 0
        if hl:
            g = int(10 + 12 * glow)
            d.rounded_rectangle([x - g, y - g, x + W - 160 + g, y + bh + g], 30 + g, fill=mix(NAVY2, ORANGE, 0.35))
        fill = ORANGE if hl else CARD
        d.rounded_rectangle([x, y, x + W - 160, y + bh], 28, fill=mix(NAVY, fill, ease(a)),
                            outline=None if hl else CARD_EDGE, width=2)
        # number badge
        bc = (x + 70, y + bh / 2)
        d.ellipse([bc[0] - 38, bc[1] - 38, bc[0] + 38, bc[1] + 38], fill=WHITE if hl else ORANGE)
        d.text(bc, str(i + 1), font=font("Bold", 40), fill=ORANGE if hl else WHITE, anchor="mm")
        tx = x + 140
        d.text((tx, y + 24), label, font=lf, fill=WHITE if hl else MUTED)
        for w, wx, wy in words:
            d.text((tx + wx, y + 80 + wy), w, font=vf, fill=WHITE)
        y += bh + 26

def draw_cta(d, s, t, gt, brand):
    f = font("Bold", 88)
    words, yend = layout_words(d, s["text"], f, W - 160, 80, 470, 112)
    for i, (w, x, y) in enumerate(words):
        a = (t - 0.2 - i * 0.08) / 0.35
        if a <= 0: continue
        sc = 0.5 + 0.5 * back(a)
        ww = d.textlength(w, font=f)
        col = ORANGE2 if w.lower() in ("follow", "daily") else WHITE
        d.text((x + ww / 2, y + 56), w, font=font("Bold", 88 * sc), fill=mix(NAVY, col, ease(a)), anchor="mm")
    if brand.get("phone"):
        a = (t - 0.4 - len(words) * 0.08) / 0.5
        if a > 0:
            k = back(a) * (1 + 0.04 * pulse(gt))
            y = yend + 70
            d.text((80, y), "Contact", font=font("Medium", 38), fill=mix(NAVY, MUTED, ease(a)))
            pf = font("Bold", int(64 * k))
            tw = d.textlength(brand["phone"], font=pf)
            box = [80, y + 60, 80 + tw + 150, y + 60 + 120 * k]
            d.rounded_rectangle(box, 60, fill=mix(NAVY, ORANGE, ease(a)))
            phone_icon(d, 120, y + 60 + 30 * k, 60 * k, WHITE)
            d.text((80 + 120, (box[1] + box[3]) / 2), brand["phone"], font=pf, fill=WHITE, anchor="lm")

# ---------- original music ----------
MUSIC_STYLES = {
    # name: (bpm, chord progression as MIDI triads, arpeggio pattern, seed)
    "pop":    (120, [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]], [0, 1, 2, 1], 7),    # Am F C G
    "drive":  (128, [[50, 53, 57], [46, 50, 53], [48, 52, 55], [45, 49, 52]], [0, 2, 1, 2], 11),   # Dm Bb C A
    "bright": (116, [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]], [0, 1, 2, 2], 3),    # C G Am F
    "chill":  (96,  [[52, 55, 59], [48, 52, 55], [55, 59, 62], [50, 54, 57]], [0, 2, 1, 0], 21),   # Em C G D
    "hype":   (140, [[45, 48, 52], [45, 48, 52], [53, 57, 60], [52, 55, 59]], [0, 0, 2, 1], 5),    # Am Am F Em
}

def make_music(seconds, path, sr=44100, style="pop"):
    bpm, chords, arp, seed = MUSIC_STYLES.get(style, MUSIC_STYLES["pop"])
    BEAT = 60 / bpm
    n = int(seconds * sr); out = np.zeros(n); rng = np.random.default_rng(seed)
    def place(sig, start):
        i = int(start * sr)
        if i >= n: return
        j = min(n, i + len(sig)); out[i:j] += sig[: j - i]
    note = lambda m: 440 * 2 ** ((m - 69) / 12)
    bar = BEAT * 4
    # kick
    tk = np.arange(int(0.3 * sr)) / sr
    kick = np.sin(2 * np.pi * (45 * tk + 110 / 25 * (1 - np.exp(-25 * tk)))) * np.exp(-tk * 11) * 0.9
    # hat & clap
    th = np.arange(int(0.06 * sr)) / sr
    hat = np.diff(rng.standard_normal(len(th) + 1)) * np.exp(-th * 70) * 0.10
    tc = np.arange(int(0.2 * sr)) / sr
    clap = rng.standard_normal(len(tc)) * np.exp(-tc * 22) * 0.22
    t = 0.0; b = 0
    while t < seconds:
        ch = chords[(b // 4) % 4]
        if t >= bar:  # drums enter after the first bar
            place(kick, t)
            place(hat, t + BEAT / 2)
            if b % 2 == 1: place(clap, t)
        # bass on eighths
        f0 = note(ch[0] - 24)
        tb = np.arange(int(BEAT / 2 * sr)) / sr
        bass = sum(np.sin(2 * np.pi * f0 * h * tb) / h for h in (1, 2, 3)) * np.exp(-tb * 6) * 0.22
        place(bass, t); place(bass, t + BEAT / 2)
        # plucked arpeggio on sixteenths
        for k in range(4):
            m = ch[arp[k]] + 12
            tp = np.arange(int(0.22 * sr)) / sr
            pl = (np.sin(2 * np.pi * note(m) * tp) + 0.3 * np.sin(4 * np.pi * note(m) * tp)) * np.exp(-tp * 18) * 0.11
            place(pl, t + k * BEAT / 4)
        t += BEAT; b += 1
    # pad, ducked on the beat
    tt = np.arange(n) / sr
    pad = np.zeros(n)
    for i, ch in enumerate(chords * int(seconds / bar / 4 + 2)):
        s0 = int(i * bar * sr); s1 = min(n, int((i + 1) * bar * sr))
        if s0 >= n: break
        seg = tt[s0:s1]
        pad[s0:s1] = sum(np.sin(2 * np.pi * note(m) * seg) + np.sin(2 * np.pi * note(m) * 1.004 * seg) for m in ch) * 0.025
    duck = 1 - 0.6 * np.exp(-((tt % BEAT) / BEAT) * 6) * (tt >= bar)
    out += pad * duck
    fade = np.ones(n); fi = int(0.3 * sr); fo = int(1.5 * sr)
    fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo)
    out = np.tanh(out * 1.4) * fade
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.85
    data = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(data.tobytes())

# ---------- main ----------
def intro_overlay(brand, path, hook=None, accent=()):
    """Transparent overlay for the opening clip: optional big hook text at the top (shown from the
    very first frame, to stop the scroll), plus a lower-third with series badge + name + title."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    if hook:
        for y in range(0, 760):
            a = int(200 * max(0.0, 1 - y / 760))
            d.line([(0, y), (W, y)], fill=NAVY + (a,))
        hf = font("Bold", 88); acc = {a.lower() for a in accent}
        y = 300; maxw = W - 160
        for line in hook.split("\n"):
            x = 80
            for w in line.split():
                ww = d.textlength(w, font=hf)
                if x > 80 and x + ww > 80 + maxw:
                    x = 80; y += 108
                col = ORANGE2 if w.lower().strip(".,:!?") in acc else WHITE
                d.text((x + 4, y + 4), w, font=hf, fill=(0, 0, 0, 150))
                d.text((x, y), w, font=hf, fill=col + (255,))
                x += ww + d.textlength(" ", font=hf)
            y += 108
    for y in range(H - 620, H):
        a = int(220 * min(1.0, (y - (H - 620)) / 400))
        d.line([(0, y), (W, y)], fill=NAVY + (a,))
    f = font("SemiBold", 40); label = brand.get("series", "")
    if label:
        tw = d.textlength(label, font=f)
        d.rounded_rectangle([80, H - 470, 80 + tw + 60, H - 396], 37, fill=ORANGE + (255,))
        d.text((110, H - 462), label, font=f, fill=WHITE)
    d.text((80, H - 370), brand["name"], font=font("Bold", 84), fill=WHITE)
    d.text((80, H - 262), brand["title"], font=font("Regular", 40), fill=MUTED)
    if LOGO:
        x0 = W - 80 - LOGO.width
        d.rounded_rectangle([x0 - 10, 123, x0 + LOGO.width + 10, 133 + LOGO.height + 10], 14, fill=WHITE + (255,))
        img.paste(LOGO, (x0, 133), LOGO)
    img.save(path)

def main(src, out, music=True):
    spec = json.load(open(src, encoding="utf-8"))
    brand, scenes = spec["brand"], spec["scenes"]
    frames = [(si, s, f / FPS, s["seconds"]) for si, s in enumerate(scenes) for f in range(int(s["seconds"] * FPS))]
    total = len(frames)
    tmpdir = tempfile.mkdtemp()
    silent = os.path.join(tmpdir, "video.mp4")
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "19", "-r", str(FPS)]
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"] + enc + [silent], stdin=subprocess.PIPE)
    for i, (si, s, t, dur) in enumerate(frames):
        gt = i / FPS
        img = background(gt); d = ImageDraw.Draw(img)
        if s["type"] == "hook": draw_hook(d, s, t, gt)
        elif s["type"] == "steps": draw_steps(d, s, t, dur, gt)
        elif s["type"] == "cta": draw_cta(d, s, t, gt, brand)
        header(d, brand, gt); footer(d, brand); progress(d, i, total)
        if LOGO:
            x0 = W - 80 - LOGO.width
            d.rounded_rectangle([x0 - 10, 123, x0 + LOGO.width + 10, 133 + LOGO.height + 10], 14, fill=WHITE)
            img.paste(LOGO, (x0, 133), LOGO)
        if si > 0: wipe(d, t)
        p.stdin.write(img.tobytes())
    p.stdin.close(); p.wait()
    length = total / FPS
    clip = spec.get("intro_clip")
    if clip and os.path.exists(clip["path"]):
        ov = os.path.join(tmpdir, "overlay.png"); intro_overlay(brand, ov, clip.get("hook"), clip.get("accent", []))
        cs, cd = float(clip.get("start", 0)), float(clip.get("seconds", 3))
        intro = os.path.join(tmpdir, "intro.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(cs), "-t", str(cd), "-i", clip["path"], "-i", ov,
            "-filter_complex", f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1[v];"
            f"[v][1:v]overlay=0:0,fade=t=out:st={cd - 0.25}:d=0.25[o]", "-map", "[o]", "-an"] + enc + [intro], check=True)
        both = os.path.join(tmpdir, "both.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro, "-i", silent, "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[o]", "-map", "[o]"] + enc + [both], check=True)
        silent = both; length += cd
    if music:
        wav = os.path.join(tmpdir, "music.wav")
        make_music(length, wav, style=spec.get("music", "pop"))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-c", "copy", "-movflags", "+faststart", out], check=True)
    print(f"Rendered {out}: {length:.1f}s, music={'on' if music else 'off'}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], music="--no-music" not in sys.argv)
