#!/usr/bin/env python3
"""
UNIFIED ISLAND compositor — Harvestholm (village, N) + Lantern Quay (harbor, S),
one road, crossroads mailbox at the midpoint, offshore lane isles.

Merges the PROVEN recipes of world-reimagine/compose_d1.py (village kit) and
compose_d2.py (harbor kit). Round-1 gate fixes baked in:
  * palette_coherence: NEUTRAL DAY — zero global tint/gradient/vignette/glow
    passes (round-0 foreign mass was tinted native colors). Every pixel comes
    from LimeZu sheets; tiny drawn accents reuse sheet-native hues.
  * clustering: props in purposeful clusters + connective paths; meadow/road/
    water keep real negative space; three-pass ground painting everywhere,
    water textured with sheet-sampled wave dashes (no flat voids).

Outputs (scratchpad only):
  unified-world.png  1920x1280  (60x40 tiles @2x, whole island)
  unified-close.png  1584x1200  (@3x crop centered on the crossroads)
  unified-world.map.json / unified-world.labels.json (map/v1 + labels/v1)

Deterministic: fnv1a-seeded LCG only. No random/time/network. Repo read-only.
"""
import json
import sys
from PIL import Image, ImageDraw, ImageFilter

# In-repo landing (WORLD-V1A T1): asset + output paths are repo-relative --
# this file lives at cabinet/scripts/world-compose/world-unified/.
from pathlib import Path as _Path
_REPO = _Path(__file__).resolve().parents[4]
A   = str(_REPO / "cabinet" / "dashboard" / "public" / "world-assets")
SF  = A + "/staged-future/farm"
SG  = SF + "/Single_Files_16x16"
ST  = A + "/exteriors/street"
OUT = str(_Path(__file__).resolve().parent)
T = 16

# ---------------------------------------------------------------- io
_cache = {}
def sh(path):
    if path not in _cache:
        _cache[path] = Image.open(path).convert("RGBA")
    return _cache[path]

TER  = A + "/farm/1_Terrains_16x16.png"
PROP = A + "/farm/3_Props_and_Buildings_16x16.png"
TREE = SF + "/6_Trees_16x16.png"
COMP = SF + "/0_Complete_Tileset_16x16.png"
LIB  = A + "/interiors/5_Classroom_and_library_16x16.png"
MAIL = A + "/exteriors/ME_Singles_City_Props_16x16_Mailbox_1.png"
BLUE = A + "/exteriors/22_Post_Office_16x16_Big_Blue_Mailbox.png"
SMOK = SF + "/Animated_16x16/Animated_sheets_16x16/Stone_Oven_Smoke_16x16.png"
COW  = SF + "/Animals_16x16/Cows/Cow_16x16.png"
CHB  = SF + "/Animals_16x16/Chickens_and_Roosters/Chicken_Brown_16x16.png"
CHW  = SF + "/Animals_16x16/Chickens_and_Roosters/Chicken_White_16x16.png"
DOG  = SF + "/Animals_16x16/Dogs/Dog_Labrador_Brown_16x16.png"
DUCK = SF + "/Animals_16x16/Ducks/Duck_White_16x16.png"
DUCB = SF + "/Animals_16x16/Ducks/Duck_Brown_16x16.png"
FEN  = SF + "/2_Fences_16x16.png"
CROPD= SF + "/Crops_Growth_16x16/"

def P(name):  return SG + "/Props_and_Buildings_16x16/" + name + "_16x16.png"
def FE(name): return SG + "/Fences_16x16/" + name + "_16x16.png"
def CS(name): return SG + "/0_Complete_Tileset_Singles_16x16/" + name + ".png"
def FR(name): return SG + "/Fruit_Trees_16x16/" + name + "_16x16.png"
def SL(name): return ST + "/" + name + ".png"

def cut(path, tx, ty, tw=1, th=1):
    return sh(path).crop((tx*T, ty*T, (tx+tw)*T, (ty+th)*T))
def trim(im):
    b = im.getbbox()
    return im.crop(b) if b else im

# street singles (proven in d2)
SW1  = SL("ME_Singles_City_Terrains_16x16_Sidewalk_1_1")
SW2  = SL("ME_Singles_City_Terrains_16x16_Sidewalk_1_2")
LAMP = SL("ME_Singles_City_Props_16x16_Street_Lamp_2")
BENCH= SL("ME_Singles_City_Props_16x16_Bench_1")
BOAT = SL("ME_Singles_Vehicles_16x16_Boat_1_Down_1")
GCONDO = SL("ME_Singles_Floor_Modular_Building_16x16_Ground_Floor_Condo_1")
ROOF2  = SL("ME_Singles_Floor_Modular_Building_16x16_Roof_2")

def crop_w(im, w_px):
    """Left-crop a modular piece to w_px, re-appending its right border strip
    so the trim survives (LimeZu modular pieces tile horizontally)."""
    strip = im.crop((im.width - 4, 0, im.width, im.height))
    out = im.crop((0, 0, w_px - 4, im.height)).copy()
    cv = Image.new("RGBA", (w_px, im.height), (0, 0, 0, 0))
    cv.alpha_composite(out, (0, 0))
    cv.alpha_composite(strip, (w_px - 4, 0))
    return cv

# ---------------------------------------------------------------- determinism
def fnv1a(s):
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch); h = (h * 16777619) & 0xFFFFFFFF
    return h
class LCG:
    def __init__(self, seed): self.s = fnv1a(seed) or 1
    def n(self):
        self.s = (self.s * 1664525 + 1_013_904_223) & 0xFFFFFFFF
        return self.s
    def rf(self): return self.n() / 0xFFFFFFFF
    def ri(self, a, b): return a + self.n() % (b - a + 1)
    def pick(self, seq): return seq[self.n() % len(seq)]

# ---------------------------------------------------------------- autotile (d1, verified)
def blobset(bx, by, ibx, iby, fillers):
    return {"NW":(bx,by),"N":(bx+1,by),"NE":(bx+2,by),
            "W":(bx,by+1),"C":(bx+1,by+1),"E":(bx+2,by+1),
            "SW":(bx,by+2),"S":(bx+1,by+2),"SE":(bx+2,by+2),
            "nSE":(ibx,iby),"nSW":(ibx+1,iby),"nNE":(ibx,iby+1),"nNW":(ibx+1,iby+1),
            "fill":fillers}
TAN   = blobset(0, 0,  3, 0,  [(5,0),(5,1),(5,2)])
SOIL  = blobset(0, 8,  3, 8,  [])
MULCH = blobset(0, 12, 3, 12, [])

def autotile(cells, bs, fillp=0.3):
    out = []
    rng = LCG("fill-jitter")
    def m(x, y): return (x, y) in cells
    for (x, y) in sorted(cells):
        n,s,w,e = m(x,y-1), m(x,y+1), m(x-1,y), m(x+1,y)
        nw,ne,sw,se = m(x-1,y-1), m(x+1,y-1), m(x-1,y+1), m(x+1,y+1)
        if   not n and not w: k = "NW"
        elif not n and not e: k = "NE"
        elif not s and not w: k = "SW"
        elif not s and not e: k = "SE"
        elif not n: k = "N"
        elif not s: k = "S"
        elif not w: k = "W"
        elif not e: k = "E"
        elif not nw: k = "nNW"
        elif not ne: k = "nNE"
        elif not sw: k = "nSW"
        elif not se: k = "nSE"
        else:
            out.append((x, y, bs["fill"][rng.n() % len(bs["fill"])] if (bs["fill"] and rng.rf() < fillp) else bs["C"]))
            continue
        out.append((x, y, bs[k]))
    return out

def carve_path(waypoints, wobble=True):
    cells = set()
    def stamp(x, y):
        for dx in (0, 1):
            for dy in (0, 1):
                cells.add((x+dx, y+dy))
    x, y = waypoints[0]
    stamp(x, y)
    for (qx, qy) in waypoints[1:]:
        while (x, y) != (qx, qy):
            if x != qx and (y == qy or ((x*7 + y*3) % 5 < 3 if wobble else True)):
                x += 1 if qx > x else -1
            elif y != qy:
                y += 1 if qy > y else -1
            stamp(x, y)
    return cells

def rect(x0, y0, x1, y1):
    return {(x, y) for x in range(x0, x1+1) for y in range(y0, y1+1)}

# blob painter for 3x3 modules (d2, verified)
def paint_blob(cv, cells, mod_tl):
    mod = cut(TER, mod_tl[0], mod_tl[1], 3, 3)
    Pc = {(cx, cy): mod.crop((cx*T, cy*T, cx*T+T, cy*T+T)) for cx in range(3) for cy in range(3)}
    for (x, y) in cells:
        n = (x, y-1) in cells; s_ = (x, y+1) in cells
        w = (x-1, y) in cells; e = (x+1, y) in cells
        cx = 1 if (w and e) else (0 if e else (2 if w else 1))
        cy = 1 if (n and s_) else (0 if s_ else (2 if n else 1))
        cv.alpha_composite(Pc[(cx, cy)], (x*T, y*T))
MOD_FOAM = (8, 4)     # sand blob in water w/ foam rim
MOD_SANDG= (0, 4)     # sand blob on grass

