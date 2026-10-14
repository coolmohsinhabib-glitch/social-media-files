"""Original, royalty-free music for the short videos (v2 engine).

make_music(seconds, path, style="pop", cuts=(), seed=None) writes a 44.1 kHz stereo WAV.

What it does, compared with the first engine:
- 6 styles with their own instruments, groove and harmony:
  pop (guitar-like pluck + supersaw), drive (stabs + bell, offbeat bass),
  bright (electric piano, major key), chill (lo-fi, swing, crackle),
  hype (trap: 808 bass, hat rolls, bell lead), desi (dholak + harmonium + sitar-like pluck).
- Arranged to the video: an impact hit on frame 1, a riser + snare fill + a short gap
  before every scene cut, a crash on the cut, the lead melody enters after the hook,
  extra energy on the last scene, and a final chord with a reverb tail.
- A generated melody (chord-aware, A / A' phrases); pass a different seed per video
  so two videos in the same style still sound different.
- Stereo mix with sidechain ducking, reverb and ping-pong delay sends.
"""
import wave
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
DORIAN = [0, 2, 3, 5, 7, 9, 10]
HIJAZ = [0, 1, 4, 5, 7, 8, 10]
QUAL = {"M": [0, 4, 7], "m": [0, 3, 7], "M7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "7": [0, 4, 7, 10]}

STYLES = {
    "pop":    dict(bpm=118, key=57, scale=MINOR,  prog=[(0, "m"), (-4, "M"), (3, "M"), (-2, "M")],
                   drums="four", bass="pluck", chords="supersaw", lead="ks", swing=0.0),
    "drive":  dict(bpm=126, key=50, scale=MINOR,  prog=[(0, "m"), (-4, "M"), (-2, "M"), (-5, "M")],
                   drums="four", bass="offbeat", chords="stab", lead="bell", swing=0.0),
    "bright": dict(bpm=112, key=48, scale=MAJOR,  prog=[(0, "M"), (7, "M"), (9, "m"), (5, "M")],
                   drums="pop", bass="pluck", chords="epiano", lead="ks", swing=0.06, levels=dict(harm=-17.5)),
    "chill":  dict(bpm=88,  key=52, scale=DORIAN, prog=[(0, "m7"), (-4, "M7"), (3, "M"), (-2, "M")],
                   drums="lofi", bass="sub", chords="epiano", lead="bell", swing=0.2, levels=dict(drums=-15, bass=-17, harm=-18)),
    "hype":   dict(bpm=140, key=45, scale=MINOR,  prog=[(0, "m"), (0, "m"), (-4, "M"), (-5, "m")],
                   drums="trap", bass="808", chords="supersaw", lead="bell", swing=0.0, levels=dict(drums=-13, bass=-13.5)),
    "desi":   dict(bpm=104, key=50, scale=HIJAZ,  prog=[(0, "M"), (1, "M"), (-2, "m"), (0, "M")],
                   drums="dholak", bass="sub", chords="harmonium", lead="sitar", swing=0.08, levels=dict(harm=-17.5, lead=-15)),
}

# ---------------------------------------------------------------- helpers
def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
def tvec(sec): return np.arange(int(sec * SR)) / SR
def _sos(kind, fc, order=2):
    if kind == "band":
        lo, hi = fc; return butter(order, [max(lo, 20), min(hi, SR * 0.45)], "band", fs=SR, output="sos")
    return butter(order, min(max(fc, 20), SR * 0.45), kind, fs=SR, output="sos")
def lp(x, fc, o=2): return sosfilt(_sos("low", fc, o), x, axis=-1)
def hp(x, fc, o=2): return sosfilt(_sos("high", fc, o), x, axis=-1)
def bp(x, lo, hi, o=2): return sosfilt(_sos("band", (lo, hi), o), x, axis=-1)
def env(n, a=0.002, decay=6.0, release=0.0):
    t = np.arange(n) / SR; e = np.exp(-t * decay)
    na = max(1, int(a * SR)); e[:na] *= np.linspace(0, 1, min(na, n))
    nr = int(release * SR)
    if 0 < nr < n: e[-nr:] *= np.linspace(1, 0, nr)
    return e
def saw(f, t, phase=0.0): return 2 * ((f * t + phase) % 1.0) - 1

class Bus:
    def __init__(self, n): self.x = np.zeros((2, n)); self.n = n
    def add(self, sig, start, pan=0.0, gain=1.0):
        sig = np.asarray(sig)
        i = int(round(start * SR))
        if i >= self.n or i < -len(sig.T): return
        if sig.ndim == 1:
            a = (pan + 1) * np.pi / 4; sig = np.vstack([sig * np.cos(a), sig * np.sin(a)]) * 1.414
        s0 = max(0, -i); i = max(i, 0); j = min(self.n, i + sig.shape[1] - s0)
        self.x[:, i:j] += sig[:, s0:s0 + j - i] * gain

# ---------------------------------------------------------------- instruments
class Kit:
    def __init__(self, rng):
        self.rng = rng
        t = tvec(0.45); f = 46 + 150 * np.exp(-t * 32)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5)
        click = hp(rng.standard_normal(len(t)), 2500) * np.exp(-t * 350) * 0.35
        self.kick = np.tanh(1.8 * (body + click)) * 0.95
        t = tvec(0.3); nz = rng.standard_normal(len(t))
        self.snare = (np.sin(2 * np.pi * 185 * t) * np.exp(-t * 28) * 0.55 + np.sin(2 * np.pi * 330 * t) * np.exp(-t * 35) * 0.2
                      + bp(nz, 1500, 9000) * np.exp(-t * 15) * 0.75)
        t = tvec(0.35); c = np.zeros(len(t))
        for k, dl in enumerate((0, 0.011, 0.022)):
            i = int(dl * SR); c[i:] += np.exp(-np.arange(len(t) - i) / SR * (60 if k < 2 else 13))
        self.clap = bp(rng.standard_normal(len(t)), 900, 3500) * c * 0.8
        t = tvec(0.07); self.hat = hp(rng.standard_normal(len(t)), 7500) * np.exp(-t * 85) * 0.55
        t = tvec(0.35); self.ohat = hp(rng.standard_normal(len(t)), 6500) * np.exp(-t * 11) * 0.38
        t = tvec(0.06); self.shaker = bp(rng.standard_normal(len(t)), 4000, 11000) * np.sin(np.pi * np.arange(len(t)) / len(t)) * 0.45
        t = tvec(2.2)
        self.crash = np.vstack([hp(rng.standard_normal(len(t)), 3500) * np.exp(-t * 2.1),
                                hp(rng.standard_normal(len(t)), 3500) * np.exp(-t * 2.1)]) * 0.33
        # dholak: low "ge", high "na", slap "ti/ka"
        t = tvec(0.5); f = 72 + 70 * np.exp(-t * 14)
        self.ge = (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)
                   + bp(rng.standard_normal(len(t)), 100, 600) * np.exp(-t * 60) * 0.4) * 0.95
        t = tvec(0.3)
        self.na = (np.sin(2 * np.pi * 410 * t) * 0.6 + np.sin(2 * np.pi * 410 * 2.3 * t) * 0.25 + np.sin(2 * np.pi * 410 * 3.6 * t) * 0.12) * np.exp(-t * 16)
        self.na += bp(rng.standard_normal(len(t)), 1500, 6000) * np.exp(-t * 120) * 0.35
        t = tvec(0.12); self.ti = bp(rng.standard_normal(len(t)), 700, 4000) * np.exp(-t * 55) * 0.6

    def impact(self):
        t = tvec(1.8); f = 30 + 45 * np.exp(-t * 6)
        boom = np.tanh(2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)) * 0.9
        thud = lp(self.rng.standard_normal(len(t)), 900) * np.exp(-t * 12) * 0.6
        m = boom + thud
        out = np.vstack([m, m]); out[:, :self.crash.shape[1]] += self.crash[:, :len(t)] * 1.2
        return out

    def riser(self, sec):
        n = int(sec * SR); nz = self.rng.standard_normal(n); out = np.zeros(n); blk = 1024
        for b in range(0, n, blk):
            k = b / n; c = 400 * (14000 / 400) ** k
            out[b:b + blk] = bp(nz[b:b + blk], c * 0.6, min(c * 1.6, 20000))
        t = np.arange(n) / SR; amp = (t / sec) ** 2.2
        sweep = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (2 * t / sec)) / SR) * 0.15
        return (out * 0.5 + sweep) * amp

