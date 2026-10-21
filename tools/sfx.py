#!/usr/bin/env python3
"""Original, royalty-free sound effects for Mohsin's videos – synthesised here, no downloads.

Every effect is made from sine waves and filtered noise with numpy only, so there is no
licence or copyright risk. The effects are timed to the renderer's animations (render_video.py
calls `cues_from_spec`) or to a cue list for videos that are already rendered.

Effects (name: where it is used – playbook SFX map):
  impact   hook slam on the first frame
  whoosh   scene transitions (the orange wipe) – peak lands on the cut
  swish    a card / line sliding in
  pop      a word or title appearing
  coin     a money / fee / cost / profit figure appearing
  ding     the highlighted tip or key line settling
  riser    the build-up 1.2 s before the payoff / call-to-action scene
  notify   the contact / phone box appearing
  error    a mistake ("galat", ❌)
  chime    the correct way (✅)
  tick     counters, typing, small UI moments

Usage on an existing video (keeps its music, adds the effects, masters to -14 LUFS / -1 dBTP):
  python3 sfx.py add  in.mp4 cues.json out.mp4        cues.json = [{"t": 3.4, "fx": "whoosh"}, ...]
  python3 sfx.py demo out_dir                          writes one WAV per effect to listen to
"""
import json, math, os, subprocess, sys, tempfile, wave
import numpy as np

SR = 44100
RNG = np.random.default_rng(7)

# ---------- building blocks ----------
def _t(d): return np.arange(int(d * SR)) / SR

def _env(n, a, r, curve=4.0):
    """attack/release envelope in seconds, exponential release."""
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(a, 1e-4))
    rel = np.exp(-curve * np.maximum(0, t - a) / max(r, 1e-4))
    return e * rel

def _sweep_noise(d, f0, f1, width=0.6, shape=None):
    """Noise through a moving band-pass (STFT, numpy only). f0→f1 Hz over d seconds."""
    n = int(d * SR); hop, win = 256, 1024
    x = RNG.standard_normal(n + win)
    w = np.hanning(win)
    out = np.zeros(n + win)
    freqs = np.fft.rfftfreq(win, 1 / SR)
    frames = range(0, n, hop)
    for k, i in enumerate(frames):
        p = i / max(1, n - 1)
        if shape is not None: p = shape(p)
        fc = f0 * (f1 / f0) ** p
        band = np.exp(-0.5 * (np.log2(np.maximum(freqs, 1) / fc) / width) ** 2)
        seg = np.fft.irfft(np.fft.rfft(x[i:i + win] * w) * band)
        out[i:i + win] += seg * w
    y = out[:n]
    return y / (np.max(np.abs(y)) + 1e-9)

def _partials(d, f, parts, decay):
    t = _t(d); y = np.zeros_like(t)
    for mult, amp, dk in parts:
        y += amp * np.sin(2 * np.pi * f * mult * t) * np.exp(-t * decay * dk)
    return y

def _norm(y, db):
    return y / (np.max(np.abs(y)) + 1e-9) * 10 ** (db / 20)

# ---------- the effects ----------
def impact():
    d = 0.9; t = _t(d)
    f = 45 + 95 * np.exp(-t * 18)                      # pitch drop 140→45 Hz
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5)
    click = _sweep_noise(0.05, 3000, 900) * np.exp(-_t(0.05) * 60)
    y = body; y[:len(click)] += 0.35 * click
    return _norm(np.tanh(1.6 * y), -8)

def whoosh(d=0.5):
    # rises to its peak at 70 % (that point is placed on the cut), then falls away
    y = _sweep_noise(d, 350, 5200, width=0.5, shape=lambda p: math.sin(p * math.pi / 2) ** 1.4)
    t = np.linspace(0, 1, len(y))
    env = np.where(t < 0.7, (t / 0.7) ** 2.2, np.exp(-(t - 0.7) * 11))
    return _norm(y * env, -15)

def swish():
    y = _sweep_noise(0.26, 900, 4200, width=0.45)
    t = np.linspace(0, 1, len(y))
    return _norm(y * np.sin(np.pi * t) ** 1.5, -19)

def pop():
    d = 0.11; t = _t(d)
    f = 520 + 600 * np.exp(-t * 55)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.002, 0.05, 5)
    return _norm(y, -17)

def coin():
    a = _partials(0.18, 1975.5, [(1, 1, 1), (2.76, .35, 1.6), (5.4, .15, 2.4)], 16)   # B6
    b = _partials(0.55, 2637.0, [(1, 1, 1), (2.76, .3, 1.5), (5.4, .12, 2.2)], 7)     # E7
    y = np.zeros(int(0.62 * SR)); y[:len(a)] += a; s = int(0.07 * SR); y[s:s + len(b)] += b
    shimmer = _sweep_noise(len(y) / SR, 6000, 9000, width=0.3) * np.exp(-np.arange(len(y)) / SR * 9)
    return _norm(y + 0.12 * shimmer, -18)

