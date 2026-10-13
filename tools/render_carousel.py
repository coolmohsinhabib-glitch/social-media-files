#!/usr/bin/env python3
"""Render branded carousel slides (1080x1350, Instagram/Facebook/LinkedIn) from JSON.

Usage: python3 render_carousel.py slides.json out_dir/

JSON:
{
  "brand": {"name": "Mohsin Habib", "title": "CFO & Co-Founder, IDB Pakistan",
            "phone": "+92 319 3498717", "series": "INTRO"},
  "photo": "optional/path/to/portrait.png",   # shown on slide 1 if present
  "slides": [
    {"kicker": "Hello", "text": "Hi, I'm Mohsin Habib", "accent": ["Mohsin", "Habib"]},
    ...
  ]
}
The last slide is drawn as a call-to-action with the phone number.
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
NAVY = (14, 24, 62); NAVY2 = (27, 44, 102); ORANGE = (224, 94, 62); ORANGE2 = (255, 142, 96)
WHITE = (255, 255, 255); MUTED = (170, 184, 224); EDGE = (62, 84, 160)
FD = "/usr/share/fonts/truetype/google-fonts/"

def font(w, s):
    for n in (f"Poppins-{w}.ttf", "Poppins-Bold.ttf"):
        try: return ImageFont.truetype(FD + n, int(s))
        except OSError: pass
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(s))

_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "idb-icon.png")
LOGO = None
if os.path.exists(_LOGO_PATH):
    _l = Image.open(_LOGO_PATH).convert("RGBA"); LOGO = _l.resize((int(_l.width * 84 / _l.height), 84))

def mix(a, b, k): return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))

def base(i):
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H): d.line([(0, y), (W, y)], fill=mix(NAVY, NAVY2, y / H))
    for y in range(40, H, 60):
        for x in range(30, W, 60):
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=mix(NAVY2, MUTED, 0.18))
    glow = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([200, 200, 700, 700], fill=ORANGE + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    pos = [(560, -300), (-380, 600), (520, 700)][i % 3]
    img.paste(glow, pos, glow)
    return img

def words_layout(d, text, f, maxw, x0, y0, lh):
    out = []; y = y0
    for para in text.split("\n"):
        line = []; lw = 0
        for w in para.split():
            ww = d.textlength(w, font=f); sp = d.textlength(" ", font=f) if line else 0
            if line and lw + sp + ww > maxw:
                out += [(t, x0 + o, y) for t, o in line]; y += lh; line = []; lw = 0; sp = 0
            line.append((w, lw + sp)); lw += sp + ww
        out += [(t, x0 + o, y) for t, o in line]; y += lh
    return out, y

def chrome(d, brand, i, n):
    f = font("SemiBold", 32); label = brand.get("series", "")
    if label:
        tw = d.textlength(label, font=f)
        d.rounded_rectangle([80, 90, 80 + tw + 52, 150], 30, fill=ORANGE)
        d.text((106, 97), label, font=f, fill=WHITE)
    lw = LOGO.width + 34 if LOGO else 0
    if n > 1: d.text((W - 80 - lw, 104), f"{i + 1}/{n}", font=font("SemiBold", 30), fill=MUTED, anchor="ra")
    d.line([80, H - 190, W - 80, H - 190], fill=EDGE, width=2)
    d.text((80, H - 160), brand["name"], font=font("Bold", 40), fill=WHITE)
    d.text((80, H - 108), brand["title"], font=font("Regular", 28), fill=MUTED)
    if i < n - 1:
        sf = font("SemiBold", 32); tw = d.textlength("Swipe", font=sf)
        d.text((W - 120 - tw, H - 152), "Swipe", font=sf, fill=ORANGE2)
        d.polygon([(W - 108, H - 146), (W - 80, H - 132), (W - 108, H - 118)], fill=ORANGE2)

def circle_photo(path, size):
    im = Image.open(path).convert("RGB")
    s = min(im.size); im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    im = im.resize((size, size))
    m = Image.new("L", (size, size), 0); ImageDraw.Draw(m).ellipse([0, 0, size, size], fill=255)
    return im, m

def photo_bg(path, focus=0.3, fade_start=0.38):
    """Full-bleed photo, cover-cropped (focus = vertical crop anchor 0..1), navy fade at the bottom."""
    im = Image.open(path).convert("RGB")
    k = max(W / im.width, H / im.height); im = im.resize((int(im.width * k + 1), int(im.height * k + 1)))
    x = (im.width - W) // 2; y = int((im.height - H) * focus)
    im = im.crop((x, y, x + W, y + H))
    fade = Image.new("L", (1, H))
    for yy in range(H):
        t = max(0.0, (yy - H * fade_start) / (H * 0.40)); fade.putpixel((0, yy), int(255 * min(1.0, t) ** 1.2 * 0.94))
    top = Image.new("L", (1, H))
    for yy in range(H):
        top.putpixel((0, yy), int(190 * max(0.0, 1 - yy / 280)))
    navy = Image.new("RGB", (W, H), NAVY)
    im = Image.composite(navy, im, fade.resize((W, H)))
    im = Image.composite(navy, im, top.resize((W, H)))
    return im

def render(spec, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    brand, slides = spec["brand"], spec["slides"]; n = len(slides); paths = []
    for i, s in enumerate(slides):
        bgp = s.get("bg_photo")
        img = photo_bg(bgp, s.get("focus", 0.3), s.get("fade_start", 0.38)) if bgp and os.path.exists(bgp) else base(i)
        d = ImageDraw.Draw(img); chrome(d, brand, i, n)
        if LOGO:
            pad = 10; x0 = W - 80 - LOGO.width
            d.rounded_rectangle([x0 - pad, 78 - pad, x0 + LOGO.width + pad, 78 + LOGO.height + pad], 14, fill=WHITE)
            img.paste(LOGO, (x0, 78), LOGO)
        y0 = s.get("text_y", 470)
        if i == 0 and spec.get("photo") and os.path.exists(spec["photo"]):
            ph, m = circle_photo(spec["photo"], 300)
            d.ellipse([74, 214, 386, 526], fill=ORANGE); img.paste(ph, (80, 220), m); y0 = 600
        if s.get("kicker"):
            d.text((80, y0 - 70), s["kicker"].upper(), font=font("SemiBold", 34), fill=ORANGE2)
        last = i == n - 1
        f = font("Bold", 96 if not last else 88)
        ws, yend = words_layout(d, s["text"], f, W - 160, 80, y0, 118)
        acc = {a.lower() for a in s.get("accent", [])}
        for w, x, y in ws:
            d.text((x, y), w, font=f, fill=ORANGE2 if w.lower().strip(".,:!?") in acc else WHITE)
        if s.get("sub"):
            sf = font("Regular", 42)
            sw, yend = words_layout(d, s["sub"], sf, W - 160, 80, yend + 24, 60)
            for w, x, y in sw: d.text((x, y), w, font=sf, fill=MUTED)
        if s.get("logo_card"):
            lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "idb-logo-horizontal.jpg")
            if os.path.exists(lp):
                lg = Image.open(lp).convert("RGB"); lw = 560; lg = lg.resize((lw, int(lg.height * lw / lg.width)))
                y = yend + 50; pad = 20
                d.rounded_rectangle([80, y, 80 + lw + 2 * pad, y + lg.height + 2 * pad], 28, fill=WHITE)
                img.paste(lg, (80 + pad, y + pad))
        if last and brand.get("phone"):
            pf = font("Bold", 56); tw = d.textlength(brand["phone"], font=pf); y = yend + 50
            d.rounded_rectangle([80, y, 80 + tw + 90, y + 100], 50, fill=ORANGE)
            d.text((125, y + 50), brand["phone"], font=pf, fill=WHITE, anchor="lm")
        p = os.path.join(out_dir, f"slide-{i + 1:02d}.jpg"); img.save(p, quality=92); paths.append(p)
    return paths

if __name__ == "__main__":
    print("\n".join(render(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2])))