def ks(m, sec, rng, bright=0.6, decay=0.996, buzz=0.0):
    """Karplus-Strong plucked string (guitar / sitar-like)."""
    n = int(sec * SR); N = max(2, int(SR / hz(m))); out = np.zeros(n + N + 1)
    burst = rng.uniform(-1, 1, N)
    burst = lp(burst, 1500 + 9000 * bright)
    out[:N] = burst
    for s in range(N, n + N, N):
        prev = out[s - N:s]; prev2 = out[s - N - 1:s - 1] if s - N - 1 >= 0 else np.concatenate([[0], prev[:-1]])
        out[s:s + N] = (0.5 * (prev + prev2) * decay)[: len(out[s:s + N])]
    y = out[:n]
    if buzz:  # sitar "jawari" buzz: bright harmonics from a soft bridge clip
        y = y + buzz * hp(np.tanh(4 * y), 1800)
    return y * env(n, 0.001, 0.0, 0.03)

def bell(m, sec):
    t = tvec(sec); f = hz(m)
    i = 2.2 * np.exp(-t * 6)
    return np.sin(2 * np.pi * f * t + i * np.sin(2 * np.pi * f * 3.5 * t)) * np.exp(-t * 3.2) * env(len(t), 0.002, 0, 0.02)

def epiano(m, sec):
    t = tvec(sec); f = hz(m); i = 1.4 * np.exp(-t * 3)
    s = np.sin(2 * np.pi * f * t + i * np.sin(2 * np.pi * f * t)) * np.exp(-t * 1.6)
    s += 0.15 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 9)
    return s * (1 + 0.12 * np.sin(2 * np.pi * 4.5 * t)) * env(len(t), 0.003, 0, 0.06)

