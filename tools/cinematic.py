"""Cinematic moods for the short videos: suspense, inspiring, motivational (original, royalty-free).

make_cinematic(seconds, path, mood, cuts=(), seed=None) writes a 44.1 kHz stereo WAV.
Instruments are modelled, not sampled: piano (inharmonic partials, 3 strings per note, hammer),
string ensemble (6 detuned bows per note with vibrato), staccato strings, tremolo, taiko,
braam (cinematic brass hit), ticking clock, reverse swells, hall reverb.
The arrangement follows the video: a hit on frame 1, a swell into every scene cut, a hit on
the cut, the theme on the last scenes, and a final chord that rings out.
"""
import wave
import numpy as np
from scipy.signal import fftconvolve
from music import SR, hz, tvec, lp, hp, bp, saw, Bus, Kit, QUAL

def vo(root, q, lo, hi):
    while root < lo: root += 12
    while root > hi: root -= 12
    return [root + i for i in QUAL[q]]

# ---------------------------------------------------------------- instruments
def piano(m, dur, vel, rng):
    f = hz(m); n = int((dur + 0.3) * SR); t = np.arange(n) / SR
    base = max(0.35, 1.1 - (m - 48) * 0.02); s = np.zeros(n)
    for k in range(1, 13):
        fk = k * f * np.sqrt(1 + 0.00035 * k * k)
        if fk > 15000: break
        a = vel ** (0.5 + 0.12 * k) / k
        for det in (-0.8, 0.0, 0.9):
            s += a * np.sin(2 * np.pi * fk * 2 ** (det / 1200) * t + rng.random() * 6.283) * np.exp(-t * base * (1 + 0.4 * (k - 1))) / 3
    s *= 0.6 * np.exp(-t * 3.5) + 0.4
    h = min(n, int(0.025 * SR)); s[:h] += lp(rng.standard_normal(h), 2200) * np.exp(-np.arange(h) / SR * 220) * 0.12 * vel
    off = int(dur * SR)
    if off < n: s[off:] *= np.exp(-np.arange(n - off) / SR * 18)
    s = lp(s, 1400 + 6500 * vel); a = int(0.0015 * SR); s[:a] *= np.linspace(0, 1, a)
    return s * 0.55

def strings(notes, dur, rng, att=0.5, rel=0.9, bright=2600, voices=6, trem=0.0):
    n = int((dur + rel) * SR); t = np.arange(n) / SR; L = np.zeros(n); R = np.zeros(n)
    vib_on = np.clip(t / 0.5, 0, 1)
    for m in notes:
        for v in range(voices):
            det = rng.uniform(-11, 11); vr = 5 + rng.random() * 0.8
            fr = hz(m) * 2 ** (det / 1200) * (1 + 0.003 * vib_on * np.sin(2 * np.pi * vr * t + rng.random() * 6.28))
            s = 2 * ((np.cumsum(fr) / SR + rng.random()) % 1.0) - 1
            if v % 2: L += s
            else: R += s
    e = np.ones(n); na = max(1, int(att * SR)); e[:na] = np.sin(np.linspace(0, np.pi / 2, na)) ** 2
    nd = int(dur * SR); e[nd:] = np.linspace(1, 0, n - nd) ** 2
    if trem: e *= 1 - trem * (0.5 + 0.5 * np.sin(2 * np.pi * 7.5 * t))
    out = np.vstack([lp(L, bright, 4), lp(R, bright, 4)]) * e
    out = hp(out, 70)
    return out / (len(notes) * voices / 2)

def stacc(m, rng, length=0.2, bright=3200):
    t = tvec(length); s = np.zeros(len(t))
    for v in range(4):
        s += saw(hz(m) * 2 ** (rng.uniform(-8, 8) / 1200), t, rng.random())
    e = np.exp(-t * 16); a = int(0.004 * SR); e[:a] *= np.linspace(0, 1, a)
    return lp(s, bright, 4) * e / 4

