"""ウラジロ (Gleichenia japonica) の形 (Claude 版)。基準は plants/notes/urajiro.md。
森の足もとや林のふちの斜面に大きな群れを作るシダ (0.5〜1.5m)。1 枚の葉は長い茶色の柄の先で左右 2 枚の大きな羽片に分かれ、
それぞれが弓なりに水平〜斜め下へ広がる。分かれ目から次の段が伸び、2〜3 段に重なる。
羽片は細い小羽片が櫛の歯のように密に並ぶ。表は明るい〜やや黄みの緑、裏は白い (名前の由来)。下には枯れた茶色の古い葉。
1 株ではなく群れなので、1 つの形は「何枚もの葉が重なった小さな群れ」にする。一年中ほぼ同じなので形は 1 つ。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng

LEAF = "FD_Leaf_UrajiroOpus"
LEAF_PNG = "T_FD_Leaf_UrajiroOpus.png"
GREEN = ((104, 136, 50), (118, 148, 56), (92, 124, 46), (128, 152, 62))
UNDER = ((196, 204, 182), (182, 192, 170))   # 裏は白い
DEAD = ((142, 112, 72), (124, 96, 62))       # 枯れた古い葉
RACHIS = (120, 96, 60)
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.3, colors=GREEN)
# 区画: (0,0) (1,0) 表の羽片、(0,1) 裏が見える羽片、(1,1) 枯れた羽片
FRONT_CELLS = ((0, 0), (1, 0))
UNDER_CELL = (0, 1)
DEAD_CELL = (1, 1)


def _pinna(draw, r, ox, oy, s, colors, rachis):
    """区画の下の中央から上へ伸びる 1 枚の羽片。軸の左右に細長い小羽片が櫛の歯のように密に並び、先ほど短い。"""
    x0, y0 = ox + s * 0.5, oy + s * 0.99
    n = 34
    pts = []
    for k in range(n + 1):
        t = k / n
        pts.append((x0 + math.sin(t * 2.2) * s * 0.03, y0 - t * s * 0.95))
    draw.line(pts, fill=rachis, width=max(3, s // 200))
    for k in range(1, n):
        t = k / n
        p = pts[k]
        ln = s * 0.27 * math.sin(math.pi * min(1.0, t * 1.1)) ** 0.6 * (1.05 - 0.4 * t)
        for side in (1, -1):
            ang = -math.pi / 2 + side * r.uniform(1.15, 1.35)
            col = fo._jitter(r.choice(colors), r, 10)
            draw.polygon(fo._leaf_polygon(p, ang, ln, 0.3, n=8), fill=col)


def leaf_texture(path, size=fo.TEXTURE_SIZE):
    r = random.Random("UrajiroOpus")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for (i, j) in FRONT_CELLS:
        _pinna(draw, r, i * cell, j * cell, cell, GREEN, RACHIS)
    _pinna(draw, r, UNDER_CELL[0] * cell, UNDER_CELL[1] * cell, cell, UNDER, RACHIS)
    _pinna(draw, r, DEAD_CELL[0] * cell, DEAD_CELL[1] * cell, cell, DEAD, (96, 74, 48))
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


MATERIALS = {LEAF: dict(color=(1, 1, 1), roughness=0.75, texture=LEAF_PNG, alpha=True)}
LEAVES = {LEAF: (LEAF_PNG, leaf_texture)}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto", "hokuriku")


def _card(fol, base, along, normal, length, width, cell, dark):
    """base (羽片の付け根) から along の向きに長さ length、幅 width の羽片の板。付け根ほど暗い。"""
    along = np.asarray(along, float) / np.linalg.norm(along)
    side = np.cross(normal, along)
    side /= np.linalg.norm(side)
    b = np.asarray(base, float)
    corners = [b - side * width / 2, b + side * width / 2, b + side * width / 2 + along * length, b - side * width / 2 + along * length]
    ci, cj = cell
    u0, u1 = ci / fo.CELLS, (ci + 1) / fo.CELLS
    v0, v1 = cj / fo.CELLS, (cj + 1) / fo.CELLS
    for k, (c, t) in enumerate(zip(corners, [(u0, v1), (u1, v1), (u1, v0), (u0, v0)])):
        d = (c - fol.center) / fol.radii
        n = d / max(np.linalg.norm(d), 1e-6) * 0.4 + np.array([0, 0, 0.6])
        fol.normals.append(n / np.linalg.norm(n))
        fol.colors.append(dark if k < 2 else 1.0)
        fol.verts.append(c)
        fol.uvs.append(t)


def urajiro(name, seed, height, radius, fronds, tiers):
    """height: 群れの高さ、radius: 群れの広がり、fronds: 葉の数、tiers: 1 枚の葉の段の数 (2〜3)。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = fo.Foliage(LEAF, rng, (0, 0, height * 0.5), (radius, radius, height * 0.6))
    for _ in range(int(fronds * 0.5)):   # 下に積もった枯れた古い葉
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 1)) * radius * 0.8
        p = np.array([math.cos(a) * rr, math.sin(a) * rr, rng.uniform(0.04, 0.12)])
        b = rng.uniform(0, 2 * math.pi)
        _card(fol, p, [math.cos(b), math.sin(b), -0.15], [0, 0, 1.0], height * 0.45, height * 0.2, DEAD_CELL, 0.5)
    for _ in range(fronds):
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 1)) * radius * 0.7
        base = np.array([math.cos(a) * rr, math.sin(a) * rr, -0.05])
        h = height * rng.uniform(0.4, 0.62) / (1 + 0.12 * (tiers - 1))
        lean = np.array([math.cos(a), math.sin(a), 0.0]) * rng.uniform(0.05, 0.2)
        top = base + (np.array([0, 0, 1.0]) + lean) * h
        bark_tube(m, "FD_Bark", np.array([base, (base + top) / 2, top]), [0.006, 0.005, 0.004], n=3)
        node, face = top, rng.uniform(0, math.pi)
        for t in range(tiers):
            plen = height * rng.uniform(0.45, 0.6) * (1 - 0.2 * t)
            for side in (1, -1):   # 左右 2 枚の羽片が弓なりに水平〜斜め下へ
                d = np.array([math.cos(face) * side, math.sin(face) * side, -rng.uniform(0.1, 0.45)])
                roll = rng.uniform(-0.45, 0.45)   # 羽片を軸のまわりに少しねじる (横からも面が見える)
                sd = np.cross([0, 0, 1.0], d)
                normal = np.array([-d[0] * d[2], -d[1] * d[2], 1.0]) + sd / max(np.linalg.norm(sd), 1e-6) * math.tan(roll)
                cell = UNDER_CELL if rng.random() < 0.15 else FRONT_CELLS[int(rng.integers(0, 2))]
                _card(fol, node, d, normal, plen, plen * 0.4, cell, 0.6)
            # 分かれ目から次の段が上へ伸びる (向きを少し回す)
            nxt = node + np.array([0, 0, height * rng.uniform(0.15, 0.22)])
            if t < tiers - 1:
                bark_tube(m, "FD_Bark", np.array([node, (node + nxt) / 2, nxt]), [0.004, 0.0035, 0.003], n=3)
            node, face = nxt, face + rng.uniform(-0.6, 0.6)
    return fol.write(m)


PLANTS = {
    # 明るい林のふちの斜面の大きな群れ / 森の中の群れ / 小さな群れ
    "SM_FD_UrajiroOpus_A": dict(make=lambda: urajiro("SM_FD_UrajiroOpus_A", 201, 1.3, 1.3, 40, 3),
                                height_m=1.2, habitat=("understory",), share=0.05, regions=REGIONS),
    "SM_FD_UrajiroOpus_B": dict(make=lambda: urajiro("SM_FD_UrajiroOpus_B", 202, 1.0, 1.0, 30, 2),
                                height_m=0.85, habitat=("understory",), share=0.05, regions=REGIONS),
    "SM_FD_UrajiroOpus_C": dict(make=lambda: urajiro("SM_FD_UrajiroOpus_C", 203, 0.7, 0.7, 20, 2),
                                height_m=0.55, habitat=("understory",), share=0.04, regions=REGIONS),
}