def supersaw(notes, sec, rng, short=False):
    t = tvec(sec); L = np.zeros(len(t)); R = np.zeros(len(t))
    for m in notes:
        for k, c in enumerate((-14, -7, -2, 3, 8, 15)):
            s = saw(hz(m) * 2 ** (c / 1200), t, rng.random())
            if k % 2: L += s
            else: R += s
    e = env(len(t), 0.004, 9.0, 0.02) if short else env(len(t), 0.06, 0.25, 0.12)
    fc = 3200 if short else 2400
    return np.vstack([lp(L, fc), lp(R, fc)]) * e / (len(notes) * 3)

def harmonium(notes, sec):
    t = tvec(sec); s = np.zeros(len(t))
    for m in notes:
        for det in (0, 3.5):
            f = hz(m) * 2 ** (det / 1200)
            s += sum(np.sin(2 * np.pi * f * h * t) / h ** 0.75 for h in range(1, 10))
    s = lp(s, 3200) * (1 + 0.05 * np.sin(2 * np.pi * 5.5 * t))
    return s * env(len(t), 0.07, 0.05, 0.12) / (len(notes) * 9)

def bass_note(kind, m, sec, rng, glide_from=None):
    t = tvec(sec); f = hz(m)
    if kind == "808":
        fr = f * np.ones(len(t))
        if glide_from is not None:
            g = np.exp(-t * 18); fr = f + (hz(glide_from) - f) * g
        s = np.sin(2 * np.pi * np.cumsum(fr) / SR)
        return np.tanh(2.2 * s) * np.exp(-t * 1.1) * env(len(t), 0.003, 0, 0.04) * 0.75
    if kind == "sub":
        return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * env(len(t), 0.01, 1.5, 0.05) * 0.8
    s = lp(saw(f, t) + 0.6 * saw(f * 1.005, t), 320 if kind == "offbeat" else 520)
    return (s * 0.9 + np.sin(2 * np.pi * f * t) * 0.7) * env(len(t), 0.003, 5.5 if kind == "offbeat" else 3.0, 0.03) * 0.75