def ding():
    y = _partials(1.1, 1318.5, [(1, 1, 1), (2.0, .5, 1.4), (3.01, .25, 2), (4.2, .12, 2.8)], 3.2)  # E6 bell
    y *= _env(len(y), 0.003, 1.1, 1.0)
    return _norm(y, -19)

def riser(d=1.2):
    t = _t(d)
    n = _sweep_noise(d, 250, 6000, width=0.7)
    f = 180 * (4.0 ** (t / d))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    env = (t / d) ** 2.4
    return _norm((0.75 * n + 0.25 * tone) * env, -17)

def notify():
    a = _partials(0.16, 1318.5, [(1, 1, 1), (3.0, .2, 2)], 14)    # E6
    b = _partials(0.35, 1975.5, [(1, 1, 1), (3.0, .2, 2)], 9)     # B6
    y = np.zeros(int(0.5 * SR)); y[:len(a)] += a; s = int(0.11 * SR); y[s:s + len(b)] += b
    return _norm(y, -19)

def error():
    t = _t(0.13)
    sq = np.sign(np.sin(2 * np.pi * 196 * t)) * _env(len(t), 0.004, 0.12, 2)
    y = np.zeros(int(0.32 * SR)); y[:len(t)] += sq; s = int(0.17 * SR); y[s:s + len(t)] += sq
    return _norm(np.tanh(y), -22)

def chime():
    y = np.zeros(int(0.8 * SR))
    for i, f in enumerate((1046.5, 1318.5, 1568.0)):              # C6 E6 G6
        p = _partials(0.6, f, [(1, 1, 1), (2.0, .3, 1.5)], 6)
        s = int(i * 0.07 * SR); y[s:s + len(p)] += p
    return _norm(y, -19)

def tick():
    y = _sweep_noise(0.02, 4000, 2500, width=0.4) * np.exp(-_t(0.02) * 220)
    return _norm(y, -24)

FX = {"impact": impact, "whoosh": whoosh, "swish": swish, "pop": pop, "coin": coin, "ding": ding,
      "riser": riser, "notify": notify, "error": error, "chime": chime, "tick": tick}
# where in each sound the "hit" is (seconds) – that point is placed exactly on the cue time
HIT = {"whoosh": 0.35, "riser": 1.2, "swish": 0.12}
_cache = {}

def get(fx):
    if fx not in _cache: _cache[fx] = FX[fx]()
    return _cache[fx]

def render_track(cues, length):
    """Mix a list of {"t": seconds, "fx": name, "gain_db": optional} into one mono track."""
    y = np.zeros(int(length * SR) + SR)
    for c in cues:
        s = get(c["fx"]) * 10 ** (c.get("gain_db", 0) / 20)
        start = int((c["t"] - HIT.get(c["fx"], 0)) * SR)
        if start < 0: s, start = s[-start:], 0
        end = min(len(y), start + len(s)); y[start:end] += s[:end - start]
    return y[:int(length * SR)]

def write_wav(path, y, channels=2):
    y = np.clip(y, -1, 1)
    data = (np.repeat(y[:, None], channels, axis=1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data)

# ---------- timing: the same clock as render_video.py ----------
MONEY = ("$", "rs", "pkr", "fee", "fees", "cost", "profit", "payout", "price", "kamai", "paisa", "budget", "investment")

def cues_from_spec(spec, intro_seconds=0.0):
    """Cue list that follows render_video.py's animation timings exactly.
    Scene-level override: "sfx": false (silence a scene) or "sfx": [{"at": 1.2, "fx": "error"}] (extra cues, seconds into the scene)."""
    cues = [{"t": 0.0, "fx": "impact"}]
    t0 = intro_seconds
    scenes = spec["scenes"]
    for si, s in enumerate(scenes):
        dur = s["seconds"]
        if si > 0 or intro_seconds:
            cues.append({"t": t0 + 0.0, "fx": "whoosh"})            # orange wipe / intro fade
        if s.get("sfx") is False:
            t0 += dur; continue
        if s["type"] == "hook":
            words = s["text"].split()
            for i in range(len(words)):
                if i % 2 == 0: cues.append({"t": t0 + 0.15 + i * 0.12, "fx": "pop", "gain_db": -3})
            cues.append({"t": t0 + 0.25 + len(words) * 0.12, "fx": "swish"})
        elif s["type"] == "steps":
            cues.append({"t": t0 + 0.25, "fx": "pop"})                 # title
            n = len(s["lines"]); step = (dur * 0.62) / n
            coined = False
            for i, (label, value) in enumerate(s["lines"]):
                ti = t0 + 0.45 + i * step
                has_number = any(ch.isdigit() for ch in value) or any(m in value.lower() for m in ("$", "rs", "pkr"))
                money_word = any(m in f"{label} {value}".lower() for m in MONEY)
                cues.append({"t": ti, "fx": "swish"})
                # one coin per scene on the first money/number line, pops on the rest, ding on the highlight (no repetition)
                if (has_number or money_word) and not coined and s.get("highlight") != i + 1:
                    cues.append({"t": ti + 0.3, "fx": "coin", "gain_db": -2}); coined = True
                else: cues.append({"t": ti + 0.3, "fx": "pop"})
                if s.get("highlight") == i + 1: cues.append({"t": ti + 0.5, "fx": "ding"})
        elif s["type"] == "cta":
            words = s["text"].split()
            for i in range(0, len(words), 2): cues.append({"t": t0 + 0.2 + i * 0.08, "fx": "pop", "gain_db": -4})
            cues.append({"t": t0 + 0.45 + len(words) * 0.08, "fx": "notify"})
        for extra in s.get("sfx", []) if isinstance(s.get("sfx"), list) else []:
            cues.append({"t": t0 + float(extra["at"]), "fx": extra["fx"], "gain_db": extra.get("gain_db", 0)})
        if si + 1 == len(scenes) - 1:                                   # build-up into the last scene (payoff/CTA)
            cues.append({"t": t0 + dur, "fx": "riser"})
        t0 += dur
    return sorted(cues, key=lambda c: c["t"])

# ---------- balance against the music ----------
# target level of each effect relative to the music's loudness at that moment (dB, RMS)
TARGET = {"impact": -8, "whoosh": -5, "swish": -8, "pop": -7, "coin": -4, "ding": -4, "riser": -6,
          "notify": -4, "error": -5, "chime": -4, "tick": -10}

def _rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)

