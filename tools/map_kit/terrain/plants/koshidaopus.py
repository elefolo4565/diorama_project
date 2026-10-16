"""コシダ (Dicranopteris linearis) の形 (Claude 版)。基準は plants/notes/koshida.md。
日当たりのよい斜面・切り通し・尾根の荒れ地を一面に覆うシダ (0.3〜1m)。針金のような細い黒褐色の柄が 2 つに分かれることを
何度もくり返し、からまり合ったやぶになる。分かれた枝先に細長い羽片 (10〜25cm) が 2 枚ずつ付く。
色は黄緑〜明るい緑 (日なたほど黄色っぽい)、裏は白っぽい。中に枯れた茶色の柄と古い葉が多く残る。上面はややでこぼこの平ら。
1 つの形は「からまり合った小さなやぶ」: 柄と羽片のからまりを描いた縦の板を何枚も立て、上面を羽片の板で覆う。
一年中ほぼ同じなので形は 1 つ。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from scenery_meshes import Mesh, Rng

LEAF = "FD_Leaf_KoshidaOpus"
LEAF_PNG = "T_FD_Leaf_KoshidaOpus.png"
GREEN = ((128, 150, 52), (142, 160, 60), (112, 138, 48), (150, 162, 70))   # 黄緑〜明るい緑
UNDER = ((178, 188, 160), (166, 178, 150))                                 # 裏は白っぽい
DEAD = ((146, 112, 70), (124, 94, 58))                                     # 枯れた古い葉
WIRE = (60, 44, 30)                                                        # 針金のような黒褐色の柄
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.3, colors=GREEN)
TANGLE_CELLS = ((0, 0), (1, 0))   # 横から見たからまり
TOP_CELL = (0, 1)                 # 上から見た羽片の広がり
DEAD_CELL = (1, 1)                # 枯れたからまり (やぶの下の方)


def _pinna(draw, r, base, ang, ln, colors):
    """細長い羽片: 軸の左右に細かい裂片が櫛の歯のように並ぶ。"""
    ca, sa = math.cos(ang), math.sin(ang)
    n = 12
    for k in range(1, n):
        t = k / n
        p = (base[0] + ca * ln * t, base[1] + sa * ln * t)
        w = ln * 0.16 * math.sin(math.pi * t) ** 0.5
        for side in (1, -1):
            a = ang + side * 1.2
            col = fo._jitter(r.choice(colors), r, 10)
            draw.polygon(fo._leaf_polygon(p, a, w, 0.5, n=6), fill=col)
    draw.line([base, (base[0] + ca * ln, base[1] + sa * ln)], fill=WIRE, width=1)


def _tangle(draw, r, ox, oy, s, colors, wire, stems=5):
    """区画の下から柄が何本も立ち、2 つに分かれることを 3〜4 回くり返す。上の分かれ目に羽片が 2 枚ずつ。"""
    for _ in range(stems):
        p = (ox + s * r.uniform(0.1, 0.9), oy + s * 0.99)
        level = [(p, -math.pi / 2 + r.uniform(-0.3, 0.3))]
        seg = s * r.uniform(0.2, 0.26)
        for lv in range(4):
            nxt = []
            for q, a in level:
                for side in (1, -1):
                    a2 = a + side * r.uniform(0.35, 0.6)
                    e = (q[0] + math.cos(a2) * seg, max(oy + s * 0.03, q[1] + math.sin(a2) * seg))
                    draw.line([q, e], fill=wire, width=max(2, s // 300))
                    nxt.append((e, a2 * 0.6 - math.pi / 2 * 0.4))
            level = nxt
            seg *= 0.72
            if lv >= 2:
                for q, a in level:
                    for side in (1, -1):
                        _pinna(draw, r, q, a + side * r.uniform(0.9, 1.4), s * r.uniform(0.14, 0.2), colors)


def leaf_texture(path, size=fo.TEXTURE_SIZE):
    r = random.Random("KoshidaOpus")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for (i, j) in TANGLE_CELLS:
        _tangle(draw, r, i * cell, j * cell, cell, GREEN + UNDER[:1], WIRE)
    _tangle(draw, r, DEAD_CELL[0] * cell, DEAD_CELL[1] * cell, cell, DEAD, (84, 64, 44))
    ox, oy, s = TOP_CELL[0] * cell, TOP_CELL[1] * cell, cell
    for _ in range(30):   # 上から見たやぶ: 2 枚ずつの羽片がいろいろな向きに重なる
        c = (ox + s * r.uniform(0.12, 0.88), oy + s * r.uniform(0.12, 0.88))
        a = r.uniform(0, 2 * math.pi)
        for side in (1, -1):
            _pinna(draw, r, c, a + side * r.uniform(1.2, 1.8), s * r.uniform(0.14, 0.22), GREEN)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


MATERIALS = {LEAF: dict(color=(1, 1, 1), roughness=0.75, texture=LEAF_PNG, alpha=True)}
LEAVES = {LEAF: (LEAF_PNG, leaf_texture)}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto")


def _card(fol, center, up, side, w, h, cell, flip, dark):
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
        n = d / max(np.linalg.norm(d), 1e-6) * 0.5 + np.array([0, 0, 0.5])
        fol.normals.append(n / np.linalg.norm(n))
        fol.colors.append(dark if k < 2 else 1.0)
        fol.verts.append(c)
        fol.uvs.append(t)


def koshida(name, seed, height, rx, ry, stands):
    """height: やぶの高さ、rx, ry: 広がり (半径)、stands: からまりの縦の板の数。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = fo.Foliage(LEAF, rng, (0, 0, height * 0.5), (rx, ry, height * 0.6))
    for _ in range(stands):
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 1))
        x, y = math.cos(a) * rx * rr * 0.85, math.sin(a) * ry * rr * 0.85
        h = height * (1.0 - 0.3 * rr * rr) * rng.uniform(0.85, 1.1)
        face = rng.uniform(0, math.pi)
        side = np.array([math.cos(face), math.sin(face), 0.0])
        cell = DEAD_CELL if rng.random() < 0.2 else TANGLE_CELLS[int(rng.integers(0, 2))]
        h = h * 0.75 if cell == DEAD_CELL else h
        _card(fol, (x, y, h / 2 - 0.03), [x / rx * 0.15, y / ry * 0.15, 1.0], side, h * rng.uniform(1.0, 1.4), h,
              cell, rng.random() < 0.5, 0.5)
    for _ in range(int(stands * 0.7)):   # 上面: ややでこぼこの平らな羽片の層
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 0.7))
        x, y = math.cos(a) * rx * rr, math.sin(a) * ry * rr
        z = height * (1.0 - 0.3 * rr * rr) * rng.uniform(0.66, 0.8)
        normal = np.array([rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 1.0])
        side = np.cross(normal, [math.cos(a), math.sin(a), 0.0])
        up = np.cross(side, normal)
        w = min(rx, ry) * rng.uniform(0.5, 0.75)
        _card(fol, (x, y, z), up, side, w, w, TOP_CELL, rng.random() < 0.5, 0.8)
    return fol.write(m)


PLANTS = {
    # 切り通しの斜面のやぶ / 林のふち / 尾根の低いやぶ
    "SM_FD_KoshidaOpus_A": dict(make=lambda: koshida("SM_FD_KoshidaOpus_A", 211, 0.9, 1.2, 0.9, 26),
                                height_m=0.9, habitat=("understory",), share=0.04, regions=REGIONS),
    "SM_FD_KoshidaOpus_B": dict(make=lambda: koshida("SM_FD_KoshidaOpus_B", 212, 0.65, 1.0, 0.8, 22),
                                height_m=0.65, habitat=("understory",), share=0.04, regions=REGIONS),
    "SM_FD_KoshidaOpus_C": dict(make=lambda: koshida("SM_FD_KoshidaOpus_C", 213, 0.4, 0.8, 0.6, 18),
                                height_m=0.4, habitat=("understory",), share=0.03, regions=REGIONS),
}