def reverb(x, sec=1.6, seed=1):
    r = np.random.default_rng(seed); t = tvec(sec); pre = int(0.018 * SR)
    out = []
    for ch in range(2):
        ir = r.standard_normal(len(t)) * np.exp(-t * 6.9 / sec)
        ir = np.concatenate([np.zeros(pre), lp(ir, 6500)])
        out.append(fftconvolve(x[ch], ir)[: x.shape[1]])
    out = np.array(out)
    return out / (np.max(np.abs(out)) + 1e-9) * (np.max(np.abs(x)) + 1e-9)

# ---------------------------------------------------------------- composition
def voicing(key, off, q, lo=55, hi=66):
    r = key + off
    while r < lo: r += 12
    while r > hi: r -= 12
    return [r + i for i in QUAL[q]]

def make_melody(st, rng, bars=8):
    """Chord-aware melody, A (4 bars) + A' (same opening, new ending). Returns [(beat, midi, beats)]."""
    key, scale, prog = st["key"], st["scale"], st["prog"]
    pool = [key + 12 + o + 12 * k for k in (0, 1) for o in scale]
    pool = sorted(p for p in pool if 64 <= p <= 83)
    rhythms = [[0, 3, 6, 8, 10, 12], [0, 2, 4, 7, 10, 12, 14], [0, 4, 6, 10, 12], [0, 3, 6, 9, 12, 14], [2, 4, 6, 8, 11, 14]]
    if st["drums"] == "trap": rhythms = [[0, 3, 6, 8, 11, 14], [0, 2, 3, 6, 8, 10, 12]]
    if st["drums"] == "lofi": rhythms = [[0, 6, 8, 12], [2, 6, 10, 12], [0, 4, 10]]
    def bar_notes(b, prev, rhythm):
        off, q = prog[b % len(prog)]; ct = set((key + off + i) % 12 for i in QUAL[q])
        notes = []
        for k, s in enumerate(rhythm):
            strong = s % 8 == 0 or k == 0
            if strong:
                cands = [p for p in pool if p % 12 in ct]
            else:
                idx = min(range(len(pool)), key=lambda i: abs(pool[i] - prev))
                cands = [pool[min(len(pool) - 1, max(0, idx + d))] for d in (-2, -1, 1, 2)]
            w = np.array([1 / (1 + abs(c - prev)) for c in cands]); w /= w.sum()
            prev = int(rng.choice(cands, p=w)); notes.append(prev)
        return notes, prev
    seq = []; prev = pool[len(pool) // 3]
    A = []
    rA = [rhythms[rng.integers(len(rhythms))] for _ in range(2)]
    for b in range(4):
        r = rA[b % 2]; ns, prev = bar_notes(b, prev, r); A.append((r, ns))
    B = A[:2]
    for b in (2, 3):
        r = rhythms[rng.integers(len(rhythms))]; ns, prev = bar_notes(b, prev, r); B.append((r, ns))
    phrase = A + B
    for b in range(bars):
        r, ns = phrase[b % 8]
        for k, s in enumerate(r):
            nxt = r[k + 1] if k + 1 < len(r) else 16
            seq.append((b * 4 + s / 4, ns[k], min(nxt - s, 4) / 4))
    return seq

DRUMS = {  # 16 steps per bar: (step, voice, velocity)
    "four":   [(s, "kick", 1) for s in (0, 4, 8, 12)] + [(s, "clap", 0.9) for s in (4, 12)]
              + [(s, "hat", 0.9) for s in (2, 6, 10, 14)] + [(s, "hat", 0.35) for s in (1, 3, 5, 7, 9, 11, 13, 15)] + [(14, "ohat", 0.6)],
    "pop":    [(s, "kick", 1) for s in (0, 7, 8, 10)] + [(s, "snare", 0.9) for s in (4, 12)]
              + [(s, "hat", 0.7 if s % 4 else 0.45) for s in range(0, 16, 2)],
    "lofi":   [(0, "kick", 0.9), (10, "kick", 0.75), (4, "snare", 0.6), (12, "snare", 0.65)]
              + [(s, "hat", 0.4 if s % 4 else 0.25) for s in range(0, 16, 2)],
    "trap":   [(0, "kick", 1), (11, "kick", 0.9), (8, "clap", 1), (8, "snare", 0.6)]
              + [(s, "hat", 0.55 if s % 2 else 0.8) for s in range(16)],
    "dholak": [(0, "ge", 1), (0, "na", 0.6), (2, "ge", 0.55), (4, "na", 0.9), (6, "ti", 0.7), (8, "na", 0.85),
               (10, "ti", 0.6), (12, "ge", 0.8), (12, "na", 0.7), (14, "na", 0.75), (0, "kick", 0.6), (8, "kick", 0.5)]
              + [(s, "shaker", 0.5 if s % 2 else 0.8) for s in range(16)],
}

def make_music(seconds, path, style="pop", cuts=(), seed=None):
    st = STYLES.get(style, STYLES["pop"])
    rng = np.random.default_rng(seed if seed is not None else sum(map(ord, style)))
    beat = 60 / st["bpm"]; step = beat / 4; bar = beat * 4
    n = int(seconds * SR); kit = Kit(rng)
    drums, bass, harm, lead, fx, send = (Bus(n) for _ in range(6))
    cuts = sorted(c for c in set(cuts) if 0.5 < c < seconds - 0.5)
    tail = 1.6; end_t = max(bar, seconds - tail)          # groove stops here, final chord rings out
    def section(t): return sum(1 for c in cuts if c <= t)
    nsec = len(cuts) + 1
    def gap(t):  # silence kick/bass for the half-beat before each cut
        return any(c - beat * 0.5 <= t < c for c in cuts)
    # time grid aligned to the start; cuts get their own hits on top
    kicks = []
    nbars = int(np.ceil(end_t / bar)) + 1
    pat = DRUMS[st["drums"]]
    for b in range(nbars):
        for s, v, vel in pat:
            sw = st["swing"] * step if s % 2 else 0
            t = b * bar + s * step + sw
            if t >= end_t: continue
            sec_i = section(t)
            if v in ("kick", "ge") and gap(t): continue
            if v == "hat" and vel < 0.5 and sec_i == 0 and st["drums"] == "four": continue
            vel *= 0.9 + 0.2 * rng.random()
            snd = {"kick": kit.kick, "snare": kit.snare, "clap": kit.clap, "hat": kit.hat, "ohat": kit.ohat,
                   "shaker": kit.shaker, "ge": kit.ge, "na": kit.na, "ti": kit.ti}[v]
            pan = {"hat": 0.25, "ohat": -0.2, "shaker": -0.3, "na": 0.15, "ti": -0.15}.get(v, 0)
            drums.add(snd, t, pan, vel)
            if v in ("snare", "clap", "na"): send.add(snd, t, pan, vel * 0.25)
            if v in ("kick", "ge"): kicks.append(t)
        if st["drums"] == "trap" and b % 2 == 1:   # hat roll at the end of every 2nd bar
            for k in range(6):
                t = b * bar + 12 * step + k * step * 2 / 3
                if t < end_t: drums.add(kit.hat, t, 0.25, 0.4 + 0.08 * k)
    # cut transitions: snare fill + riser before, crash + kick on the cut
    for c in cuts:
        rl = min(bar, c - 0.3)
        if rl > 0.5: fx.add(kit.riser(rl), c - rl, 0, 0.55)
        for k in range(4):
            tt = c - beat + k * step
            drums.add(kit.snare if st["drums"] != "dholak" else kit.na, tt, 0.1 * (k - 1.5), 0.35 + 0.15 * k)
        drums.add(kit.crash, c, 0, 0.9); drums.add(kit.kick, c, 0, 1.0); kicks.append(c)
        send.add(kit.crash, c, 0, 0.3)
    # frame-1 impact
    fx.add(kit.impact(), 0.0, 0, 0.9); send.add(kit.impact(), 0.0, 0, 0.25)
    # harmony + bass
    prev_root = None
    for b in range(nbars):
        t0 = b * bar
        if t0 >= end_t: break
        off, q = st["prog"][b % len(st["prog"])]
        notes = voicing(st["key"], off, q)
        root = st["key"] + off
        while root > 45: root -= 12
        while root < 33: root += 12
        dur = min(bar, end_t - t0)
        ch = st["chords"]
        if ch == "supersaw":
            harm.add(supersaw(notes, dur + 0.15, rng), t0, 0, 0.55); send.add(supersaw(notes, dur, rng), t0, 0, 0.12)
        elif ch == "stab":
            for s in (0, 3, 6, 10, 12):
                if t0 + s * step < end_t: harm.add(supersaw(notes, 0.35, rng, short=True), t0 + s * step, 0, 0.75)
            send.add(supersaw(notes, dur, rng), t0, 0, 0.06)
        elif ch == "epiano":
            for s, rs in ((0, 0), (6, 0.5), (10, 0.3)) if st["drums"] != "lofi" else ((0, 0), (8, 0.4)):
                if t0 + s * step >= end_t: continue
                for k, m in enumerate(notes):
                    harm.add(epiano(m, min(bar, end_t - t0) + 0.4), t0 + s * step + k * 0.012, (k - 1) * 0.3, 0.32 * (1 - rs * 0.4))
                    send.add(epiano(m, 1.0), t0 + s * step, 0, 0.1)
        elif ch == "harmonium":
            h = harmonium(notes, dur + 0.15); harm.add(h, t0, -0.1, 0.9); send.add(h, t0, 0, 0.2)
        # bass
        bk = st["bass"]
        if bk == "808":
            for s, ln in ((0, 11), (11, 5)):
                tt = t0 + s * step
                if tt < end_t and not gap(tt): bass.add(bass_note("808", root, ln * step, rng, prev_root), tt); prev_root = root
        elif bk == "offbeat":
            for s in (2, 6, 10, 14):
                tt = t0 + s * step
                if tt < end_t and not gap(tt): bass.add(bass_note("offbeat", root + 12, step * 1.6, rng), tt)
        elif bk == "sub":
            for s, ln in ((0, 6), (6, 4), (10, 6)):
                tt = t0 + s * step
                if tt < end_t and not gap(tt): bass.add(bass_note("sub", root + 12, ln * step, rng), tt)
        else:
            for s in (0, 3, 6, 8, 11, 14):
                tt = t0 + s * step
                if tt < end_t and not gap(tt): bass.add(bass_note("pluck", root + 12, step * 2.5, rng), tt)
    # lead melody: enters after the hook (first cut or bar 2), denser on the last scene
    mel = make_melody(st, rng, bars=max(8, nbars))
    lead_in = cuts[0] if cuts else bar * 2
    lk = st["lead"]
    for bt, m, ln in mel:
        t = bt * beat
        if t < lead_in - 0.01 or t >= end_t: continue
        last = section(t) == nsec - 1
        sec_len = ln * beat + 0.6
        if lk == "ks":
            s = ks(m, sec_len + 0.6, rng, 0.55); lead.add(s, t, 0.2, 0.55); lead.add(ks(m - 12, sec_len, rng, 0.4), t + 0.008, -0.25, 0.25)
        elif lk == "sitar":
            s = ks(m, sec_len + 1.0, rng, 0.75, 0.9975, buzz=0.6); lead.add(s, t, 0.15, 0.6)
        else:
            s = bell(m, sec_len + 0.5); lead.add(s, t, 0.1, 0.42)
            if last: lead.add(bell(m + 12, sec_len), t, -0.2, 0.15)
        for k in range(1, 4):  # ping-pong delay (dotted eighth)
            send.add(s, t, 0, 0.0)
            lead.add(s, t + k * beat * 0.75, 0.7 if k % 2 else -0.7, 0.33 ** k * 0.9)
        send.add(s, t, 0, 0.22)
    # final chord + hit
    off, q = st["prog"][0]
    fin = voicing(st["key"], off, q)
    if st["chords"] == "harmonium": fh = harmonium(fin, tail + 0.4)
    else: fh = supersaw(fin, tail + 0.4, rng)
    harm.add(fh, end_t, 0, 0.7); send.add(fh, end_t, 0, 0.5)
    drums.add(kit.crash, end_t, 0, 0.7); drums.add(kit.kick, end_t, 0, 1.0); kicks.append(end_t)
    if st["lead"] in ("ks", "sitar"):
        lead.add(ks(fin[-1] + 12, tail + 0.4, rng, 0.6, 0.997, 0.6 if st["lead"] == "sitar" else 0), end_t, 0.2, 0.5)
    # sidechain duck on bass + harmony
    tt = np.arange(n) / SR; duck = np.ones(n)
    for k in sorted(kicks):
        i = int(k * SR); j = min(n, i + int(0.25 * SR))
        if i < n: duck[i:j] = np.minimum(duck[i:j], 1 - 0.55 * np.exp(-(tt[i:j] - k) / 0.09))
    # mix: every stem is levelled to a target loudness (measured where it plays), so no style
    # ends up with a buried melody or a booming bass
    def level(x, db):
        m = np.abs(x).max(0); act = m > 1e-3
        if not act.any(): return x
        r = np.sqrt((x[:, act] ** 2).mean()); return x * (10 ** (db / 20) / (r + 1e-9))
    tg = dict(drums=-12, bass=-15.5, harm=-19, lead=-15.5)
    tg.update(st.get("levels", {}))
    mix = (level(drums.x, tg["drums"]) + level(bass.x, tg["bass"]) * duck + level(harm.x, tg["harm"]) * duck
           + level(lead.x, tg["lead"]) + fx.x * 0.75)
    mix += reverb(send.x, 1.8 if st["drums"] in ("lofi", "dholak") else 1.4, 7) * 0.35
    if st["drums"] == "lofi":   # vinyl crackle + a softer top end
        cr = np.zeros(n); idx = rng.integers(0, n, int(seconds * 25)); cr[idx] = rng.uniform(-0.25, 0.25, len(idx))
        mix += hp(np.vstack([cr, np.roll(cr, 37)]), 1500) * 0.6
        mix = lp(mix, 9000)
    mix = hp(mix, 28)
    fade = np.ones(n); fi = int(0.01 * SR); fo = int(0.35 * SR)
    fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo)
    mix = mix / (np.max(np.abs(mix)) + 1e-9)
    mix = np.tanh(mix * 1.6) / np.tanh(1.6) * fade * 0.92
    data = (mix.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())

if __name__ == "__main__":  # quick demo: python3 music.py out_dir
    import sys, os
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    for s in STYLES:
        make_music(18, os.path.join(d, f"demo-{s}.wav"), s, cuts=(3.0, 8.0, 13.0), seed=42)
        print("wrote", s)
