"""ススキ (Miscanthus sinensis) の形 (Claude 版)。基準は plants/notes/susuki.md。
根元から密に葉が出る株立ちの大きな草 (1〜2m)。細長い葉が株の中心から噴水のように立ち上がり、外へ弓なりに垂れる。
季節の形は 3 つ: 春・夏 = 緑の葉だけ (基本の形)、秋 = 株の上へ稈が抜き出て銀白色の穂 (`_Aki`)、
冬 = 株全体が枯れた茶色〜薄い黄土色で、ほつれた古い穂が残る (`_Fuyu`。少し倒れて低い)。
どれも同じ乱数の順で作るので、株の形は 3 つとも同じ。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from scenery_meshes import Mesh, Rng

NAME = "SusukiOpus"
# 季節ごとの葉の色と穂の色 (並びは同じで、色だけ変える)
LEAF_COLORS = {
    "": ((86, 118, 48), (104, 134, 58), (76, 104, 44), (118, 142, 66)),            # 春・夏: 緑〜灰緑
    "Aki": ((112, 124, 60), (134, 132, 70), (100, 110, 54), (150, 128, 72)),       # 秋: 少し黄ばんだ緑
    "Fuyu": ((178, 152, 104), (160, 134, 90), (192, 170, 122), (140, 116, 80)),    # 冬: 枯れた茶色〜薄い黄土色
}
PLUME_COLORS = {
    "": ((214, 206, 192), (196, 170, 168)),
    "Aki": ((232, 226, 212), (214, 200, 190), (200, 172, 170)),   # 銀白色、出たての赤紫が少し
    "Fuyu": ((204, 190, 164), (186, 170, 142)),                    # 色あせて茶色がかる
}
STALK = {"": (120, 132, 70), "Aki": (150, 140, 84), "Fuyu": (172, 150, 108)}
LEAVES, MATERIALS = {}, {}
LEAF_CELLS = ((0, 0), (1, 0), (0, 1))   # 葉の噴水の絵
PLUME_CELL = (1, 1)                     # 稈と穂の絵


def _blade(draw, r, root, s, ang, length, width, col, droop):
    """付け根から ang の向きに立ち上がり、先が外へ弓なりに垂れる細長い葉。"""
    pts_l, pts_r = [], []
    n = 14
    for k in range(n + 1):
        t = k / n
        a = ang + droop * t * t * (1 if ang >= 0 else -1)   # 先ほど外へ倒れる
        if k == 0:
            x, y = root
        else:
            x += math.sin(a) * length / n
            y -= math.cos(a) * length / n
        w = width * s * (1 - t) ** 0.8 * 0.5
        nx, ny = math.cos(a), math.sin(a)
        pts_l.append((x - nx * w, y - ny * w))
        pts_r.append((x + nx * w, y + ny * w))
    draw.polygon(pts_l + pts_r[::-1], fill=col)


def _texture(path, season, size=fo.TEXTURE_SIZE):
    """2x2。3 つの区画は根元から噴水のように広がる葉の束、1 つは稈と穂。"""
    r = random.Random(NAME)   # 季節で並びを変えない (同じ乱数の順)
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    colors = LEAF_COLORS[season]
    for (i, j) in LEAF_CELLS:
        ox, oy, s = i * cell, j * cell, cell
        root = (ox + s * 0.5, oy + s * 0.99)
        blades = []
        for _ in range(46):
            ang = r.gauss(0, 0.42)
            ang = max(-1.1, min(1.1, ang))
            length = s * r.uniform(0.55, 0.95) * (1 - 0.25 * abs(ang))
            droop = r.uniform(0.6, 1.5) + abs(ang) * 0.8
            blades.append((ang, length, droop, r.uniform(0.012, 0.02), r.choice(colors)))
        blades.sort(key=lambda b: -abs(b[0]))   # 外の葉から描き、中心の葉を手前に
        for ang, length, droop, w, base in blades:
            col = fo._jitter(base, r, 10)
            if season == "Fuyu":
                droop *= 1.25   # 枯れて垂れる
            _blade(draw, r, root, s, ang, length, w, col, droop)
    # 稈と穂: 区画の下から上へ細い稈、先 35% にほうきのように広がる 10〜20 本の細い枝 (綿毛でふわふわ)
    i, j = PLUME_CELL
    ox, oy, s = i * cell, j * cell, cell
    x0, y0 = ox + s * 0.5, oy + s * 0.99
    head = (ox + s * 0.5 + s * 0.03, oy + s * 0.42)
    draw.line([(x0, y0), head], fill=STALK[season], width=max(3, s // 160))
    n = 14 if season == "Fuyu" else 18
    pcols = PLUME_COLORS[season]
    for k in range(n):
        spread = (k - (n - 1) / 2) / n
        ln = s * r.uniform(0.26, 0.38)
        pts = [head]
        x, y = head
        for q in range(1, 9):
            t = q / 8
            a = spread * 1.1 + 0.35 * t * t   # 先が少し片側へ垂れる
            x += math.sin(a) * ln / 8
            y -= math.cos(a) * ln / 8
            pts.append((x, y))
        col = r.choice(pcols)
        draw.line(pts, fill=col, width=max(2, s // 300))
        fuzz = 22 if season != "Fuyu" else 9   # 綿毛 (冬はほつれて少ない)
        for _ in range(fuzz):
            px, py = pts[r.randrange(2, len(pts))]
            rad = s * r.uniform(0.006, 0.012)
            c2 = fo._jitter(col, r, 8)
            draw.ellipse([px - rad, py - rad * 1.6, px + rad, py + rad * 1.6], fill=c2 + (255,))
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


for _s in LEAF_COLORS:
    _leaf_name, _png = f"FD_Leaf_{NAME}{_s}", f"T_FD_Leaf_{NAME}{_s}.png"
    fo.LEAF_KINDS[_leaf_name] = dict(texture=_png, style="broad", leaves=0, length=(1, 1), width=0.2, colors=LEAF_COLORS[_s])
    MATERIALS[_leaf_name] = dict(color=(1, 1, 1), roughness=0.7, texture=_png, alpha=True)
    LEAVES[_leaf_name] = (_png, lambda path, s=_s: _texture(path, s))
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto", "tohoku", "hokuriku", "hokkaido")


def _card(fol, bottom, up, side, w, h, cell, flip, dark=0.45):
    """bottom (下の辺の中央) から up の向きに高さ h、幅 w の板。cell の区画の絵を貼る。下ほど暗い。"""
    up = np.asarray(up, float) / np.linalg.norm(up)
    side = np.asarray(side, float) / np.linalg.norm(side)
    b = np.asarray(bottom, float)
    corners = [b - side * w / 2, b + side * w / 2, b + side * w / 2 + up * h, b - side * w / 2 + up * h]
    ci, cj = cell
    u0, u1 = ci / fo.CELLS, (ci + 1) / fo.CELLS
    v0, v1 = cj / fo.CELLS, (cj + 1) / fo.CELLS
    if flip:
        u0, u1 = u1, u0
    for k, (c, t) in enumerate(zip(corners, [(u0, v1), (u1, v1), (u1, v0), (u0, v0)])):
        d = (c - fol.center) / fol.radii
        n = d / max(np.linalg.norm(d), 1e-6) * 0.6 + np.array([0, 0, 0.4])
        fol.normals.append(n / np.linalg.norm(n))
        fol.colors.append(dark if k < 2 else 1.0)
        fol.verts.append(c)
        fol.uvs.append(t)


def susuki(name, seed, height, width, blades, culms, season=""):
    """height: 葉の高さ、width: 株の半径、blades: 葉の束の板の数、culms: 穂の数 (秋・冬だけ見える)。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = fo.Foliage(f"FD_Leaf_{NAME}{season}", rng, (0, 0, height * 0.4), (width, width, height * 0.6))
    sag = 0.85 if season == "Fuyu" else 1.0   # 冬は枯れて少し倒れ、低くなる
    for k in range(blades):
        az = math.pi * k / blades + rng.uniform(-0.2, 0.2)   # 半回転で全周 (板は両面)
        side = np.array([math.cos(az), math.sin(az), 0.0])
        out = np.array([-math.sin(az), math.cos(az), 0.0])
        tilt = rng.uniform(-0.25, 0.25)
        up = np.array([0, 0, 1.0]) + out * tilt
        off = rng.normal(size=2) * width * 0.12
        h = height * rng.uniform(0.75, 1.05) * sag
        w = width * rng.uniform(1.7, 2.2)
        cell = LEAF_CELLS[int(rng.integers(0, 3))]
        _card(fol, (off[0], off[1], -0.03), up + out * (0.12 if season == "Fuyu" else 0.0), side, w, h, cell,
              rng.random() < 0.5)
    tall = height * 1.55
    for k in range(culms):
        a = rng.uniform(0, 2 * math.pi)
        lean = rng.uniform(0.05, 0.22) * (1.4 if season == "Fuyu" else 1.0)
        up = np.array([math.cos(a) * lean, math.sin(a) * lean, 1.0])
        h = tall * rng.uniform(0.85, 1.08) * sag
        face = a + math.pi / 2 + rng.uniform(-0.6, 0.6)
        side = np.array([math.cos(face), math.sin(face), 0.0])
        off = rng.normal(size=2) * width * 0.15
        flip = rng.random() < 0.5
        if season in ("Aki", "Fuyu"):
            _card(fol, (off[0], off[1], 0.0), up, side, h * 0.42, h, PLUME_CELL, flip, dark=0.7)
    return fol.write(m)


SEASONS = {"": 1 | 2, "Aki": 4, "Fuyu": 8}
SHAPES = {"A": (161, 1.25, 0.55, 30, 18), "B": (162, 0.95, 0.45, 26, 12), "C": (163, 0.7, 0.35, 26, 8)}
SHARES = {"A": 0.05, "B": 0.05, "C": 0.04}
PLANTS = {}
for _k, (_seed, _h, _w, _bl, _cu) in SHAPES.items():
    _base = f"SM_FD_{NAME}_{_k}"
    for _s, _bits in SEASONS.items():
        _n = _base + (f"_{_s}" if _s else "")
        _hm = {"": _h, "Aki": _h * 1.55, "Fuyu": _h * 1.55 * 0.85}[_s]
        PLANTS[_n] = dict(make=lambda s=_seed, h=_h, w=_w, b=_bl, c=_cu, se=_s, n=_n: susuki(n, s, h, w, b, c, se),
                          height_m=round(_hm, 2), habitat=("grassland", "farm"), share=SHARES[_k], seasons=_bits,
                          regions=REGIONS, **({"place_with": _base} if _s else {}))
