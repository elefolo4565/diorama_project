"""ネザサ (Pleioblastus argenteostriatus f. glaber) の形 (Claude 版)。基準は plants/notes/nezasa.md。
地下茎で広がり、すき間なく密なやぶを作るササ (1〜2m、刈られるあぜでは 0.3〜0.8m)。細い稈が真っすぐ立ち、
上の方で枝を出して葉が茂る。やぶの上面は葉の重みで外へ弓なりに垂れる。下の方は枯れた茶色の葉と稈が混じる。
1 株ではなく帯・面に続くので、1 つの形は横に広い「やぶのかたまり」にする。
季節の形は 2 つ: 春〜秋 = 明るい緑 (基本の形)、冬 = 葉の縁が白く枯れて全体に淡い色 (`_Fuyu`)。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from scenery_meshes import Mesh, Rng

NAME = "NezasaOpus"
LEAF_COLORS = {
    "": ((96, 130, 48), (112, 144, 56), (84, 116, 42), (124, 150, 62)),       # 明るい緑〜黄緑、つやは弱い
    "Fuyu": ((118, 132, 70), (132, 142, 82), (106, 120, 64), (144, 148, 92)),  # 冬: 色が淡く黄ばむ
}
DEAD = ((150, 126, 84), (128, 106, 70))   # 下の方の枯れた葉
CULM = (110, 128, 70)
EDGE = (222, 218, 196)                    # 冬の白く枯れた葉の縁
LEAVES, MATERIALS = {}, {}
STAND_CELLS = ((0, 0), (1, 0), (0, 1))    # 稈が並んで立ち、上で葉が茂る絵
TOP_CELL = (1, 1)                         # 上から見た葉の広がり


def _leaf(draw, base, ang, ln, col, edge):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = fo._leaf_polygon(base, ang, ln, 0.16, n=10)
    draw.polygon(pts, fill=col)
    if edge:   # 冬: 縁が白く枯れる
        draw.line(pts + [pts[0]], fill=EDGE, width=2)
    draw.line([base, (base[0] + ca * ln * 0.9, base[1] + sa * ln * 0.9)], fill=tuple(int(c * 0.8) for c in col), width=1)


def _texture(path, season, size=fo.TEXTURE_SIZE):
    r = random.Random(NAME)   # 季節で並びを変えない
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    colors = LEAF_COLORS[season]
    fuyu = season == "Fuyu"
    for (i, j) in STAND_CELLS:
        ox, oy, s = i * cell, j * cell, cell
        culms = []
        for k in range(9):   # 細い稈が少しずつ傾いて並ぶ
            x0 = ox + s * (0.08 + 0.84 * (k + r.uniform(0.1, 0.9)) / 9)
            top = (x0 + r.uniform(-0.06, 0.06) * s, oy + s * r.uniform(0.08, 0.3))
            draw.line([(x0, oy + s * 0.99), top], fill=CULM, width=max(2, s // 260))
            culms.append(((x0, oy + s * 0.99), top))
        for (x0, y0), (x1, y1) in culms:
            # 下の方: 枯れた茶色の葉が少し
            for _ in range(2):
                t = r.uniform(0.15, 0.4)
                b = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                _leaf(draw, b, math.pi / 2 + r.uniform(-1.2, 1.2), s * r.uniform(0.08, 0.13), fo._jitter(r.choice(DEAD), r), False)
            # 上の方: 枝先に 3〜9 枚ずつ手のひらのように広がり、外へ垂れる
            for _ in range(r.randint(4, 6)):
                t = r.uniform(0.45, 1.0)
                b = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                n = r.randint(3, 7)
                for q in range(n):
                    a = -math.pi / 2 + (q - (n - 1) / 2) * 0.5 + r.uniform(-0.2, 0.2) + (0.6 if q > n / 2 else -0.6) * t
                    ln = s * r.uniform(0.12, 0.2)
                    k_ = 1.12 - 0.3 * ((b[1] - oy) / s)
                    col = tuple(int(min(255, c * k_)) for c in fo._jitter(r.choice(colors), r, 10))
                    _leaf(draw, b, a, ln, col, fuyu and r.random() < 0.7)
    ox, oy, s = TOP_CELL[0] * cell, TOP_CELL[1] * cell, cell
    for _ in range(26):   # 上から見たやぶ: 葉の手のひらが重なる
        c = (ox + s * r.uniform(0.12, 0.88), oy + s * r.uniform(0.12, 0.88))
        n = r.randint(5, 8)
        a0 = r.uniform(0, 2 * math.pi)
        for q in range(n):
            a = a0 + 2 * math.pi * q / n + r.uniform(-0.2, 0.2)
            col = fo._jitter(r.choice(colors), r, 10)
            _leaf(draw, c, a, s * r.uniform(0.1, 0.16), col, fuyu and r.random() < 0.7)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


for _s in LEAF_COLORS:
    _leaf_name, _png = f"FD_Leaf_{NAME}{_s}", f"T_FD_Leaf_{NAME}{_s}.png"
    fo.LEAF_KINDS[_leaf_name] = dict(texture=_png, style="broad", leaves=0, length=(1, 1), width=0.2, colors=LEAF_COLORS[_s])
    MATERIALS[_leaf_name] = dict(color=(1, 1, 1), roughness=0.7, texture=_png, alpha=True)
    LEAVES[_leaf_name] = (_png, lambda path, s=_s: _texture(path, s))
REGIONS = ("kyushu", "shikoku", "chugoku", "kansai", "chubu", "kanto")


def _card(fol, center, up, side, w, h, cell, flip, dark):
    """center を中心に、up の向きに高さ h、幅 w の板 (cell の区画の絵)。下の辺ほど暗い。"""
    up = np.asarray(up, float) / np.linalg.norm(up)
    side = np.asarray(side, float) / np.linalg.norm(side)
    c0 = np.asarray(center, float)
    corners = [c0 - side * w / 2 - up * h / 2, c0 + side * w / 2 - up * h / 2,
               c0 + side * w / 2 + up * h / 2, c0 - side * w / 2 + up * h / 2]
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


def nezasa(name, seed, height, rx, ry, stands, season=""):
    """height: やぶの高さ、rx, ry: やぶの広がり (半径)、stands: 稈の並ぶ板の数。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = fo.Foliage(f"FD_Leaf_{NAME}{season}", rng, (0, 0, height * 0.5), (rx, ry, height * 0.6))
    for _ in range(stands):   # 縦の板: 稈が並んで立つ。やぶの縁ほど低い
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 1))
        x, y = math.cos(a) * rx * rr * 0.85, math.sin(a) * ry * rr * 0.85
        h = height * (1.0 - 0.35 * rr * rr) * rng.uniform(0.85, 1.1)
        face = rng.uniform(0, math.pi)
        side = np.array([math.cos(face), math.sin(face), 0.0])
        out = np.array([x / rx, y / ry, 0.0]) * 0.25
        _card(fol, (x, y, h / 2 - 0.03), np.array([0, 0, 1.0]) + out, side, h * rng.uniform(0.9, 1.2), h,
              STAND_CELLS[int(rng.integers(0, 3))], rng.random() < 0.5, 0.45)
    for _ in range(int(stands * 0.6)):   # 上面: 外へ弓なりに垂れる葉の層
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 0.6))
        x, y = math.cos(a) * rx * rr, math.sin(a) * ry * rr
        z = height * (1.0 - 0.45 * rr * rr) * rng.uniform(0.78, 0.92)
        tilt = np.array([math.cos(a), math.sin(a), 0.0]) * rr * 0.4
        normal = np.array([0, 0, 1.0]) + tilt
        side = np.cross(normal, [math.cos(a + 1.3), math.sin(a + 1.3), 0.0])
        up = np.cross(side, normal)
        w = min(rx, ry) * rng.uniform(0.45, 0.65)
        _card(fol, (x, y, z), up, side, w, w, TOP_CELL, rng.random() < 0.5, 0.75)
    return fol.write(m)


SEASONS = {"": 1 | 2 | 4, "Fuyu": 8}
SHAPES = {   # 林のふちの背の高いやぶ / 道沿いのやぶ / あぜの刈られた低いやぶ
    "A": (191, 1.5, 1.1, 0.8, 26, ("understory",), 0.04),
    "B": (192, 1.0, 0.9, 0.6, 22, ("understory", "farm"), 0.04),
    "C": (193, 0.5, 0.9, 0.5, 26, ("farm",), 0.04),
}
PLANTS = {}
for _k, (_seed, _h, _rx, _ry, _st, _hab, _sh) in SHAPES.items():
    _base = f"SM_FD_{NAME}_{_k}"
    for _s, _bits in SEASONS.items():
        _n = _base + (f"_{_s}" if _s else "")
        PLANTS[_n] = dict(make=lambda s=_seed, h=_h, a=_rx, b=_ry, st=_st, se=_s, n=_n: nezasa(n, s, h, a, b, st, se),
                          height_m=_h, habitat=_hab, share=_sh, seasons=_bits, regions=REGIONS,
                          **({"place_with": _base} if _s else {}))
