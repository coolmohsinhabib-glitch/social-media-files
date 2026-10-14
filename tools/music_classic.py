"""'classic': the original music from Mohsin's first video (eBay TIP #01), kept exactly as it was.
Approved by Mohsin on 14 Oct 2026 together with the cinematic 'rising' track.
make_classic(seconds, path) writes a 44.1 kHz mono WAV at 120 BPM (Am F C G).
"""
import wave
import numpy as np

BPM = 120
BEAT = 60 / BPM

def make_classic(seconds, path, sr=44100):
    n = int(seconds * sr); out = np.zeros(n); rng = np.random.default_rng(7)
    def place(sig, start):
        i = int(start * sr)
        if i >= n: return
        j = min(n, i + len(sig)); out[i:j] += sig[: j - i]
    note = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
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
            m = ch[[0, 1, 2, 1][k]] + 12
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