def braam(root, dur, rng):
    n = int(dur * SR); t = np.arange(n) / SR; s = np.zeros(n)
    for m in (root, root + 7, root + 12, root + 19):
        for v in range(4):
            s += saw(hz(m) * 2 ** (rng.uniform(-12, 12) / 1200), t, rng.random())
    out = np.zeros(n); blk = 512
    for b in range(0, n, blk):
        tt = b / SR; c = 180 + 2600 * (tt / 0.18 if tt < 0.18 else np.exp(-(tt - 0.18) * 1.6))
        out[b:b + blk] = lp(s[b:b + blk], c, 2)
    e = np.exp(-t * 1.1); a = int(0.015 * SR); e[:a] *= np.linspace(0, 1, a)
    return np.tanh(1.8 * out / 16) * e

def taiko(rng, pitch=1.0, size=1.0):
    t = tvec(1.1); f = 52 * pitch + 70 * np.exp(-t * 22)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.2 / size)
    skin = bp(rng.standard_normal(len(t)), 120, 1400) * np.exp(-t * 28) * 0.6
    return np.tanh(1.5 * (body + skin))

def tick(rng, hi=True):
    t = tvec(0.05)
    return (bp(rng.standard_normal(len(t)), 2500, 8000) * np.exp(-t * 520) * 0.8
            + np.sin(2 * np.pi * (2300 if hi else 1700) * t) * np.exp(-t * 260) * 0.35)

def choir(notes, dur, rng):
    """'Aah' pad: string-like source through vowel formants."""
    src = strings(notes, dur, rng, att=0.8, rel=1.2, bright=6000, voices=4)
    out = sum(g * bp(src, f * 0.85, f * 1.15) for f, g in ((750, 1.0), (1200, 0.55), (2600, 0.3)))
    return out * 2.2

def hall(x, sec=2.8, seed=3):
    r = np.random.default_rng(seed); t = tvec(sec); out = []
    for ch in range(2):
        nz = r.standard_normal(len(t))
        ir = lp(nz, 7000) * np.exp(-t * 6.9 / (sec * 0.45)) * 0.5 + lp(nz, 2400) * np.exp(-t * 6.9 / sec)
        er = np.zeros(int(0.08 * SR))
        for _ in range(10): er[r.integers(int(0.006 * SR), len(er))] += r.uniform(0.2, 0.6)
        ir = np.concatenate([er, np.zeros(int(0.02 * SR))]) if False else ir
        ir[: len(er)] += er
        ir = np.concatenate([np.zeros(int(0.022 * SR)), ir])
        out.append(fftconvolve(x[ch], ir)[: x.shape[1]])
    out = np.array(out)
    return out * (np.sqrt((x ** 2).mean()) + 1e-9) / (np.sqrt((out ** 2).mean()) + 1e-9)

def reverse_swell(notes, length, rng):
    n = int(length * SR)
    ch = sum(piano(m, 0.5, 0.9, rng) for m in notes)
    pad = np.zeros(n + int(0.6 * SR)); pad[: len(ch)] += ch[: len(pad)]
    st = np.vstack([pad, pad]); wet = hall(st, 2.5, 9)[:, :n]
    out = wet[:, ::-1] * np.linspace(0, 1, n) ** 1.5
    return out

# ---------------------------------------------------------------- moods
MOODS = {
    "suspense":     dict(bpm=120, key=45, prog=[(0, "m"), (-4, "M"), (-7, "m"), (-5, "M")]),   # Am F Dm E
    "inspiring":    dict(bpm=100, key=48, prog=[(9, "m"), (5, "M"), (0, "M"), (7, "M")]),     # Am F C G (C major)
    "motivational": dict(bpm=110, key=50, prog=[(0, "m"), (-4, "M"), (3, "M"), (-2, "M")]),   # Dm Bb F C
    "rising":       dict(bpm=104, key=48, prog=[(9, "m"), (5, "M"), (0, "M"), (7, "M")]),     # inspiring -> epic (C major)
}
THEMES = {  # (bar, beat, midi, beats) over the 4-chord loop
    "rising": None,
    "inspiring": [(0, 0, 76, 1.5), (0, 1.5, 74, .5), (0, 2, 72, 1), (0, 3, 76, 1), (1, 0, 77, 1.5), (1, 1.5, 76, .5), (1, 2, 72, 2),
                  (2, 0, 79, 1.5), (2, 1.5, 76, .5), (2, 2, 72, 1), (2, 3, 74, 1), (3, 0, 74, 2), (3, 2, 71, 1), (3, 3, 74, 1)],
    "motivational": [(0, 0, 69, 2), (0, 2, 74, 1), (0, 3, 77, 1), (1, 0, 77, 2), (1, 2, 74, 2), (2, 0, 72, 1), (2, 1, 77, 1),
                     (2, 2, 81, 2), (3, 0, 79, 2), (3, 2, 76, 1), (3, 3, 72, 1)],
    "suspense": [(0, 0, 81, 2), (0, 2, 76, 2), (1, 0, 77, 2), (1, 2, 72, 2), (2, 0, 74, 2), (2, 2, 77, 2), (3, 0, 80, 2), (3, 2, 76, 2)],
}

