"""The trailer's score: an original chiptune, synthesized here.

Four voices, as on an 8-bit console: a 25% pulse lead, a 12.5% pulse
arpeggio, a triangle bass and noise drums, at 120 beats a minute, so every
cut of the trailer (on whole seconds) lands on a beat. The song is a list of
sections, each a chord per bar and a melody written out note by note.
"""
import array
import math
import random
import wave

RATE = 44100
BPM = 120
BEAT = 60 / BPM
NOTES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
         "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
CHORDS = {"Am": ("A", [0, 3, 7]), "F": ("F", [0, 4, 7]), "C": ("C", [0, 4, 7]), "G": ("G", [0, 4, 7]),
          "Dm": ("D", [0, 3, 7]), "E": ("E", [0, 4, 7]), "E7": ("E", [0, 4, 7, 10]), "Bdim": ("B", [0, 3, 6]),
          "Em": ("E", [0, 3, 7]), "D": ("D", [0, 4, 7]), "Fm": ("F", [0, 3, 7])}


def freq(name, octave):
    n = NOTES[name] + 12 * (octave + 1)
    return 440.0 * 2 ** ((n - 69) / 12)


def parse_melody(text):
    """'E5:1 D5:.5 -:1' -> [(freq or None, beats)]"""
    out = []
    for tok in text.split():
        note, beats = tok.split(":")
        if note == "-":
            out.append((None, float(beats)))
        else:
            name, octave = note[:-1], int(note[-1])
            out.append((freq(name, octave), float(beats)))
    return out


# (name, bars, chords (one a bar), melody, energy 0..1)
SONG = [
    ("intro", 3, ["Am", "F", "C"], "A4:1 C5:1 E5:2 F4:1 A4:1 C5:2 G4:1 C5:1 E5:1 G5:1", 0.55),
    ("narrow", 4, ["Am", "F", "C", "G"],
     "E5:.5 E5:.5 D5:.5 C5:.5 A4:2 F5:.5 E5:.5 D5:.5 C5:.5 A4:2 G4:.5 A4:.5 C5:.5 E5:.5 G5:2 "
     "D5:.5 E5:.5 G5:1 B4:2", 0.7),
    ("looks", 4, ["Am", "F", "C", "G"],
     "A5:.5 G5:.5 E5:.5 C5:.5 E5:1 A4:1 F5:.5 E5:.5 C5:.5 A4:.5 C5:2 E5:.5 G5:.5 C6:1 G5:1 E5:1 "
     "D5:1 B4:.5 D5:.5 G5:2", 0.85),
    ("config", 3, ["F", "C", "G"], "A4:1 C5:1 F5:2 G4:1 C5:1 E5:2 B4:1 D5:1 G5:1 -:1", 0.6),
    ("work", 2, ["Am", "F"], "A4:.5 C5:.5 E5:.5 C5:.5 A4:.5 C5:.5 E5:1 F4:.5 A4:.5 C5:.5 A4:.5 F5:2", 0.75),
    ("boss", 3, ["Dm", "E", "Am"],
     "D5:.5 F5:.5 A5:1 G#5:.5 F5:.5 D5:1 E5:.5 G#5:.5 B5:1 G#5:1 E5:1 A5:.5 E5:.5 C5:.5 A4:.5 A4:2", 0.95),
    ("victory", 2, ["C", "G"], "C5:.5 E5:.5 G5:.5 C6:.5 C6:2 B5:.5 G5:.5 D5:.5 B4:.5 G5:2", 0.9),
    ("levelup", 2, ["F", "C"], "F5:.5 A5:.5 C6:1 A5:.5 C6:.5 F6:1 E6:.5 C6:.5 G5:.5 E5:.5 C6:2", 0.9),
    ("dungeon", 3, ["Am", "F", "G"],
     "A4:1 E5:1 A5:1 G5:1 F5:1 C5:1 A4:2 G4:.5 B4:.5 D5:.5 G5:.5 B5:2", 0.85),
    ("toprow", 4, ["C", "G", "Am", "F"],
     "E5:1 G5:1 C6:2 D5:1 G5:1 B5:2 C5:1 E5:1 A5:2 A4:.5 C5:.5 F5:.5 A5:.5 C6:2", 0.8),
    ("party", 3, ["F", "G", "C"], "A5:.5 G5:.5 F5:1 C5:2 B4:.5 D5:.5 G5:1 D5:2 E5:.5 G5:.5 C6:1 G5:2", 0.8),
    ("harvest", 3, ["Am", "Bdim", "E7"],
     "A4:.5 C5:.5 E5:.5 A5:.5 G#5:2 B4:.5 D5:.5 F5:.5 B5:.5 A5:2 G#5:.5 E5:.5 D5:.5 B4:.5 G#4:2", 0.85),
    ("live", 4, ["Am", "F", "C", "G"],
     "E5:.5 A5:.5 E5:.5 C5:.5 E5:1 A4:1 F5:.5 A5:.5 F5:.5 C5:.5 F5:2 G5:.5 E5:.5 C5:.5 E5:.5 G5:1 C6:1 "
     "B5:.5 G5:.5 D5:.5 G5:.5 B5:2", 0.9),
    ("bench", 2, ["F", "G"], "F5:1 A5:1 C6:2 D6:1 B5:1 G5:2", 0.75),
    ("outro", 2, ["F", "C"], "A5:1 G5:1 F5:2 E5:4", 0.6),
]


