#!/usr/bin/env python3
"""Procedural timber quay.

Tiling a generated deck sprite along the shore piles overlapping slabs into a
jumbled staircase — the deck has to be one continuous surface that follows the
waterline exactly, so it is drawn rather than stamped. Planks run along the
isometric axis and the front edge gets a fascia board so the deck reads as
standing on the water rather than painted onto it.
"""
import math
from PIL import Image, ImageDraw

PLANK   = [(122, 88, 56), (134, 98, 62), (146, 108, 70), (158, 118, 78), (168, 128, 86)]
JOINT   = (92, 66, 42)
FASCIA  = (104, 74, 46)
POSTTOP = (150, 112, 72)
POSTSID = (108, 78, 50)


def _hash(i, j, seed=7):
    return (i*73856093 ^ j*19349663 ^ seed*83492791) & 0xFFFF


def deck_strip(canvas, pts, depth, seed=3, plank_w=13):
    """Lay a deck between an upper edge polyline `pts` and `depth` px below it."""
    d = ImageDraw.Draw(canvas, "RGBA")
    if len(pts) < 2: return
    # deck surface
    poly = list(pts) + [(x, y+depth) for x, y in reversed(pts)]
    d.polygon(poly, fill=PLANK[2])
    # planks running with the shore, shaded per board
    xs = [p[0] for p in pts]
    x0, x1 = min(xs), max(xs)
    def top_at(x):
        for i in range(len(pts)-1):
            a, b = pts[i], pts[i+1]
            if a[0] <= x <= b[0] and b[0] != a[0]:
                t = (x-a[0])/(b[0]-a[0]); return a[1] + (b[1]-a[1])*t
        return pts[0][1] if x < pts[0][0] else pts[-1][1]
    n = max(3, depth//plank_w)
    for k in range(n):
        f0 = k/n; f1 = (k+1)/n
        for x in range(int(x0), int(x1)):
            t = top_at(x)
            # tone varies per board AND along its length, so the deck reads as
            # laid timber rather than one smooth ramp
            c = PLANK[(_hash(k, x//26, seed) + k) % len(PLANK)]
            d.line([(x, t+depth*f0), (x, t+depth*f1-2)], fill=c)
            d.point((x, t+depth*f1-1), fill=JOINT)
    # butt joints between board ends
    for x in range(int(x0), int(x1), 34):
        t = top_at(x)
        jx = x + (_hash(x//34, 3, seed) % 12)
        d.line([(jx, t+2), (jx, t+depth-2)], fill=JOINT)
    # front fascia — a constant lip so the deck has thickness above the water;
    # following the shore drop turned it into a wall at the wharf's low end
    for x in range(int(x0), int(x1)):
        t = top_at(x)+depth
        d.line([(x, t), (x, t+8)], fill=FASCIA)
    d.line([(x0, top_at(x0)), (x1, top_at(x1))], fill=JOINT)


def posts(canvas, pts, depth, step=64, height=26, seed=5):
    d = ImageDraw.Draw(canvas, "RGBA")
    xs = [p[0] for p in pts]
    x0, x1 = min(xs), max(xs)
    def top_at(x):
        for i in range(len(pts)-1):
            a, b = pts[i], pts[i+1]
            if a[0] <= x <= b[0] and b[0] != a[0]:
                t = (x-a[0])/(b[0]-a[0]); return a[1] + (b[1]-a[1])*t
        return pts[0][1] if x < pts[0][0] else pts[-1][1]
    for x in range(int(x0)+18, int(x1), step):
        y = top_at(x)+depth+8
        w = 9
        d.rectangle([x-w, y, x+w, y+height], fill=POSTSID)
        d.ellipse([x-w, y-5, x+w, y+5], fill=POSTTOP)


def jetty(canvas, x, y, length, width=54, angle=0.0, seed=11):
    """A finger pier walking out into the water at the iso angle."""
    d = ImageDraw.Draw(canvas, "RGBA")
    dx = math.sin(angle); dy = math.cos(angle)
    for s in range(length):
        px = x + dx*s; py = y + dy*s*0.86
        for i in range(int(-width/2), int(width/2)):
            c = PLANK[(_hash(int(s)//9, (i+64)//11, seed)) % len(PLANK)]
            d.point((px+i, py), fill=c)
        if s % 9 == 8:
            d.line([(px-width/2, py), (px+width/2, py)], fill=JOINT)
        d.point((px-width/2, py), fill=JOINT); d.point((px+width/2, py), fill=JOINT)
    # side fascia + posts
    for s in range(0, length, 46):
        px = x + dx*s; py = y + dy*s*0.86
        for sx in (-width/2, width/2):
            d.rectangle([px+sx-6, py, px+sx+6, py+30], fill=POSTSID)
            d.ellipse([px+sx-6, py-4, px+sx+6, py+4], fill=POSTTOP)
    px = x + dx*length; py = y + dy*length*0.86
    d.line([(px-width/2, py), (px+width/2, py)], fill=JOINT)