# terrain shorthands
GRASS   = (TER, 3, 2)
GVAR    = (TER, 8, 8)
GRASS_V = [(COMP, 8, 13), (COMP, 10, 13), (COMP, 10, 17), (COMP, 8, 17)]
WATER_P = (TER, 17, 1)     # pure flat-blue water (pond-module heart)
POND_MOD= (16, 0)          # 3x3 pond module TL — wave hues sampled from its rim
SAND_P  = [(TER, 19, 7), (TER, 20, 7), (TER, 21, 7), (TER, 22, 7)]
PLANK   = (TER, 1, 9)
def tile(spec): return cut(spec[0], spec[1], spec[2])

# ---------------------------------------------------------------- characters (d1, verified)
CDIR = {"right":0, "up":1, "left":2, "down":3}
def cpath(n): return A + "/characters/Premade_Character_%02d.png" % n
def cframe(n, row, d, i=0):
    x = (CDIR[d]*6 + i) * T
    return sh(cpath(n)).crop((x, row, x+T, row+32))
def c_idle(n,d,i=0): return cframe(n, 32, d, i)
def c_walk(n,d,i=0): return cframe(n, 64, d, i)
SIT2_DIR = {"down":0, "up":1}
def c_read(n,d,i=1):
    x = (SIT2_DIR[d]*6 + i) * T
    return sh(cpath(n)).crop((x, 224, x+T, 256))

def cow_f(kind, i, d=0):
    r = {"idle":48, "graze":96, "walk":144}[kind]
    x = (d*6 + i) * 48
    return sh(COW).crop((x, r, x+48, r+48))
def chick(kind, i=0, white=False):
    r = {"idle":16, "walk":32, "peck":48}[kind]
    p = CHW if white else CHB
    return sh(p).crop((i*T, r, (i+1)*T, r+T))
def dog_sleep(i=0):
    return sh(DOG).crop((i*48, 384, (i+1)*48, 416))
def duck_frame(i, brown=False):
    return sh(DUCB if brown else DUCK).crop((16*i, 112, 16*i+16, 128))

TREECUTS = {"oakS":(0,4,3,5), "oakM":(4,3,4,6), "oakL":(8,2,5,7),
            "oakXL":(13,0,7,9), "pineS":(20,3,3,5), "pineM":(25,3,4,5)}
def tree(kind):
    tx, ty, tw, th = TREECUTS[kind]
    return trim(cut(TREE, tx, ty, tw, th))

def crop_stage(species, i):
    im = sh(CROPD + species + "_Growth_Stages_16x16.png")
    ph = 16 if im.height <= 48 else 32
    fr = im.crop((i*T, 0, (i+1)*T, ph))
    return trim(fr) if fr.getbbox() else fr

def plotbed(w, h):
    names = {(0,0):"Upper_Left",(1,0):"Upper_Middle",(2,0):"Upper_Right",
             (0,1):"Middle_Left",(1,1):"Middle_Central",(2,1):"Middle_Right",
             (0,2):"Bottom_Left",(1,2):"Bottom_Middle",(2,2):"Bottom_Right"}
    im = Image.new("RGBA", (w*T, h*T), (0,0,0,0))
    for y in range(h):
        for x in range(w):
            kx = 0 if x == 0 else (2 if x == w-1 else 1)
            ky = 0 if y == 0 else (2 if y == h-1 else 1)
            im.alpha_composite(sh(FE("Topsoil_Arable_Big_Modular_" + names[(kx,ky)])), (x*T, y*T))
    return im

def mailbox(flag_up=True, pips=2):
    """THE Captain surface (16x32 city mailbox). flag_up = pending>0;
    envelope pips (<=5) in the slot band."""
    m = sh(MAIL).copy()
    d = ImageDraw.Draw(m)
    if flag_up:
        d.rectangle([13, 4, 14, 13], fill=(198, 50, 40, 255))     # pole
        d.rectangle([9, 4, 14, 8],   fill=(226, 70, 54, 255))     # flag
        d.point((10, 5), fill=(255, 130, 108, 255))               # glint
        for i in range(min(pips, 5)):                             # envelope pips
            x0 = 4 + i*4
            d.rectangle([x0, 17, x0+2, 18], fill=(242, 236, 222, 255))
            d.point((x0+1, 17), fill=(96, 66, 42, 255))
    return m

def noticeboard():
    board = trim(cut(LIB, 13, 3, 3, 2)).copy()
    bd = ImageDraw.Draw(board)
    pin_cols = [(226, 84, 68), (250, 208, 120), (120, 200, 140), (140, 170, 250)]
    brng = LCG("xr-pins")
    for _ in range(8):
        px_ = 5 + brng.ri(0, 32); py_ = 4 + brng.ri(0, 9)
        c = pin_cols[brng.ri(0, 3)]
        bd.rectangle([px_, py_, px_+1, py_+1], fill=c + (255,))
    im = Image.new("RGBA", (board.width, board.height + 6), (0,0,0,0))
    d = ImageDraw.Draw(im)
    for lx in (4, board.width - 7):
        d.rectangle([lx, board.height - 3, lx + 2, board.height + 5], fill=(96, 66, 42, 255))
    im.alpha_composite(board, (0, 0))
    return im