def envelope(n, attack=0.004, release=0.04, sustain=0.75, decay=0.06):
    a, d, r = int(attack * RATE), int(decay * RATE), int(release * RATE)
    out = []
    for i in range(n):
        if i < a:
            v = i / max(1, a)
        elif i < a + d:
            v = 1 - (1 - sustain) * (i - a) / max(1, d)
        else:
            v = sustain
        if i > n - r:
            v *= max(0.0, (n - i) / max(1, r))
        out.append(v)
    return out


def pulse(f, n, duty, vol, vibrato=0.0):
    env = envelope(n)
    out = []
    phase = 0.0
    for i in range(n):
        ff = f * (1 + vibrato * math.sin(2 * math.pi * 5.5 * i / RATE)) if vibrato and i > RATE * 0.12 else f
        phase = (phase + ff / RATE) % 1.0
        out.append((1.0 if phase < duty else -1.0) * vol * env[i])
    return out


def triangle(f, n, vol):
    env = envelope(n, release=0.02, sustain=0.9)
    return [(4 * abs(((i * f / RATE) % 1.0) - 0.5) - 1) * vol * env[i] for i in range(n)]


def noise(n, vol, decay, rng, lowpass=0.0):
    out, prev = [], 0.0
    for i in range(n):
        v = rng.uniform(-1, 1)
        prev = prev * lowpass + v * (1 - lowpass)
        out.append(prev * vol * math.exp(-i / (decay * RATE)))
    return out


def kick(n, vol):
    out = []
    phase = 0.0
    for i in range(n):
        f = 150 * math.exp(-i / (0.03 * RATE)) + 45
        phase += f / RATE
        out.append(math.sin(2 * math.pi * phase) * vol * math.exp(-i / (0.12 * RATE)))
    return out


def add(buf, start, samples, pan=0.0):
    left, right = (1 - max(0, pan)), (1 + min(0, pan))
    for i, v in enumerate(samples):
        j = start + i
        if j >= len(buf) // 2:
            break
        buf[2 * j] += v * left
        buf[2 * j + 1] += v * right


def render(path, seconds=None):
    """Write the score as a 16-bit stereo WAV; returns its length in seconds."""
    beats = sum(bars * 4 for _, bars, *_ in SONG)
    length = seconds or beats * BEAT + 1.5
    total = int(length * RATE)
    buf = [0.0] * (2 * total)
    rng = random.Random(4)
    t_beat = 0
    for name, bars, chords, melody, energy in SONG:
        start_beat = t_beat
        for b, chord in enumerate(chords[:bars] + chords[bars:]):
            if b >= bars:
                break
            root, shape = CHORDS[chord]
            bar_start = start_beat + 4 * b
            for step in range(8):                              # bass: eighths, root and octave
                oct_ = 2 if step % 2 == 0 else 3
                note = freq(root, oct_) * (1.5 if step in (3, 7) and chord not in ("Bdim",) else 1.0)
                n = int(BEAT / 2 * RATE * 0.9)
                add(buf, int((bar_start + step / 2) * BEAT * RATE), triangle(note, n, 0.32))
            tones = [freq(root, 4) * 2 ** (s / 12) for s in shape]
            if energy > 0.6:                                   # arpeggio: sixteenths through the chord
                for step in range(16):
                    f = tones[step % len(tones)] * (2 if (step // len(tones)) % 2 else 1)
                    n = int(BEAT / 4 * RATE * 0.8)
                    add(buf, int((bar_start + step / 4) * BEAT * RATE), pulse(f, n, 0.125, 0.06 * energy),
                        pan=0.35)
            for step in range(8):                              # drums
                at = int((bar_start + step / 2) * BEAT * RATE)
                if step in (0, 4) or (energy > 0.85 and step == 6):
                    add(buf, at, kick(int(0.25 * RATE), 0.55))
                if step in (2, 6):
                    add(buf, at, noise(int(0.18 * RATE), 0.22 * energy, 0.05, rng, 0.2))
                add(buf, at, noise(int(0.05 * RATE), 0.07 * energy, 0.012, rng, 0.0), pan=-0.3)
        t = start_beat
        for f, length_b in parse_melody(melody):               # the lead
            if f is not None:
                n = int(length_b * BEAT * RATE * 0.92)
                add(buf, int(t * BEAT * RATE), pulse(f, n, 0.25, 0.17, vibrato=0.004 if length_b >= 1 else 0),
                    pan=-0.15)
            t += length_b
        t_beat += bars * 4
    peak = max(1e-9, max(abs(v) for v in buf))
    data = array.array("h", (int(max(-1, min(1, v / peak * 0.8)) * 32767) for v in buf))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())
    return length


def section_starts():
    """{section: start in seconds}, so the shots can cut where the music changes."""
    out, t = {}, 0.0
    for name, bars, *_ in SONG:
        out[name] = t
        t += bars * 4 * BEAT
    return out