def make_cinematic(seconds, path, mood="inspiring", cuts=(), seed=None):
    md = MOODS[mood]; rng = np.random.default_rng(seed if seed is not None else 11)
    beat = 60 / md["bpm"]; bar = 4 * beat; n = int(seconds * SR); kit = Kit(rng)
    B = {k: Bus(n) for k in ("perc", "low", "keys", "str", "lead", "fx", "send")}
    cuts = sorted(c for c in set(cuts) if 0.5 < c < seconds - 1.0)
    tail = 2.3; end_t = max(bar, seconds - tail); nsec = len(cuts) + 1
    sec = lambda t: sum(1 for c in cuts if c <= t)
    gap = lambda t: any(c - beat * 0.5 <= t < c for c in cuts)
    nbars = int(np.ceil(end_t / bar))
    def add(bus, sig, t, pan=0, g=1.0, send=0.0):
        if t >= end_t + 0.001 and bus not in ("fx",): return
        B[bus].add(sig, t, pan, g)
        if send: B["send"].add(sig, t, pan, g * send)
    theme = THEMES[mood] or THEMES["inspiring"]
    # ---- frame-1 hit
    root0 = md["key"] + md["prog"][0][0]
    if mood in ("inspiring", "rising"):
        add("fx", kit.impact(), 0, 0, 0.45 if mood == "inspiring" else 0.7, 0.4)
        if mood == "rising":
            for p, pn in ((1.0, -0.2), (0.85, 0.2)): add("perc", taiko(rng, p), 0.0, pn, 0.6, 0.5)
        for m in vo(root0, md["prog"][0][1], 57, 69): add("keys", piano(m, bar, 0.95, rng), 0.0, 0, 0.6, 0.5)
    else:
        add("fx", kit.impact(), 0, 0, 0.8, 0.3)
        add("low", braam(vo(root0, "M", 33, 44)[0], 3.0, rng), 0, 0, 1.0, 0.5)
        for p, pn in ((1.0, -0.3), (0.85, 0.3), (1.15, 0)): add("perc", taiko(rng, p), 0.0 + rng.random() * 0.012, pn, 0.7, 0.5)
    # ---- bars
    for b in range(nbars):
        t0 = b * bar; s = sec(t0); last = s == nsec - 1 and nsec > 1; mid = s >= 1
        off, q = md["prog"][b % 4]; r = md["key"] + off
        bass = vo(r, q, 33, 44)[0]; chord = vo(r, q, 55, 66); high = vo(r, q, 64, 76)
        dur = min(bar, end_t - t0)
        if mood == "suspense":
            add("str", strings([bass, bass + 7], dur, rng, 0.3, 0.6, 900), t0, 0, 0.9, 0.3)                         # drone
            add("str", strings([high[-1] + 12], dur, rng, 0.15, 0.4, 5000, 4, trem=0.6), t0, 0.3, 0.35, 0.5)       # tremolo violin
            for k in range(16):                                                                                     # pulse
                tt = t0 + k * beat / 4
                if tt >= end_t or gap(tt): continue
                v = (1.0 if k % 4 == 0 else 0.6) * (0.55 if s == 0 else 1.0)
                add("low", stacc(bass + 12, rng, 0.14, 500 + 900 * (b % 4) / 3), tt, 0, v)
            for k in range(8):                                                                                      # clock
                tt = t0 + k * beat / 2
                if tt < end_t and not gap(tt): add("perc", tick(rng, k % 2 == 0), tt, 0.35, 0.45 if k % 2 == 0 else 0.25, 0.15)
            if mid:
                for k in range(8):                                                                                  # staccato ostinato
                    tt = t0 + k * beat / 2
                    if tt >= end_t or gap(tt): continue
                    nn = [chord[0], chord[0] + 12, chord[2], chord[0] + 12, chord[1], chord[0] + 12, chord[2], chord[1] + 12][k]
                    add("str", stacc(nn, rng), tt, -0.25, 0.8, 0.25)
                for bt, g in ((0, 1.0), (2.5, 0.75)) if not last else ((0, 1), (1.5, .6), (2, .8), (2.5, .7), (3, .9), (3.5, .8)):
                    tt = t0 + bt * beat
                    if tt < end_t and not gap(tt): add("perc", taiko(rng, 1.0 + 0.1 * (bt % 1)), tt, 0, g, 0.45)
            if last:
                add("str", strings(chord + [chord[0] + 12], dur, rng, 0.2, 0.8, 3400), t0, 0, 0.9, 0.4)
                if b == int(cuts[-1] // bar) + 1 if cuts else False: pass
        elif mood == "inspiring":
            pat = [bass + 12, chord[2], chord[0] + 12, chord[1] + 12, chord[0] + 12, chord[2], chord[1] + 12, chord[2] + 12]
            for k in range(8):                                                                                      # piano arpeggio
                tt = t0 + k * beat / 2
                if tt >= end_t: continue
                add("keys", piano(pat[k], beat * 1.5, 0.75 if k % 2 == 0 else 0.55, rng), tt, (k % 3 - 1) * 0.2, 0.7, 0.35)
            add("keys", piano(bass, bar, 0.7, rng), t0, 0, 0.7, 0.3)
            add("str", strings(chord, dur, rng, 0.7 if s == 0 else 0.4, 1.0, 1800 if s == 0 else 2800), t0, 0, 0.55 if s == 0 else 0.8, 0.5)
            if mid:
                add("low", strings([bass], dur, rng, 0.05, 0.3, 600, 3), t0, 0, 0.9)
                for k in range(4):
                    tt = t0 + k * beat
                    if tt >= end_t or gap(tt): continue
                    if k in (0, 2): add("perc", kit.kick, tt, 0, 0.8)
                    if k in (1, 3): add("perc", kit.clap, tt, 0, 0.45, 0.4)
                for k in range(8):
                    tt = t0 + k * beat / 2
                    if tt < end_t and not gap(tt): add("perc", kit.shaker, tt, -0.3, 0.5 if k % 2 else 0.3)
            if last:
                add("str", strings([m + 12 for m in chord], dur, rng, 0.3, 1.0, 4200), t0, 0.1, 0.55, 0.5)
        elif mood == "rising":
            pat = [bass + 12, chord[2], chord[0] + 12, chord[1] + 12, chord[0] + 12, chord[2], chord[1] + 12, chord[2] + 12]
            for k in range(8):                                                                                      # piano arpeggio, all the way
                tt = t0 + k * beat / 2
                if tt < end_t: add("keys", piano(pat[k], beat * 1.5, (0.75 if k % 2 == 0 else 0.55) * (0.85 if last else 1), rng), tt, (k % 3 - 1) * 0.2, 0.7, 0.35)
            add("keys", piano(bass, bar, 0.7, rng), t0, 0, 0.7, 0.3)
            add("str", strings(chord, dur, rng, 0.7 if s == 0 else 0.35, 1.0, 1800 if s == 0 else 3000), t0, 0, 0.55 if s == 0 else 0.8, 0.5)
            if mid:
                add("low", strings([bass, bass + 12], dur, rng, 0.15, 0.5, 1100), t0, 0, 0.8, 0.3)
                for bt in (0, 2):
                    tt = t0 + bt * beat
                    if tt < end_t and not gap(tt): add("perc", taiko(rng, 1.0, 0.8), tt, 0, 0.75, 0.4)
            if s >= 2 or last:                                                                                      # epic layer
                for k in range(16):
                    tt = t0 + k * beat / 4
                    if tt >= end_t or gap(tt): continue
                    nn = [chord[0], chord[0], chord[2], chord[0], chord[0] + 12, chord[0], chord[2], chord[1]][k % 8]
                    add("str", stacc(nn - 12, rng, 0.16, 2600), tt, -0.2, 1.0 if k % 4 == 0 else 0.6, 0.2)
                hits = ((1.5, 0.6, 1.2), (3, 0.6, 1.3), (3.5, 0.7, 1.2))
                if last: hits += ((1, .7, 1.25), (2.5, .6, 1.3), (3.75, .55, 1.35))
                for bt, g, p in hits:
                    tt = t0 + bt * beat
                    if tt < end_t and not gap(tt): add("perc", taiko(rng, p, 0.8), tt, (p - 1.15) * 2, g, 0.45)
            if last:
                add("lead", choir(chord, dur, rng), t0, 0, 0.6, 0.6)
                add("low", braam(bass, min(bar, 2.0), rng), t0, 0, 0.45, 0.4)
                add("str", strings([m + 12 for m in chord], dur, rng, 0.3, 1.0, 4200), t0, 0.1, 0.55, 0.5)
                for k in (1, 3):
                    tt = t0 + k * beat
                    if tt < end_t and not gap(tt): add("perc", kit.clap, tt, 0, 0.6, 0.5)
        else:  # motivational
            for k in range(16):                                                                                     # 16th ostinato
                tt = t0 + k * beat / 4
                if tt >= end_t or gap(tt): continue
                nn = [chord[0], chord[0], chord[2], chord[0], chord[0] + 12, chord[0], chord[2], chord[1]][k % 8]
                add("str", stacc(nn - 12, rng, 0.16, 2600), tt, -0.2, (1.0 if k % 4 == 0 else 0.65) * (0.7 if s == 0 else 1.0), 0.2)
            add("low", strings([bass, bass + 12], dur, rng, 0.2, 0.6, 1200), t0, 0, 0.8, 0.3)
            if mid:
                add("str", strings(chord, dur, rng, 0.25, 0.9, 3000), t0, 0, 0.75, 0.45)
                hits = ((0, 1.0, 1.0), (1.5, 0.6, 1.2), (2, 0.85, 1.0), (3, 0.6, 1.3), (3.5, 0.7, 1.2))
                if last: hits += ((1, .7, 1.25), (2.5, .6, 1.3), (3.75, .55, 1.35))
                for bt, g, p in hits:
                    tt = t0 + bt * beat
                    if tt < end_t and not gap(tt): add("perc", taiko(rng, p, 0.8), tt, (p - 1.15) * 2, g, 0.45)
            if last:
                add("lead", choir(chord, dur, rng), t0, 0, 0.8, 0.6)
                add("low", braam(bass, min(bar, 2.0), rng), t0, 0, 0.55, 0.4)
                for k in (1, 3):
                    tt = t0 + k * beat
                    if tt < end_t and not gap(tt): add("perc", kit.clap, tt, 0, 0.6, 0.5)
        # theme
        th_on = (mood == "rising" and (s >= 2 or last)) or (mood == "suspense" and mid) or (mood == "inspiring" and (s >= 2 or (s >= 1 and nsec <= 2))) or (mood == "motivational" and (last or (s >= 2 and nsec > 3)))
        if th_on:
            for tb, bt, m, ln in theme:
                if tb != b % 4: continue
                tt = t0 + bt * beat
                if tt >= end_t: continue
                if mood == "suspense":
                    add("lead", piano(m, ln * beat, 0.6, rng), tt, 0.25, 0.75, 0.9)
                elif mood == "rising":
                    add("lead", piano(m + 12, ln * beat, 0.85, rng), tt, 0.15, 0.55, 0.5)
                    if last:
                        add("lead", strings([m, m - 12], ln * beat, rng, 0.08, 0.6, 3800, 5), tt, 0.1, 1.0, 0.55)
                        add("lead", braam(m - 24, ln * beat + 0.3, rng), tt, -0.1, 0.12, 0.3)
                elif mood == "inspiring":
                    add("lead", piano(m + 12, ln * beat, 0.8, rng), tt, 0.15, 0.6, 0.5)
                    add("lead", piano(m, ln * beat, 0.7, rng), tt, -0.15, 0.4, 0.4)
                    if last: add("str", strings([m], ln * beat, rng, 0.08, 0.5, 4000, 4), tt, 0, 0.5, 0.5)
                else:
                    add("lead", strings([m, m - 12], ln * beat, rng, 0.08, 0.6, 3800, 5), tt, 0.1, 1.0, 0.55)
                    add("lead", braam(m - 24, ln * beat + 0.3, rng), tt, -0.1, 0.18, 0.3)
    # ---- transitions
    for c in cuts:
        sw = min(bar * 0.75, c - 0.2)
        off, q = md["prog"][int(c // bar) % 4]
        add("fx", reverse_swell(vo(md["key"] + off, q, 60, 72), sw, rng), c - sw, 0, 0.9)
        rc = kit.crash[:, ::-1][:, -int(sw * SR):] if sw < kit.crash.shape[1] / SR else kit.crash[:, ::-1]
        add("fx", rc, c - rc.shape[1] / SR, 0, 0.5)
        if mood != "inspiring" and not (mood == "rising" and c == cuts[0]):
            add("fx", kit.riser(sw), c - sw, 0, 0.4)
            for p, pn in ((1.0, -0.3), (0.9, 0.3)): add("perc", taiko(rng, p), c, pn, 0.8, 0.5)
            add("fx", kit.impact(), c, 0, 0.45, 0.3)
            if mood in ("motivational", "rising"):
                for k in range(4): add("perc", taiko(rng, 1.4, 0.5), c - beat + k * beat / 4, 0.2 * (k - 1.5), 0.35 + 0.12 * k)
        else:
            add("perc", kit.kick, c, 0, 0.9); add("fx", kit.crash, c, 0, 0.6, 0.4)
    # ---- ending
    if mood in ("inspiring", "rising"): fin = vo(md["key"], "M", 55, 66)
    elif mood == "motivational": fin = vo(md["key"], "M", 55, 66)        # D major: lift at the end
    else: fin = vo(md["key"], "m", 55, 66)
    froot = vo(fin[0], "M", 33, 44)[0]
    add("str", strings(fin + [fin[0] + 12], tail, rng, 0.05, 1.6, 3000), end_t, 0, 1.0, 0.7)
    for m in fin + [froot, froot + 12]: B["keys"].add(piano(m, tail, 0.9, rng), end_t); B["send"].add(piano(m, tail, 0.9, rng), end_t, 0, 0.5)
    if mood != "inspiring":
        B["low"].add(braam(froot, tail + 0.3, rng), end_t, 0, 0.9)
        for p in (1.0, 0.85): B["perc"].add(taiko(rng, p), end_t, 0, 0.9)
        B["fx"].add(kit.impact(), end_t, 0, 0.6)
        if mood == "suspense":
            B["perc"].add(tick(rng), end_t + 1.0, 0.35, 0.5); B["send"].add(tick(rng), end_t + 1.0, 0.35, 0.5)
    else:
        B["fx"].add(kit.crash, end_t, 0, 0.5); B["perc"].add(kit.kick, end_t, 0, 0.9)
    # ---- mix
    def level(x, db):
        a = np.abs(x).max(0) > 1e-3
        if not a.any(): return x
        return x * 10 ** (db / 20) / (np.sqrt((x[:, a] ** 2).mean()) + 1e-9)
    tg = {"suspense": dict(perc=-15, low=-16, keys=-20, str=-17, lead=-17),
          "inspiring": dict(perc=-19, low=-19, keys=-14, str=-18, lead=-15.5),
          "motivational": dict(perc=-13.5, low=-17, keys=-20, str=-15, lead=-16),
          "rising": dict(perc=-15, low=-17.5, keys=-16, str=-16, lead=-15.5)}[mood]
    mix = sum(level(B[k].x, v) for k, v in tg.items()) + B["fx"].x * 0.6
    mix += hall(B["send"].x, 3.0 if mood != "motivational" else 2.6) * (0.45 if mood == "inspiring" else 0.38)
    mix = hp(mix, 30)
    fo = int(0.4 * SR); mix[:, -fo:] *= np.linspace(1, 0, fo)
    mix /= np.max(np.abs(mix)) + 1e-9
    mix = np.tanh(mix * 1.5) / np.tanh(1.5) * 0.92
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix.T * 32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    import sys, os
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    for m in MOODS:
        make_cinematic(24, os.path.join(d, f"{m}.wav"), m, cuts=(3.0, 9.0, 15.0), seed=7); print("wrote", m)