def build_stack(parts):
    w = max(p.width for p in parts)
    h = sum(p.height for p in parts)
    cv = Image.new("RGBA", (w, h), (0,0,0,0))
    y = 0
    for p in parts:
        cv.alpha_composite(p, ((w - p.width)//2, y))
        y += p.height
    return cv

def build_lighthouse(body_t=7, H_t=11):
    """Silo BODY (dome cropped off) + drawn DARK lamp head on boulders.
    The unlit lamp is the summit — cells_graduated=0, never pre-lit."""
    silo = sh(P("Silos_2"))
    dome_px = 56                      # silver dome rows of Silos_2 (5x14t sprite)
    body = silo.crop((0, dome_px, silo.width, dome_px + body_t*T))
    W, H = 6*T, H_t*T
    cv = Image.new("RGBA", (W, H), (0,0,0,0))
    rb = sh(P("Rock_Big")); rm = sh(P("Rock_Medium")); rs = sh(P("Rock_Small"))
    cv.alpha_composite(rb, (0, H - rb.height))
    cv.alpha_composite(rb, (W - rb.width - 2, H - rb.height + 2))
    cv.alpha_composite(rm, (W//2 - rm.width//2 + 6, H - rm.height))
    cv.alpha_composite(rs, (W//2 - 24, H - rs.height - 2))
    bx = (W - body.width)//2
    by = H - 2*T - body.height + 6
    cv.alpha_composite(body, (bx, by))
    d = ImageDraw.Draw(cv)
    d.rectangle([bx + 10, by + 22, bx + body.width - 11, by + 23], fill=(52, 48, 62, 255))
    lx = W//2
    d.rectangle([lx-5, by - 12, lx+4, by - 2], fill=(38, 40, 54, 255), outline=(20, 22, 32, 255))
    d.rectangle([lx-3, by - 10, lx+2, by - 4], fill=(30, 36, 52, 255))
    d.point((lx-3, by - 9), fill=(58, 68, 92, 255))
    d.rectangle([lx-6, by - 2, lx+5, by - 1], fill=(30, 30, 42, 255))
    d.rectangle([lx-1, by - 15, lx, by - 12], fill=(24, 26, 36, 255))
    return cv

def berth_stack3(stage, seed):
    """Round-2 cargo pile: 3-tile footprint, pieces TOUCHING (designed clumping).
    Stage 1..7 accumulation grammar — crates/sacks/barrels/timber, no invented
    pixels. Reads as a working berth, not a chalk outline."""
    rng = LCG(seed)
    Wp, Hp = 3*T + 8, 3*T + 10
    cv = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 0))
    def put(sp, x, y):
        cv.alpha_composite(sp, (int(x), int(y)))
    crate = sh(P("Crate_Brown_Empty"));  crated = sh(P("Crate_Dark_Brown_Empty"))
    sack1 = sh(P("Sack_Jute_Load_1"));   sack2  = sh(P("Sack_Jute_Load_2"))
    boxl  = sh(P("Box_Load"));           boxs   = sh(P("Box_Single"))
    wood  = sh(P("Wood_Board_Load"))
    b2 = cut(PROP, 24, 6, 2, 2); bl = cut(PROP, 26, 6, 2, 2); bt = cut(PROP, 24, 4, 1, 2)
    j = rng.ri(-2, 2)
    # back row (drawn first)
    if stage >= 5: put(wood, Wp - wood.width - 2 + j, Hp - wood.height - 14)
    if stage >= 3: put(b2, 0, Hp - b2.height - 12)
    if stage >= 6: put(bt, Wp - bt.width - 26, Hp - bt.height - 16)
    if stage >= 7: put(bl, 16, Hp - bl.height - 22)
    # mid row
    if stage >= 4: put(crated, 22 + j, Hp - crated.height - 6)
    if stage >= 3: put(boxl, Wp - boxl.width - 4, Hp - boxl.height - 4)
    # front row (touching)
    if stage >= 2:
        put(crate, 2, Hp - crate.height)
        put(sack1, crate.width - 4, Hp - sack1.height + 2)
    if stage >= 6: put(crate, 6, Hp - crate.height - 12)      # second layer
    if stage >= 7: put(sack2, Wp - sack2.width - 2, Hp - sack2.height)
    if stage == 1: put(boxs, 14, Hp - boxs.height - 2)
    return cv

def berth_stack(stage, seed):
    """Cargo pile recipes 1..7 on a tight 2-tile footprint (d2, verified)."""
    W, H = 2*T + 2, 3*T
    cv = Image.new("RGBA", (W, H), (0,0,0,0))
    def put(sp, x, y):
        cv.alpha_composite(sp, (x, y))
    crate = sh(P("Crate_Brown_Empty"))
    sack1 = sh(P("Sack_Jute_Load_1")); sack2 = sh(P("Sack_Jute_Load_2"))
    boxl = sh(P("Box_Load")); boxs = sh(P("Box_Single"))
    b2 = cut(PROP, 24, 6, 2, 2); bl = cut(PROP, 26, 6, 2, 2); bt = cut(PROP, 24, 4, 1, 2)
    if stage >= 6: put(b2, 1, H - b2.height - 18)
    if stage >= 7: put(bl, 2, H - bl.height - 24)
    if stage >= 4: put(boxl, 2, H - boxl.height - 8)
    if stage >= 5: put(bt, W - bt.width - 2, H - bt.height - 10)
    if stage >= 2: put(crate, 0, H - crate.height)
    if stage >= 3: put(sack1, W - sack1.width, H - sack1.height + 2)
    if stage >= 7: put(sack2, W - sack2.width - 6, H - sack2.height)
    if stage == 1: put(boxs, 8, H - boxs.height - 2)
    return cv

# ---------------------------------------------------------------- thought chip
FONT = {"A":["010","101","111","101","101"],"B":["110","101","110","101","110"],
"C":["011","100","100","100","011"],"D":["110","101","101","101","110"],
"E":["111","100","110","100","111"],"H":["101","101","111","101","101"],
"I":["111","010","010","010","111"],"L":["100","100","100","100","111"],
"O":["010","101","101","101","010"],"P":["110","101","110","100","100"],
"S":["011","100","010","001","110"],"T":["111","010","010","010","010"],
"U":["101","101","101","101","011"],"D2":["110","101","101","101","110"],
"G":["011","100","101","101","011"],"N":["101","111","111","111","101"],
"R":["110","101","110","110","101"],"V":["101","101","101","010","010"],
"W":["101","101","111","111","101"],"K":["101","110","100","110","101"],
"M":["101","111","111","101","101"],"F":["111","100","110","100","100"],
"Y":["101","101","010","010","010"]," ":["000","000","000","000","000"]}
def thought_chip(lines):
    w = max(len(t) for t in lines)*4 + 5
    h = len(lines)*6 + 5
    im = Image.new("RGBA", (w, h + 7), (0,0,0,0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w-1, h-1], radius=2, fill=(242, 236, 222, 244),
                        outline=(96, 66, 42, 255))
    for li, text in enumerate(lines):
        x = 3
        for ch in text:
            for gy, row in enumerate(FONT.get(ch, FONT[" "])):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        d.point((x+gx, 3 + li*6 + gy), fill=(64, 46, 30, 255))
            x += 4
    d.ellipse([6, h+1, 9, h+4], fill=(242, 236, 222, 235))
    d.ellipse([3, h+4, 5, h+6], fill=(242, 236, 222, 215))
    return im

# ---------------------------------------------------------------- scene
class Scene:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.ground = Image.new("RGBA", (W*T, H*T), (26, 30, 24, 255))
        self.shadow = Image.new("RGBA", (W*T, H*T), (0, 0, 0, 0))
        self.ents = []
        self.over = []
        self.props = []          # map/v1 prop registry: (name, x, y, w_px, h_px)
    def gpaste(self, im, tx, ty):
        self.ground.alpha_composite(im, (int(tx*T), int(ty*T)))
    def gtiles(self, picks):
        for x, y, (tx, ty) in picks:
            self.ground.alpha_composite(cut(TER, tx, ty), (x*T, y*T))
    def ent(self, im, tx, ty, dx=0, dy=0, bias=0.0, prop=None):
        px = int(tx*T + dx); py = int((ty+1)*T - im.height + dy)
        self.ents.append(((ty + bias)*T + dy, px, py, im))
        if prop:
            self.props.append((prop, int(tx), int(ty), im.width, im.height))
        return px, py
    def shadow_blob(self, cx, foot_y, w, alpha=34, stretch=0):
        h = max(4, int(w*0.30))
        lay = Image.new("RGBA", (w*2 + 16, h*3), (0,0,0,0))
        d = ImageDraw.Draw(lay)
        ox = lay.width//2
        d.ellipse([ox - w//2, h, ox + w//2, h*2], fill=(30, 34, 30, alpha))
        lay = lay.filter(ImageFilter.GaussianBlur(1.4))
        self.shadow.alpha_composite(lay, (int(cx - lay.width//2), int(foot_y - int(h*1.55))))
    def vfx(self, im, px, py):
        self.over.append((im, int(px), int(py)))
    def compose(self):
        cv = self.ground.copy()
        cv.alpha_composite(self.shadow)
        for (k, px, py, im) in sorted(self.ents, key=lambda e: e[0]):
            cv.alpha_composite(im, (int(px), int(py)))
        for (im, px, py) in self.over:
            cv.alpha_composite(im, (int(px), int(py)))
        return cv

def up(im, k): return im.resize((im.width*k, im.height*k), Image.NEAREST)

# ================================================================ THE ISLAND
W, H = 60, 40
ROADX = 28                      # road west column (2 wide: 28,29)
QUAY_Y0, QUAY_Y1 = 27, 31       # quay stone rows (round-2: 5-row working wharf)
SEA_Y = 32                      # first water row

def build_scene():
    sc = Scene(W, H)
    rng = LCG("unified-island-v1")

    # ============ PASS 1: base terrain (three-pass ground painting) ============
    grass = tile(GRASS); gvar = tile(GVAR)
    gv2 = [tile(s) for s in GRASS_V]
    for ty in range(H):
        for tx in range(W):
            sc.gpaste(grass, tx, ty)
    # mid patches: comp-sheet grass variants clustered in soft daubs
    for _ in range(150):
        cx_, cy_ = rng.ri(1, W-2), rng.ri(1, 26)
        v = gv2[rng.ri(0, 3)]
        for _ in range(rng.ri(2, 5)):
            sc.gpaste(v, min(W-1, max(0, cx_ + rng.ri(-2, 2))), min(26, max(0, cy_ + rng.ri(-1, 1))))
    # micro speckle: d1 gvar as a dense per-cell pass (sheet-native leaf specks)
    sp = LCG("speckle-pass")
    for ty in range(0, 27):
        for tx in range(W):
            if sp.rf() < 0.85:
                sc.gpaste(gvar, tx, ty)
    # grass-blade flecks: 1-2px dashes in CONTRASTY sheet-native greens.
    # The base grass tile is near-monochrome, so blade hues come from the
    # comp-sheet grass variants (real blade texture), requiring >=30 sum
    # distance from the base green so each fleck actually breaks a block.
    gpx0 = grass.load()
    gbase = gpx0[T//2, T//2][:3]
    pool = {}
    for v in gv2:
        vp = v.load()
        for yy in range(T):
            for xx in range(T):
                r, g, b, a = vp[xx, yy]
                if a > 128 and g > r and g > b:      # green-family guard
                    pool[(r, g, b)] = pool.get((r, g, b), 0) + 1
    dk = [c for c, n in pool.items() if sum(c) <= sum(gbase) - 30 and n >= 4]
    lt = [c for c, n in pool.items() if sum(c) >= sum(gbase) + 30 and n >= 4]
    if not dk or not lt:                    # canopy greens — still sheet-native
        cnp = tree("oakM").load(); cw, ch = tree("oakM").size
        for yy in range(0, ch, 2):
            for xx in range(0, cw, 2):
                r, g, b, a = cnp[xx, yy]
                if a > 128 and g > r and g > b:
                    c = (r, g, b)
                    if sum(c) <= sum(gbase) - 30: dk.append(c)
                    elif sum(c) >= sum(gbase) + 30: lt.append(c)
    g_dark = min(dk, key=sum); g_lite = max(lt, key=sum)
    print("flecks: base", gbase, "dark", g_dark, "lite", g_lite)
    gd0 = ImageDraw.Draw(sc.ground)
    fl = LCG("grass-flecks")
    for ty in range(0, 27):
        for tx in range(W):
            for _ in range(fl.ri(4, 7)):
                fx2 = tx*T + fl.ri(0, T-2); fy2 = ty*T + fl.ri(0, T-3)
                col = g_dark if fl.rf() < 0.62 else g_lite
                gd0.rectangle([fx2, fy2, fx2, fy2 + fl.ri(1, 2)],
                              fill=col + (255,))

    # ============ sea (rows SEA_Y..H-1) ============
    wp = tile(WATER_P)
    for ty in range(SEA_Y, H):
        for tx in range(W):
            sc.ground.paste(wp, (tx*T, ty*T))
    # sheet-native wave accents: hues sampled from the pond module's own
    # water body + navy rim (never invented colors)
    pond = cut(TER, POND_MOD[0], POND_MOD[1], 3, 3)
    ppx = pond.load()
    cols = {}
    for yy in range(3*T):
        for xx in range(3*T):
            r, g, b, a = ppx[xx, yy]
            if a > 128 and b > r + 20:            # blue-hue guard: water colors only
                cols[(r, g, b)] = cols.get((r, g, b), 0) + 1
    ranked = sorted(cols.items(), key=lambda kv: -kv[1])
    base_rgb = ranked[0][0]
    lighter = [c for c, n in ranked if sum(c) > sum(base_rgb) + 30 and n > 8]
    darker  = [c for c, n in ranked if sum(c) < sum(base_rgb) - 30 and n > 8]
    wave_l = lighter[0] if lighter else (232, 240, 248)
    wave_d = darker[0] if darker else (52, 90, 172)
    gd = ImageDraw.Draw(sc.ground)
    wrng = LCG("waves")
    for ty in range(SEA_Y, H):
        for tx in range(W):
            n_d = 8 + (wrng.n() % 5)              # dense: no flat 8px block voids
            for _ in range(n_d):
                wx = tx*T + wrng.ri(0, T-7); wy = ty*T + wrng.ri(1, T-2)
                ln = wrng.ri(3, 6)
                roll = wrng.rf()
                col = wave_d if roll < 0.5 else (wave_l if roll < 0.86
                                                 else (226, 236, 246))
                gd.rectangle([wx, wy, wx+ln, wy], fill=col + (255,))
            for _ in range(3):                    # 1px ripple ticks between
                wx = tx*T + wrng.ri(0, T-2); wy = ty*T + wrng.ri(0, T-1)
                gd.point((wx, wy), fill=wave_d + (255,))
                gd.point((wx+1, wy), fill=wave_l + (255,))
    # long broken SWELL lines across the open sea (corpus-style wave streaks)
    srng = LCG("swell")
    for ty in range(SEA_Y, H):
        y_px = ty*T + srng.ri(3, 12)
        n_seg = 5 + srng.n() % 4
        for _ in range(n_seg):
            sx = srng.ri(0, W*T - 20); sl = srng.ri(6, 16)
            a = 96 + srng.ri(0, 40)
            y_j = y_px + srng.ri(-2, 2)
            gd.rectangle([sx, y_j, sx + sl, y_j], fill=(226, 236, 246, a))

    # ============ offshore lane isles (foam-rimmed sand blobs + grass tops) =====
    def isle(x0, y0, x1, y1, seed):
        cells = rect(x0, y0, x1, y1)
        irng = LCG(seed)
        for x in range(x0, x1+1):
            if irng.rf() < 0.5: cells.discard((x, y0))
            if irng.rf() < 0.5: cells.discard((x, y1))
        paint_blob(sc.ground, cells, MOD_FOAM)
        # grass heart
        heart = rect(x0+1, y0+1, x1-1, y1-1)
        for (hx, hy) in sorted(heart):
            if (hx, hy) in cells:
                sc.gpaste(grass, hx, hy)
        for (hx, hy) in sorted(heart):
            if (hx, hy) in cells and irng.rf() < 0.5:
                sc.gpaste(gv2[irng.ri(0, 3)], hx, hy)
        return cells
    # acme isle SW / widgets isle SE (widgets bigger: more shipped there)
    isle_s = isle(3, 36, 9, 39, "isle-acme")
    isle_p = isle(39, 36, 47, 39, "isle-widgets")

    # ============ rocky headland SW shore (palette-native: grass + rocks + foam) ==
    # grass runs to the waterline; foam scallops + boulders instead of foreign sand
    hd = ImageDraw.Draw(sc.ground)
    hrng = LCG("headland")
    for tx in range(2, 8):
        for ty in (27, 28, 29, 30, 31):
            sc.gpaste(grass, tx, ty)
            if hrng.rf() < 0.7:
                sc.gpaste(gvar, tx, ty)
    for tx in range(2, 8):
        sc.ground.paste(wp, (tx*T, 32*T))
        # white foam scallops on the waterline (native highlight family)
        fy0 = 32*T + 1 + hrng.ri(0, 2)
        hd.rectangle([tx*T + hrng.ri(0, 3), fy0, tx*T + 9 + hrng.ri(0, 5), fy0],
                     fill=(232, 240, 248, 215))
        if hrng.rf() < 0.5:
            hd.rectangle([tx*T + hrng.ri(2, 6), fy0 + 3, tx*T + 6 + hrng.ri(2, 7), fy0 + 3],
                         fill=(226, 236, 246, 150))

    # ============ quay stone (rows 28..30, x10..54) ============
    sw1 = sh(SW1).crop((0, 0, T, T)); sw2 = sh(SW2).crop((0, 0, T, T))
    # plain wharf pavement all three rows (no curb tile — that reads "street";
    # the water edge is a drawn stone lip + wall shadow + foam instead)
    for ty in range(QUAY_Y0, QUAY_Y1+1):
        for tx in range(8, 56):
            sc.ground.paste(sw1, (tx*T, ty*T))
    # quay wear: dark joint seams (sampled from the sidewalk tile itself) + weeds
    jrng = LCG("quay-joints")
    swpx = sw1.load()
    dark = min(((swpx[xx, yy][0], swpx[xx, yy][1], swpx[xx, yy][2])
                for yy in range(T) for xx in range(T)), key=sum)
    swpx2 = sw2.load()   # curb tile carries the bright stone — sample lite there
    lite = max(((swpx2[xx, yy][0], swpx2[xx, yy][1], swpx2[xx, yy][2])
                for yy in range(T) for xx in range(T)), key=sum)
    for tx in range(8, 56):
        if jrng.rf() < 0.95:
            jx = tx*T + jrng.ri(2, 13)
            jy0 = QUAY_Y0*T + jrng.ri(0, 8)
            gd.rectangle([jx, jy0, jx, min(jy0 + jrng.ri(6, 16), QUAY_Y1*T + 14)],
                         fill=dark + (255,))
        if jrng.rf() < 0.9:
            jy = QUAY_Y0*T + jrng.ri(4, 40)
            jx0 = tx*T + jrng.ri(0, 6)
            gd.rectangle([jx0, jy, jx0 + jrng.ri(5, 12), jy], fill=dark + (255,))
        # stone flecks per tile per row (sampled dark + light — native;
        # single-pixel chips so the wharf reads weathered, not gritty)
        for ty in range(QUAY_Y0, QUAY_Y1+1):
            for _ in range(jrng.ri(3, 5)):
                fx2 = tx*T + jrng.ri(0, T-2); fy2 = ty*T + jrng.ri(0, T-2)
                if jrng.rf() < 0.6:
                    gd.point((fx2, fy2), fill=dark + (255,))
                    gd.point((fx2+1, fy2), fill=dark + (255,))
                else:
                    gd.point((fx2, fy2), fill=lite + (255,))
        if jrng.rf() < 0.30:
            sc.gpaste(sh(CS("Grass_Tufts_Flowers_16x16_%d" % jrng.ri(1, 11))),
                      tx, QUAY_Y0 + (jrng.ri(0, 1))*4)
    # wharf-edge stone lip (sampled sidewalk dark) + wall shadow + tide foam
    gd.rectangle([8*T, QUAY_Y1*T + 14, 56*T-1, QUAY_Y1*T + 15], fill=dark + (255,))
    gd.rectangle([8*T, SEA_Y*T, 56*T-1, SEA_Y*T+2], fill=(38, 52, 72, 160))
    frng = LCG("tide")
    for _ in range(80):
        fx = frng.ri(8*T, 55*T); fl = frng.ri(2, 6)
        fy = SEA_Y*T + 3 + frng.ri(0, 6)
        gd.rectangle([fx, fy, fx+fl, fy],
                     fill=(232, 240, 248, 210) if frng.rf() < 0.7
                     else (226, 236, 246, 150))

    # ============ village terraces hint: mulch orchard NE + tan plaza ============
    orch = rect(44, 2, 54, 7)
    org = LCG("orch-edge")
    for x in range(44, 55):
        if org.rf() < 0.55: orch.discard((x, 7))
        if org.rf() < 0.35: orch.discard((x, 2))
    for y in range(2, 8):
        if org.rf() < 0.5: orch.discard((44, y))
    sc.gtiles(autotile(orch, MULCH))

    # plaza + paths + THE ROAD (village plaza -> crossroads -> quay mouth)
    plaza = rect(23, 10, 30, 13)
    road  = carve_path([(ROADX, 13), (ROADX, 17), (ROADX, 20), (ROADX, 23), (ROADX, 26)])
    paths = set()
    paths |= carve_path([(20, 11), (23, 11)])                       # great house -> plaza
    paths |= carve_path([(30, 11), (33, 11)])                       # plaza -> library
    paths |= carve_path([(26, 9), (26, 7), (28, 6)])                # plaza -> cottage lane
    paths |= carve_path([(30, 13), (34, 14), (36, 14)])             # plaza -> garden
    paths |= carve_path([(23, 12), (18, 14), (13, 16), (10, 17)])   # plaza -> barn yard
    paths |= carve_path([(44, 11), (47, 10), (49, 9)])              # library -> workshop
    tan = plaza | road | paths
    sc.gtiles(autotile(tan, TAN, fillp=0.75))
    # cobble center strip down the road (t3 wear): sidewalk stones inset
    for (tx, ty) in sorted(road):
        if tx in (ROADX, ROADX+1) and 13 <= ty <= 26 and (tx + ty) % 2 == 0:
            ins = sw2.crop((2, 2, 14, 14))
            sc.ground.alpha_composite(ins, (tx*T+2, ty*T+2))
    # wheel-ruts + kicked pebbles on plaza and road (colors sampled from the
    # tan filler tile itself — native by construction)
    tfill = cut(TER, 5, 1)
    tpx = tfill.load()
    tcols = sorted({tpx[xx, yy][:3] for xx in range(T) for yy in range(T)}, key=sum)
    t_lite = tcols[-1]
    # wear-dark = the soil tile's brown (kicked dirt on the path — native,
    # contrasty against the near-monochrome tan filler)
    spx2 = tile((TER, 1, 9)).load()
    t_dark = min(((spx2[xx, yy][0], spx2[xx, yy][1], spx2[xx, yy][2])
                  for yy in range(T) for xx in range(T)), key=sum)
    trng = LCG("tan-wear")
    tand = ImageDraw.Draw(sc.ground)
    for (tx, ty) in sorted(tan):
        if trng.rf() < 0.85:
            wx = tx*T + trng.ri(1, 11); wy = ty*T + trng.ri(1, 13)
            tand.rectangle([wx, wy, wx + trng.ri(1, 4), wy],
                           fill=(t_dark if trng.rf() < 0.7 else t_lite) + (255,))
        for _ in range(trng.ri(1, 3)):
            wx = tx*T + trng.ri(2, 12); wy = ty*T + trng.ri(2, 12)
            tand.point((wx, wy), fill=t_lite + (255,))
            tand.point((wx + 1, wy), fill=t_dark + (255,))

    # ============ kitchen garden plots (eval + crops story) ============
    bed = plotbed(5, 3)
    for (bx_, by_, species, stage) in [(34, 13, "Cabbage", 4), (40, 13, "Cauliflower", 5)]:
        sc.gpaste(bed, bx_, by_)
        prng = LCG("plot%d" % bx_)
        for row in range(2):
            for col in range(3):
                s = crop_stage(species, min(max(stage + prng.ri(-1, 0), 1), 6))
                sc.ent(s, bx_ + 1 + col, by_ + 1 + row, dx=prng.ri(-1, 2), dy=-3 - row,
                       prop="crop")
    sc.ent(trim(sh(P("Scarecrow"))), 39.2, 13.6, bias=0.2, prop="scarecrow")

    # ============ meadow texture: tufts (terrain decal — NOT props) ============
    verge = rect(24, 18, 34, 24)                     # flower verge at the crossroads
    for _ in range(180):
        tx, ty = rng.ri(2, W-3), rng.ri(3, 26)
        if (tx, ty) in tan or (tx, ty) in orch:
            continue
        sc.gpaste(sh(CS("Grass_Tufts_Flowers_16x16_%d" % rng.ri(1, 11))), tx, ty)
    vr = LCG("verge")
    for (tx, ty) in sorted(verge):
        if (tx, ty) in tan: continue
        if vr.rf() < 0.55:
            sc.gpaste(sh(CS("Grass_Tufts_Flowers_16x16_%d" % vr.ri(1, 11))), tx, ty)
    # hedgerows flanking the mid-island meadow (grass decals in rows;
    # west belt cleared for the smallholder field)
    dgl = cut(PROP, 25, 2, 2, 1); dsl = cut(PROP, 30, 2, 2, 2)
    hedges = [(36, 19), (38, 20), (40, 23), (42, 21), (34, 25), (24, 25),
              (12, 16), (44, 18), (22, 16), (46, 22)]
    for (hx, hy) in hedges:
        sc.gpaste(dgl if (hx + hy) % 3 else dsl, hx + (rng.ri(-1, 1)), hy)

    # ================================================================ BUILDINGS
    # Great House (HQ) on the rise, smoke = chronicle flowing
    house = sh(P("Farmer_House_1"))
    px_, py_ = sc.ent(house, 13, 12, bias=-0.3, prop=None)
    sc.shadow_blob(px_ + house.width//2, 13*T - 5, house.width - 14, 30)
    smf = trim(sh(SMOK).crop((4*48, 0, 5*48, 58))).copy()
    smf.putalpha(smf.split()[3].point(lambda v: int(v*0.80)))
    sc.vfx(smf, px_ + 88 - smf.width//2, py_ + 18 - smf.height)
    # posture pennant on the gable (guardian = 2 tails), sheet-native cream
    pn = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pn)
    pd.rectangle([0, 0, 0, 11], fill=(96, 66, 42, 255))
    pd.polygon([(1, 1), (8, 2), (1, 4)], fill=(242, 236, 222, 255))
    pd.polygon([(1, 5), (8, 6), (1, 8)], fill=(242, 236, 222, 255))
    sc.vfx(pn, px_ + 60, py_ - 2)

    # Memory Library: long-windowed hall (Farmer_House_2) E of plaza
    lib = sh(P("Farmer_House_2"))
    px_, py_ = sc.ent(lib, 33, 11, bias=-0.3, prop=None)
    sc.shadow_blob(px_ + lib.width//2, 12*T - 5, lib.width - 16, 30)
    # journal stacks by the door (books = crates of journals, honest small)
    sc.ent(sh(P("Box_Single")), 34.2, 11.6, prop="prop")
    sc.ent(sh(P("Box_Single")), 35.0, 11.4, dy=-3, prop="prop")

    # Skill Workshop: coop shed + crafting tables + canopy, 9 tool pips
    shop = sh(P("Chicken_Coop"))
    px_, py_ = sc.ent(shop, 46, 9.6, bias=-0.2, prop=None)
    sc.shadow_blob(px_ + shop.width//2, int(10.6*T) - 4, shop.width - 10, 26)
    wb = sh(P("Woodwork_Crafting_Table_Full"))
    sc.ent(wb, 50.5, 9.5, prop="prop")
    dt = sh(P("DIY_Crafting_Table_Full"))
    sc.ent(dt, 50.7, 11.2, prop="prop")
    sc.ent(sh(P("Wood_Board_Load")), 45.0, 10.9, prop="prop")

    # Retro circle / firepit: rock ring + log seats + cold ash (honest: no fire)
    fp_cx, fp_cy = 21.0, 15.0
    ash = Image.new("RGBA", (26, 14), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ash)
    ad.ellipse([0, 0, 25, 13], fill=(88, 84, 92, 235))
    ad.ellipse([5, 3, 19, 10], fill=(64, 60, 70, 255))
    ad.point((9, 6), fill=(120, 116, 124, 255)); ad.point((15, 7), fill=(120, 116, 124, 255))
    sc.ent(ash, fp_cx, fp_cy, prop="firepit")
    for (rx, ry) in [(-1.2, -0.4), (1.3, -0.5), (-1.4, 0.7), (1.5, 0.8), (0.1, -1.0)]:
        sc.ent(sh(P("Rock_Small")), fp_cx + rx, fp_cy + ry + 0.4, prop=None)
    sc.ent(sh(P("Trunk_Big_1")), fp_cx - 1.6, fp_cy + 1.6, prop="prop")
    sc.ent(sh(P("Trunk_Big_2")), fp_cx + 1.2, fp_cy + 1.7, prop="prop")
    # comms-officer writing up the retro at the fire
    px_, py_ = sc.ent(c_read(7, "down", 1), fp_cx + 0.1, fp_cy + 1.5)
    sc.shadow_blob(px_ + 8, int((fp_cy + 2.5)*T) - 2, 12, 40)

    # Law plot NW: fenced rule-posts + veto stones
    def fence_pen(x0, y0, x1, y1, ghost=False):
        for tx in range(x0, x1+1):
            for ty in range(y0, y1+1):
                if x0 < tx < x1 and y0 < ty < y1:
                    continue
                cx = 0 if tx == x0 else (2 if tx == x1 else 1)
                cy = 0 if ty == y0 else (2 if ty == y1 else 1)
                im = cut(FEN, 12+cx, 6+cy)
                if ghost:
                    im = im.copy()
                    gray = im.convert("LA").convert("RGBA")
                    im = Image.blend(im, gray, 0.62)
                    al = im.split()[3].point(lambda v: int(v*0.62))
                    im.putalpha(al)
                sc.ent(im, tx, ty, bias=0.02)
    fence_pen(4, 4, 8, 6)
    sc.ent(sh(P("Sign_1")), 5.0, 5.2, prop="prop")
    sc.ent(sh(P("Sign_2")), 6.6, 5.4, prop="prop")
    sc.ent(sh(P("Rock_Small")), 4.4, 6.6, prop="prop")
    sc.ent(sh(P("Rock_Small")), 7.6, 6.7, prop="prop")

    # ============ SMALLHOLDER BELT: the mid-island meadow is worked land =======
    # (clustering fix: purposeful textured patches + tuft drifts, with the
    #  crossroads clearing and road corridor kept as honest negative space)
    # -- west field: fenced cabbage rows on arable topsoil
    fx0, fy0, fx1, fy1 = 13, 19, 21, 23
    sc.gpaste(plotbed(fx1 - fx0 + 1, fy1 - fy0 + 1), fx0, fy0)
    crng = LCG("westfield")
    for row in range(4):
        for col in range(8):
            if crng.rf() < 0.86:
                st = min(6, max(2, 2 + ((col + 2*row) % 4) + crng.ri(-1, 0)))
                s = crop_stage("Cabbage", st)
                sc.ent(s, fx0 + 0.5 + col, fy0 + 0.55 + row, dx=crng.ri(-1, 2),
                       dy=-2, prop="crop")
    fence_pen(fx0 - 1, fy0 - 1, fx1 + 1, fy1 + 1)
    sc.ent(sh(FE("Wooden_Fence_Type_3_Brown_Gate_1")), fx1 + 1, fy0 + 1, bias=0.03)
    sc.ent(sh(P("Sack_Jute_Load_1")), fx0 - 0.4, fy1 + 1.3, prop="prop")
    # -- east fallow paddock: bare soil strip, half planted with turnips
    pad = rect(36, 21, 41, 22)
    sc.gtiles(autotile(pad, SOIL, fillp=0.5))
    prng2 = LCG("paddock")
    for i in range(6):
        if prng2.rf() < 0.6:
            s = crop_stage("Turnip", 2 + (i % 3))
            sc.ent(s, 36.4 + i, 21.5 + (i % 2)*0.7, dy=-2, prop="crop")
    # -- mulch bare patches (molehills / worn ground) in the open meadow
    for (mx0, my0, mx1, my1) in [(23, 15, 24, 16), (33, 15, 34, 16), (25, 25, 26, 26)]:
        sc.gtiles(autotile(rect(mx0, my0, mx1, my1), MULCH, fillp=0.5))
    # -- tuft/flower drifts: clustered carpets, dense at verges, thin mid-meadow
    def drift(seed, x0, y0, x1, y1, centers, per, rad, p, avoid):
        dr = LCG(seed)
        for _ in range(centers):
            cx_ = dr.ri(x0, x1); cy_ = dr.ri(y0, y1)
            for _ in range(per):
                tx = cx_ + dr.ri(-rad, rad); ty = cy_ + dr.ri(-rad, rad)
                if x0 <= tx <= x1 and y0 <= ty <= y1 and (tx, ty) not in avoid \
                        and dr.rf() < p:
                    sc.gpaste(sh(CS("Grass_Tufts_Flowers_16x16_%d" % dr.ri(1, 11))),
                              tx, ty)
    avoid_belt = tan | pad | rect(fx0 - 1, fy0 - 1, fx1 + 1, fy1 + 1)
    avoid_belt |= {(hx + dx, hy + dy) for (hx, hy) in hedges
                   for dx in (-1, 0, 1, 2) for dy in (0, 1)}
    # east flower verge carpet (between hedgerows and the road)
    drift("drift-east", 31, 17, 45, 25, 30, 9, 2, 0.75, avoid_belt)
    # west meadow between field and road
    drift("drift-west", 22, 15, 27, 26, 16, 8, 2, 0.7, avoid_belt)
    # north meadow bands (village fringe -> crossroads approach)
    drift("drift-fringe", 10, 14, 21, 18, 12, 7, 2, 0.6, avoid_belt)
    drift("drift-mid-n", 22, 14, 35, 17, 18, 8, 2, 0.65, avoid_belt)
    drift("drift-east-n", 36, 14, 46, 17, 14, 8, 2, 0.6, avoid_belt)
    # south meadow + east shore fringes (stop above the working wharf)
    drift("drift-south", 3, 24, 27, 25, 20, 8, 2, 0.6, avoid_belt)
    drift("drift-east-shore", 46, 20, 55, 25, 12, 8, 2, 0.55, avoid_belt)
    # -- headland boulders (SW shore) — clustered with the foam line
    sc.ent(sh(P("Rock_Big")), 3.2, 28.6, prop="prop")
    sc.ent(sh(P("Rock_Medium")), 5.4, 29.3, prop="prop")
    sc.ent(sh(P("Rock_Small")), 4.6, 28.1, prop="prop")
    sc.ent(sh(P("Rock_Medium")), 7.8, 28.8, prop="prop")

    # Cottage lane (4 roles, birth order) N of plaza
    coop = sh(P("Chicken_Coop"))
    for i, cx_ in enumerate([22, 27, 32, 37]):
        px_, py_ = sc.ent(coop, cx_, 4.6 + (i % 2)*0.4, bias=-0.2, prop=None)
        sc.shadow_blob(px_ + coop.width//2, int((5.6 + (i % 2)*0.4)*T) - 4, coop.width - 12, 24)
    sc.ent(sh(P("Dog_Bowl_Red_Full")), 23.2, 5.6, prop="prop")
    sc.ent(sh(P("Hay_Dry_Pile_Small")), 33.6, 5.2, prop="prop")

    # Plaza: well + bench + lamp
    well = sh(P("Well_Usable"))
    px_, py_ = sc.ent(well, 25.4, 11.3, prop="prop")
    sc.shadow_blob(px_ + well.width//2, int(12.3*T) - 6, 40, 30)
    sc.ent(sh(BENCH), 28.6, 10.2, prop="prop")
    sc.ent(sh(LAMP), 24.0, 10.1, dx=-6, prop="prop")

    # Barn + silo + composter W (services + apoptosis)
    barn = sh(P("Barn_Small"))
    px_, py_ = sc.ent(barn, 3, 18.6, bias=-0.3, prop=None)
    sc.shadow_blob(px_ + barn.width//2, int(19.6*T) - 5, barn.width - 14, 30)
    silo = sh(P("Silos_1"))
    px_, py_ = sc.ent(silo, 10.6, 18.6, bias=-0.3, prop=None)
    sc.shadow_blob(px_ + silo.width//2, int(19.6*T) - 5, silo.width - 8, 30)
    # composter: two soil bays + sacks + tarped hand-cart (retired outcome)
    sc.gtiles(autotile(rect(15, 17, 16, 18), SOIL))
    sc.gtiles(autotile(rect(15, 20, 16, 21), SOIL))
    sc.ent(sh(P("Sack_Jute_Load_2")), 15.1, 18.3, prop="prop")
    cart = sh(P("Trunk_Load_Big_Vertical")).copy()
    gray = cart.convert("LA").convert("RGBA")
    cart = Image.blend(cart, gray, 0.55)
    sc.ent(cart, 15.2, 21.2, prop="prop")

    # Pens: cow + chicken, ghost pen (disabled service)
    fence_pen(4, 21, 9, 24)
    fence_pen(10, 21, 15, 24)
    fence_pen(17, 22, 21, 25, True)
    sc.ent(sh(FE("Wooden_Fence_Type_3_Brown_Gate_1")), 6, 24, bias=0.03)
    sc.ent(sh(FE("Wooden_Fence_Type_3_Brown_Gate_1")), 12, 24, bias=0.03)
    sc.ent(sh(P("Cow_Sign")), 3.6, 24.7, prop="prop")
    sc.ent(sh(P("Chicken_Sign")), 9.6, 24.6, prop="prop")
    sc.ent(sh(P("Drinking_Trough_Horizontal_Full")), 5, 21.9, dy=-2, prop="prop")
    sc.ent(sh(P("Hay_Dry_Pile")), 7.6, 21.7, dy=-2, prop="prop")
    henh = sh(P("Henhouse"))
    sc.ent(henh, 12.6, 22.2, bias=-0.05, prop="prop")
    gsign = sh(P("Sign_Blank")).copy()
    al = gsign.split()[3].point(lambda v: int(v*0.6))
    gsign.putalpha(al)
    sc.ent(gsign, 16.6, 25.4, prop="prop")
    for (cx_, cy_, k, i, dd) in [(5.6, 23.2, "graze", 0, 0), (7.8, 22.4, "idle", 2, 0)]:
        c = cow_f(k, i, dd)
        px_, py_ = sc.ent(c, cx_, cy_)
        sc.shadow_blob(px_ + 24, int((cy_+1)*T) - 4, 30, 30)
    for (cx_, cy_, k, wh) in [(11.2, 22.4, "peck", False), (13.6, 23.4, "idle", False),
                              (11.8, 23.8, "walk", True)]:
        c = chick(k, 0, wh)
        sc.ent(c, cx_, cy_, bias=0.06)

    # Orchard trees (org age)
    def fruit(nm, tx, ty):
        im = trim(sh(FR(nm)))
        px2, py2 = sc.ent(im, tx, ty, bias=-0.1, prop=None)
        sc.shadow_blob(px2 + im.width//2, int((ty+1)*T) - 4, im.width - 20, 28)
    fruit("Fruit_Tree_Apple_Ripe_Big", 45, 4.4)
    fruit("Fruit_Tree_Apple_Ripe", 48.4, 3.2)
    fruit("Fruit_Tree_Apple_Ripe_Big", 51.6, 4.9)
    fruit("Fruit_Tree_Apple_Ripe", 47.0, 6.4)
    fruit("Fruit_Tree_Apple_Unripe", 52.8, 3.0)
    sc.ent(sh(FR("Basket_Apple")), 46.4, 5.8, prop="prop")

    # ================================================================ CROSSROADS
    # THE mailbox on the road's W shoulder — clear sightline, nothing occludes
    # the Captain surface; flag UP + 2 envelope pips (pending items story)
    mb = mailbox(True, pips=2)
    px_, py_ = sc.ent(mb, 27.2, 20.6, bias=0.1, prop="prop")
    sc.shadow_blob(px_ + 8, int(21.6*T) - 6, 14, 30)
    nb = noticeboard()
    px_, py_ = sc.ent(nb, 24.6, 19.8, prop="prop")
    sc.shadow_blob(px_ + nb.width//2, int(20.8*T), 40, 28)
    # post-kiosk: shuttered market stand + big blue mailbox (mail organ, honest 0)
    kiosk = sh(P("Market_Stand_Yellow_Small"))
    px_, py_ = sc.ent(kiosk, 31.6, 22.8, prop="prop")
    sc.shadow_blob(px_ + kiosk.width//2, int(23.8*T) - 4, kiosk.width - 8, 26)
    sc.ent(sh(BLUE), 34.4, 22.6, prop="prop")
    lamp2 = sh(LAMP)
    sc.ent(lamp2, 23.6, 22.3, dx=-6, prop="prop")
    # the dog asleep below the noticeboard (charm near, never occluding,
    # the Captain surface)
    dgs = dog_sleep(0)
    px_, py_ = sc.ent(dgs, 24.6, 21.9)
    sc.shadow_blob(px_ + 22, int(22.9*T) - 6, 24, 26)

    # THE COMMUTER: officer walking S toward the quay, thought chip above
    cm = c_walk(4, "down", 1)
    px_, py_ = sc.ent(cm, ROADX + 0.35, 19.4)
    sc.shadow_blob(px_ + 8, int(20.4*T) - 2, 12, 34)
    chip = thought_chip(["I SHOULD", "SHIP THIS"])
    sc.vfx(chip, px_ + 8 - chip.width//2, py_ - chip.height - 2)

    # ================================================================ QUAY SIDE
    # LANTERN QUAY round-2: a WORKING wharf. Street-kit masonry (NOT the
    # village farm kit), lane-grouped cargo mass, lamp rhythm, twin piers,
    # packet dock, stone breakwater + dark lighthouse.

    # --- warehouse (shipped archive) standing ON the wharf, W section
    roof_wh = sh(ROOF2).crop((0, sh(ROOF2).height - 44, sh(ROOF2).width,
                              sh(ROOF2).height))
    ware = build_stack([crop_w(roof_wh, 6*T), crop_w(sh(GCONDO), 6*T)])
    px_, py_ = sc.ent(ware, 10.6, 30.0, bias=-0.3, prop=None)
    sc.shadow_blob(px_ + ware.width//2, int(31.0*T) - 6, ware.width - 14, 30)
    # 5 inherited pack-crates against the W wall + barrels on the E wall
    for i, (dx0, dy0) in enumerate([(0, 0), (1.15, 0.1), (0.5, -0.75),
                                    (1.7, -0.6), (1.05, -1.4)]):
        sc.ent(sh(P("Crate_Dark_Brown_Empty" if i % 2 else "Crate_Brown_Empty")),
               8.0 + dx0, 29.6 + dy0, prop="prop")
    sc.ent(cut(PROP, 24, 6, 2, 2), 16.9, 29.4, prop="prop")       # barrel pair
    sc.ent(cut(PROP, 24, 4, 1, 2), 17.7, 28.7, prop="prop")       # tall barrel
    sc.ent(cut(PROP, 26, 6, 2, 2), 17.1, 30.4, prop="prop")       # laying barrel

    # --- harbormaster office E of the road mouth (ledger-window + bollard table)
    roof_eave = sh(ROOF2).crop((0, sh(ROOF2).height - 28, sh(ROOF2).width,
                                sh(ROOF2).height))
    hut = build_stack([crop_w(roof_eave, 4*T), crop_w(sh(GCONDO), 4*T)])
    px_, py_ = sc.ent(hut, 32.5, 28.4, bias=-0.3, prop=None)
    sc.shadow_blob(px_ + hut.width//2, int(29.4*T) - 5, hut.width - 12, 30)
    # the Chair at the ledger window; bench = the bollard table
    px_, py_ = sc.ent(c_idle(1, "up"), 33.6, 29.3)
    sc.shadow_blob(px_ + 8, int(30.3*T) - 2, 12, 34)
    sc.ent(sh(BENCH), 36.8, 28.8, prop="prop")

    # --- berths: chalk frames + cleats + LANE-GROUPED cargo (6 active outcomes)
    # sys W of the road mouth; widgets + acme run E as one cargo waterfront
    berth_xs = [(18.5, "sys", 3), (21.5, "sys", 2), (36.5, "widgets", 4),
                (39.8, "widgets", 5), (43.6, "acme", 3), (46.9, "acme", 3)]
    chalk = (226, 230, 238, 190)
    for i, (bx_, lane, stg) in enumerate(berth_xs):
        by_ = 28.1 if i % 2 == 0 else 28.4
        # chalk berth rectangle (dashed)
        x0, y0 = int(bx_*T) - 3, int(by_*T) + 6
        x1, y1 = int(bx_*T) + 3*T + 9, int(by_*T) + 3*T + 4
        for xx in range(x0, x1, 4):
            gd.rectangle([xx, y0, xx+1, y0], fill=chalk)
            gd.rectangle([xx, y1, xx+1, y1], fill=chalk)
        for yy in range(y0, y1, 4):
            gd.rectangle([x0, yy, x0, yy+1], fill=chalk)
            gd.rectangle([x1, yy, x1, yy+1], fill=chalk)
        # mooring cleat on the wharf lip
        cxp = int(bx_*T) + 20
        gd.rectangle([cxp, QUAY_Y1*T + 10, cxp + 3, QUAY_Y1*T + 11], fill=(40, 44, 58, 255))
        gd.rectangle([cxp + 1, QUAY_Y1*T + 8, cxp + 2, QUAY_Y1*T + 12], fill=(58, 62, 78, 255))
        stk = berth_stack3(stg, "berth%d" % i)
        px_, py_ = sc.ent(stk, bx_, by_ + 1.6, prop="prop")
        sc.shadow_blob(px_ + stk.width//2, int((by_ + 2.6)*T) - 6, 28 + 2*stg, 26)
    # officer working at a crate-desk beside the widgets berths
    sc.ent(sh(P("Crate_Brown_Empty")), 38.6, 30.7, prop="prop")
    px_, py_ = sc.ent(c_idle(10, "up"), 38.7, 31.5)
    sc.shadow_blob(px_ + 8, int(32.5*T) - 2, 12, 34)

    # --- timber yard: cargo rows east of the berths (dense, touching)
    wood = sh(P("Wood_Board_Load"))
    for (spx, yx, yy_) in [(wood, 50.2, 28.5), (cut(PROP, 24, 6, 2, 2), 52.0, 28.4),
                           (sh(P("Crate_Brown_Empty")), 53.6, 28.6),
                           (cut(PROP, 24, 4, 1, 2), 55.0, 28.0),
                           (sh(P("Sack_Jute_Load_2")), 50.6, 29.8),
                           (sh(P("Crate_Dark_Brown_Empty")), 51.8, 29.9),
                           (wood, 53.4, 29.8), (sh(P("Sack_Jute_Load_1")), 55.1, 29.9)]:
        sc.ent(spx, yx, yy_, prop="prop")
    sc.shadow_blob(int(52.6*T), int(31.0*T) - 6, 78, 22)

    # --- quay lamps: one rhythm down the whole wharf (day: unlit)
    for lx_ in (8.9, 17.6, 30.9, 37.4, 43.9, 50.4):
        sc.ent(sh(LAMP), lx_, QUAY_Y0 - 0.6, dx=-6, prop="prop")

    # ============ piers + packet dock ============
    plank = tile(PLANK)
    piers = rect(25, SEA_Y, 26, 36) | rect(31, SEA_Y, 32, 36)
    dock  = rect(8, SEA_Y, 9, 35)
    edge = (58, 40, 26, 255)
    for (tx, ty) in sorted(piers | dock):
        sc.ground.paste(plank, (tx*T, ty*T))
    allp = piers | dock
    for (tx, ty) in sorted(allp):
        if (tx-1, ty) not in allp: gd.rectangle([tx*T, ty*T, tx*T, ty*T+15], fill=edge)
        if (tx+1, ty) not in allp: gd.rectangle([tx*T+15, ty*T, tx*T+15, ty*T+15], fill=edge)
        if (tx, ty+1) not in allp: gd.rectangle([tx*T, ty*T+15, tx*T+15, ty*T+15], fill=edge)
    for (px0, py0) in [(25*T-2, 36*T+8), (27*T, 36*T+8), (31*T-2, 36*T+8), (33*T, 36*T+8),
                       (25*T-2, SEA_Y*T+6), (27*T, SEA_Y*T+6), (31*T-2, SEA_Y*T+6),
                       (33*T, SEA_Y*T+6), (8*T-2, 35*T+8), (10*T, 35*T+8)]:
        gd.rectangle([px0, py0, px0+1, py0+5], fill=(44, 30, 20, 255))
        gd.rectangle([px0-1, py0+5, px0+2, py0+6], fill=(226, 234, 244, 150))

    # packet boat arriving at the dock (approvals inbound) + wake
    boat_up = sh(BOAT).transpose(Image.FLIP_TOP_BOTTOM)
    px_, py_ = sc.ent(boat_up, 10.2, 34.0, prop=None)
    wake = Image.new("RGBA", (40, 26), (0,0,0,0))
    wd = ImageDraw.Draw(wake)
    for i, wy in enumerate(range(2, 24, 5)):
        a = 175 - i*38
        wd.rectangle([14 - i*3, wy, 17 - i*3, wy], fill=(226, 236, 246, max(a, 30)))
        wd.rectangle([22 + i*3, wy + 1, 25 + i*3, wy + 1], fill=(226, 236, 246, max(a, 30)))
    sc.vfx(wake, px_ - 4, py_ + boat_up.height - 6)
    # the courier already mid-road, envelope in hand, heading for the mailbox
    cour = c_walk(2, "up", 3).copy()
    cd_ = ImageDraw.Draw(cour)
    cd_.rectangle([2, 18, 5, 20], fill=(242, 236, 222, 255))
    cd_.point((3, 19), fill=(96, 66, 42, 255))
    px_, py_ = sc.ent(cour, ROADX + 0.9, 24.2)
    sc.shadow_blob(px_ + 8, int(25.2*T) - 2, 12, 30)

    # deploying: an officer carries a crate down the E pier toward the boats
    carrier = c_walk(3, "down", 1).copy()
    bxs = sh(P("Box_Single"))
    carrier.alpha_composite(bxs.crop((2, 4, 14, 14)), (2, 12))
    px_, py_ = sc.ent(carrier, 31.4, 32.8)
    sc.shadow_blob(px_ + 8, int(33.8*T) - 2, 12, 30)

    # moored dinghy against the W pier + an OUTBOUND rowboat making for the isles
    sc.ent(sh(BOAT), 23.6, 33.6, prop=None)
    out_b = sh(BOAT)
    px_, py_ = sc.ent(out_b, 38.6, 34.4, prop=None)
    owake = Image.new("RGBA", (40, 22), (0,0,0,0))
    od = ImageDraw.Draw(owake)
    for i, wy in enumerate(range(18, 2, -5)):
        a = 165 - i*38
        od.rectangle([14 - i*3, wy, 17 - i*3, wy], fill=(226, 236, 246, max(a, 28)))
        od.rectangle([22 + i*3, wy - 1, 25 + i*3, wy - 1], fill=(226, 236, 246, max(a, 28)))
    sc.vfx(owake, px_ - 4, py_ - 18)

    # ============ lighthouse (DARK) on a STONE breakwater arm SE ============
    # the arm continues the wharf masonry out into the sea — harbor-built,
    # not a sand spit; the unlit lamp is the farthest, tallest silhouette
    arm = ({(tx, 32) for tx in (54, 55, 56)} | {(tx, 33) for tx in (54, 55, 56)}
           | {(tx, 34) for tx in (53, 54, 55)} | {(tx, 35) for tx in (53, 54)})
    for (tx, ty) in sorted(arm):
        sc.ground.paste(sw1, (tx*T, ty*T))
        for _ in range(4):
            fx2 = tx*T + jrng.ri(0, T-2); fy2 = ty*T + jrng.ri(0, T-2)
            gd.point((fx2, fy2), fill=(dark if jrng.rf() < 0.6 else lite) + (255,))
    for (tx, ty) in sorted(arm):
        if (tx-1, ty) not in arm:
            gd.rectangle([tx*T, ty*T, tx*T, ty*T+15], fill=dark + (255,))
        if (tx+1, ty) not in arm and tx < 56:
            gd.rectangle([tx*T+15, ty*T, tx*T+15, ty*T+15], fill=dark + (255,))
        if (tx, ty+1) not in arm:
            gd.rectangle([tx*T, ty*T+14, tx*T+15, ty*T+15], fill=dark + (255,))
    lh = build_lighthouse()
    px_, py_ = sc.ent(lh, 52.6, 34.2, bias=-0.2, prop=None)
    sc.shadow_blob(px_ + lh.width//2, int(35.2*T) - 6, lh.width - 18, 34)
    sc.ent(sh(P("Rock_Medium")), 52.4, 35.0, prop="prop")
    sc.ent(sh(P("Rock_Small")), 53.6, 33.0, prop="prop")
    sc.ent(sh(P("Rock_Small")), 56.0, 32.4, prop="prop")
    frng2 = LCG("point-foam")
    for _ in range(12):
        fx = frng2.ri(52*T, int(58.5*T)); fy2 = frng2.ri(int(32.5*T), int(36.5*T))
        gd.rectangle([fx, fy2, fx + frng2.ri(3, 7), fy2], fill=(222, 232, 244, 170))

    # reef-buoy at the retired example-org anchor (mid-ring, honest dormant)
    buoy = Image.new("RGBA", (8, 12), (0, 0, 0, 0))
    bd2 = ImageDraw.Draw(buoy)
    bd2.polygon([(1, 11), (6, 11), (5, 5), (2, 5)], fill=(198, 50, 40, 255))
    bd2.rectangle([3, 2, 4, 5], fill=(64, 46, 30, 255))
    bd2.rectangle([2, 7, 5, 8], fill=(242, 236, 222, 255))
    sc.ent(buoy, 28.7, 36.4, prop=None)
    gd.rectangle([int(28.4*T), int(37.5*T), int(28.4*T) + 10, int(37.5*T)], fill=(222, 232, 244, 150))

    # isle dressing: hut silhouettes + tree + jetty stub per isle
    # acme isle SW: one hut
    sc.ent(sh(P("Henhouse")), 5.2, 37.4, prop=None)
    sc.ent(tree("pineS"), 7.4, 37.0, bias=-0.05, prop=None)
    sc.ground.paste(plank, (6*T, 39*T))
    # widgets isle SE: two huts + crates (more has shipped there)
    sc.ent(sh(P("Henhouse")), 41.2, 37.5, prop=None)
    sc.ent(sh(P("Chicken_Coop")), 44.4, 38.0, bias=-0.1, prop=None)
    sc.ent(tree("oakS"), 43.0, 36.7, bias=-0.05, prop=None)
    sc.ent(sh(P("Box_Single")), 43.6, 38.8, prop="prop")
    sc.ground.paste(plank, (42*T, 39*T))

    # ============ ducks near the W pier ============
    for i, (tx, ty) in enumerate([(20.5, 33.6), (22, 34.6), (21, 35.6), (19.3, 34.4)]):
        df = duck_frame(i % 4, brown=(i == 3))
        px_, py_ = sc.ent(df, tx, ty)
        gd.rectangle([px_ + 2, int((ty+1)*T) - 3, px_ + 13, int((ty+1)*T) - 3],
                     fill=(226, 236, 246, 90))

    # ============ tree-wall ring (N + W + E rims; sea stays open S) ============
    oXL, oL, oM, oS = tree("oakXL"), tree("oakL"), tree("oakM"), tree("oakS")
    pM = tree("pineM")
    wr = LCG("ring")
    def ring_tree(tx, ty, kinds=None):
        im = wr.pick(kinds or [oXL, oL, oL, oM, pM, oXL])
        px2, py2 = sc.ent(im, tx + wr.ri(-1, 1)*0.4, ty, bias=-0.05)
        sc.shadow_blob(px2 + im.width//2, int((ty+1)*T) - 5, im.width - 18, 26)
    x = -2.0
    while x < 58:
        ring_tree(x, wr.ri(0, 1)); x += 2.0
    x = -1.0
    while x < 58:
        if not (43 <= x <= 55):
            ring_tree(x, 1 + wr.ri(0, 1))
        else:
            ring_tree(x, 1, [oM, oL])       # shallow over the orchard
        x += 2.2
    # west column down to the cove
    y = 2
    while y < 26:
        ring_tree(-0.8, y); y += wr.ri(2, 3)
    y = 4
    while y < 22:
        ring_tree(1.1, y, [oM, oS, pM]); y += wr.ri(3, 5)
    # east column down to the warehouse
    y = 2
    while y < 24:
        ring_tree(57.6 + wr.ri(0, 2)*0.3, y, [oL, oM, pM, oXL]); y += wr.ri(1, 2)
    y = 4
    while y < 22:
        ring_tree(56.2, y, [oM, oS, pM]); y += wr.ri(3, 4)
    # inner accents
    for (tx, ty, im) in [(19, 8, oM), (10, 9, oS), (42, 17, oS), (8, 15, oM),
                         (52, 14, oM), (54, 18, oS), (17, 12, oS)]:
        px2, py2 = sc.ent(im, tx, ty, bias=-0.05)
        sc.shadow_blob(px2 + im.width//2, int((ty+1)*T) - 5, im.width - 16, 24)

    return sc

# ================================================================ map + labels
def emit_map(sc):
    prop_tiles = []
    for (name, x, y, w_px, h_px) in sc.props:
        prop_tiles.append({"sheet": name, "region": [0, 0, w_px, h_px], "x": x, "y": y})
    m = {"schema": "cabinet.world.map/v1", "tile_size": T, "width": W, "height": H,
         "layers": [
             {"name": "ground", "kind": "terrain", "walkable": True, "tiles":
              [{"sheet": "terrain", "region": [0, 0, T, T], "x": 0, "y": 0}]},
             {"name": "props", "kind": "prop", "tiles": prop_tiles},
         ]}
    with open(OUT + "/unified-world.map.json", "w") as f:
        json.dump(m, f, indent=1)
    labels = {"schema": "cabinet.world.labels/v1",
              "render": {"width": 1920, "height": 1280}, "labels": []}
    with open(OUT + "/unified-world.labels.json", "w") as f:
        json.dump(labels, f, indent=1)
    print("map/labels json written (%d props)" % len(prop_tiles))

# ================================================================ renders
def main():
    sc = build_scene()
    base = sc.compose()

    world = up(base, 2).convert("RGB")
    world.save(OUT + "/unified-world.png")
    print("unified-world.png", world.size)

    # close: x3 crop centered on the crossroads (mailbox ~ (31,20), commuter ~(28,19))
    big = up(base, 3).convert("RGB")
    cx, cy = int(29.5*T*3), int(22.4*T*3)
    CW, CH = 1584, 1200
    x0 = max(0, min(big.width - CW, cx - CW//2))
    y0 = max(0, min(big.height - CH, cy - CH//2))
    close = big.crop((x0, y0, x0 + CW, y0 + CH))
    close.save(OUT + "/unified-close.png")
    print("unified-close.png", close.size, "crop origin", (x0, y0))

    emit_map(sc)

if __name__ == "__main__":
    main()
