#!/usr/bin/env python3
"""Generate regions.js: polygons laid over wheel.png, one per emotion word.

Usage:
    python3 make_regions.py            # write regions.js
    python3 make_regions.py --preview  # also write /tmp/preview.png to check alignment

Needs Pillow and numpy. Angles are degrees clockwise from 12 o'clock around CENTER.
Nominal spoke positions come from SECTORS; each one is then snapped to the nearest
white spoke line actually painted in wheel.png. If regions don't line up, tweak
CENTER / RADII / SECTORS below.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = Image.open(os.path.join(HERE, "wheel.png")).convert("RGB")
PIXELS = np.asarray(IMAGE).astype(float)
WHITENESS = PIXELS.min(axis=2)  # white chalk lines have high values in every channel

CENTER = (768, 703)
Y_SCALE = 0.97  # the photographed wheel is slightly squashed vertically
RADII = [0, 168, 400, 622]  # core / middle / outer ring boundaries (outer is re-measured per angle)
OUTER_MARGIN = 2  # px past the measured edge, so the faded overlay fully covers the paint
SNAP_RANGE = 3.0  # degrees either side of the nominal spoke to search
SNAP_STEP = 0.25

# Each sector: name, start angle, end angle (clockwise), then the middle- and outer-ring
# words in clockwise order. Every sector has 8 words per ring, split evenly (then snapped).
SECTORS = [
    ("Joy", 330, 386.5,
     ["Connected", "Present", "Calm", "Intimate", "Safe", "Care", "Silly", "Acceptance"],
     ["Seen", "Grounded", "Grateful", "Tender", "Belonging", "Love", "Free", "Kindness"]),
    ("Genius", 26.5, 91.2,
     ["Inspired", "In awe", "Interested", "Confident", "Focused", "Creative", "Passionate", "Challenged"],
     ["Moved", "Proud", "Curious", "Brave", "In flow", "Manic", "Empowered", "Motivated"]),
    ("Anger", 91.2, 148,
     ["Protective", "Skeptical", "Resentful", "Armored up", "Frustrated", "Mad", "Aggressive", "Tense"],
     ["Loyal", "Suspicious", "Envious", "Defensive", "Irritated", "Furious", "Violent", "Hateful"]),
    ("Sad", 148, 206.5,
     ["Left out", "Disappointed", "Loss", "Tired", "Bored", "Unmotivated", "Lonely", "Lost"],
     ["Hurt", "Depressed", "Heartbroken", "Exhausted", "Numb", "Burnt out", "Isolated", "Purposeless"]),
    ("Fear", 206.5, 271.5,
     ["Fragile", "Insecure", "Worried", "Uncontrollable", "Surprised", "Threatened", "Busy", "Insignificant"],
     ["Vulnerable", "Unsafe", "Anxious", "Addicted", "Taken advantage of", "Terrified", "Overwhelmed", "Imposter syndrome"]),
    ("Disgust", 271.5, 330,
     ["Not good enough", "Embarrassed", "Guilty", "Uncomfortable", "Awful", "Avoidance", "Tainted", "Disapproval"],
     ["Ashamed", "Humiliated", "Judgemental", "Self-conscious", "Nauseous", "Aversion", "Jealous", "Not normal"]),
]


def raw_point(r, deg):
    a = math.radians(deg)
    return [round(CENTER[0] + r * math.sin(a), 1), round(CENTER[1] - r * math.cos(a) * Y_SCALE, 1)]


def measure_outer_edge():
    """Radius of the wheel's outer edge for each whole degree, found by marching out
    from the middle ring until the image turns to a solid run of white paper."""
    height, width = WHITENESS.shape
    edge = np.full(360, np.nan)
    for deg in range(360):
        run = 0
        for r in range(450, 760):
            x, y = (int(v) for v in raw_point(r, deg))
            if not (0 <= x < width and 0 <= y < height):
                break
            run = run + 1 if WHITENESS[y, x] > 232 else 0
            if run >= 14:
                edge[deg] = r - 13
                break
    # Smooth over a 9-degree circular window; fill any gaps from neighbours.
    padded = np.concatenate([edge[-4:], edge, edge[:4]])
    smooth = np.array([np.nanmedian(padded[i:i + 9]) for i in range(360)])
    return np.where(np.isnan(smooth), RADII[3], smooth)


OUTER_EDGE = measure_outer_edge()


def point(r, deg):
    if r == RADII[3]:  # the outer rim follows the real edge of the painting
        r = OUTER_EDGE[int(round(deg)) % 360] + OUTER_MARGIN
    return raw_point(r, deg)


def line_score(r0, a0, r1, a1, samples=40):
    """Mean whiteness along a segment, minus the surroundings (so only thin bright lines score high)."""
    p0, p1 = np.array(point(r0, a0)), np.array(point(r1, a1))
    direction = p1 - p0
    normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
    t = np.linspace(0, 1, samples)[:, None]
    along = p0 + t * direction

    def sample(offset):
        xy = np.rint(along + offset * normal).astype(int)
        xy[:, 0] = xy[:, 0].clip(0, WHITENESS.shape[1] - 1)
        xy[:, 1] = xy[:, 1].clip(0, WHITENESS.shape[0] - 1)
        return WHITENESS[xy[:, 1], xy[:, 0]].mean()

    return sample(0) - 0.5 * (sample(-5) + sample(5))


def snap(r0, r1, nominal):
    """Find the (angle at r0, angle at r1) of the white spoke near `nominal`."""
    offsets = np.arange(-SNAP_RANGE, SNAP_RANGE + 1e-9, SNAP_STEP)
    best, best_score = (nominal, nominal), -1e9
    for d_in in offsets:
        for d_out in offsets:
            if abs(d_in - d_out) > 2:
                continue
            score = line_score(r0 + 8, nominal + d_in, r1 - 8, nominal + d_out)
            if score > best_score:
                best, best_score = (nominal + d_in, nominal + d_out), score
    return best


def arc(r, a0, a1):
    steps = max(2, int(abs(a1 - a0)))
    return [point(r, a0 + (a1 - a0) * i / steps) for i in range(steps + 1)]


def build():
    regions = []
    for core, a0, a1, middle, outer in SECTORS:
        core_edges = None
        for ring, words in ((1, middle), (2, outer)):
            r0, r1 = RADII[ring], RADII[ring + 1]
            step = (a1 - a0) / len(words)
            edges = [snap(r0, r1, a0 + i * step) for i in range(len(words) + 1)]
            # Fall back to the even split if snapping made the spokes cross or bunch up.
            if any(edges[i + 1][0] - edges[i][0] < 2 or edges[i + 1][1] - edges[i][1] < 2
                   for i in range(len(words))):
                print(f"  {core} ring {ring}: snapping unreliable, using even split")
                edges = [(a0 + i * step,) * 2 for i in range(len(words) + 1)]
            if ring == 1:
                core_edges = (edges[0][0], edges[-1][0])
            for i, word in enumerate(words):
                (in0, out0), (in1, out1) = edges[i], edges[i + 1]
                points = arc(r1, out0, out1) + arc(r0, in1, in0)
                regions.append({"word": word, "core": core, "ring": ring, "points": points})
        regions.append({"word": core, "core": core, "ring": 0,
                        "points": arc(RADII[1], *core_edges) + [point(0, 0)]})
    return regions


def preview(regions):
    from PIL import ImageDraw
    img = IMAGE.copy()
    draw = ImageDraw.Draw(img)
    for r in regions:
        draw.polygon([tuple(p) for p in r["points"]], outline=(0, 0, 0))
        cx = sum(p[0] for p in r["points"]) / len(r["points"])
        cy = sum(p[1] for p in r["points"]) / len(r["points"])
        draw.text((cx - 20, cy - 5), r["word"][:9], fill=(0, 0, 0))
    img.save("/tmp/preview.png")


if __name__ == "__main__":
    regions = build()
    with open(os.path.join(HERE, "regions.js"), "w") as f:
        f.write("// Generated by make_regions.py -- do not edit by hand.\n")
        f.write("const REGIONS = " + json.dumps(regions, separators=(",", ":")) + ";\n")
    print(f"wrote {len(regions)} regions")
    if "--preview" in sys.argv:
        preview(regions)
        print("wrote /tmp/preview.png")