def balance(cues, music_mono):
    """Set each cue's gain so the effect sits TARGET dB under (or over) the local music level."""
    out = []
    for c in cues:
        fx = get(c["fx"]); i = int(c["t"] * SR); hit = int(HIT.get(c["fx"], 0) * SR)
        a = max(0, i - hit); b = min(len(music_mono), a + len(fx))
        m = music_mono[a:b] if b > a else np.zeros(1)
        music_db = max(_rms_db(m), -40.0)                       # silent passage: treat as -40 dB
        fx_db = _rms_db(fx[: max(1, b - a)])
        g = music_db + TARGET.get(c["fx"], -6) - fx_db + c.get("gain_db", 0)
        out.append({**c, "gain_db": float(np.clip(g, -12, 24))})
    return out

def duck_envelope(cues, n, depth_db=-3.0):
    """Music gain curve: dips depth_db under every effect (10 ms attack, 120 ms release)."""
    g = np.zeros(n)
    for c in cues:
        fx = get(c["fx"]); a = max(0, int((c["t"] - HIT.get(c["fx"], 0)) * SR)); b = min(n, a + len(fx))
        g[a:b] = np.maximum(g[a:b], np.abs(fx[: b - a]) / (np.max(np.abs(fx)) + 1e-9) > 0.05)
    k = int(0.12 * SR); kern = np.exp(-np.arange(k) / (k / 4)); kern /= kern.sum()
    g = np.convolve(g, kern)[:n]
    return 10 ** ((depth_db * np.clip(g * 3, 0, 1)) / 20)

def mix_with_music(music, cues):
    """music: (n, 2) float array. Returns (n, 2) with ducking + balanced effects."""
    mono = music.mean(axis=1)
    cues = balance(cues, mono)
    fx = render_track(cues, len(mono) / SR)
    fx = np.pad(fx, (0, max(0, len(mono) - len(fx))))[: len(mono)]
    duck = duck_envelope(cues, len(mono))
    return music * duck[:, None] + fx[:, None], cues

def _read_audio(src):
    b = subprocess.check_output(["ffmpeg", "-v", "error", "-i", src, "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"])
    return (np.frombuffer(b, "<i2").astype(np.float64) / 32768).reshape(-1, 2)

def _write_stereo(path, y):
    y = np.clip(y, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((y * 32767).astype("<i2").tobytes())

def add_to_video(src, cues, out):
    """Add balanced, ducked effects to a rendered video and master to -14 LUFS / -1 dBTP."""
    tmp = tempfile.mkdtemp()
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).decode())
    try: music = _read_audio(src)
    except subprocess.CalledProcessError: music = np.zeros((int(dur * SR), 2))
    if len(music) == 0: music = np.zeros((int(dur * SR), 2))
    mixed, used = mix_with_music(music, cues)
    wav = os.path.join(tmp, "mix.wav"); _write_stereo(wav, mixed * 0.5)   # headroom, loudnorm restores level
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1:LRA=9,alimiter=limit=0.89:level=false", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-shortest", "-movflags", "+faststart", out], check=True)
    return used

if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "add":
        add_to_video(sys.argv[2], json.load(open(sys.argv[3])), sys.argv[4]); print("wrote", sys.argv[4])
    elif len(sys.argv) >= 3 and sys.argv[1] == "demo":
        os.makedirs(sys.argv[2], exist_ok=True)
        for k in FX: write_wav(os.path.join(sys.argv[2], f"{k}.wav"), np.concatenate([get(k), np.zeros(SR // 3)]))
        print("wrote", len(FX), "effects to", sys.argv[2])
    else:
        print(__doc__)
