"""ハマヒサカキ (Eurya emarginata) の形 (Claude 版)。基準は plants/notes/hamahisakaki.md。
海岸の崖や岩場のいちばん海側に生える常緑の低木 (1〜3m)。根元から何本もの枝が出て、細い枝が水平に何段も重なる。
潮風で風上が刈り込まれ、上面が平らで風下 (+X) へ傾いた形になる。岬では 1m 以下で地面をはう。
葉は 2〜4cm の小さな倒卵形で、枝の左右に 2 列に (羽根のように) 平らに並ぶ。濃い緑でつやがある。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_HamahisakakiOpus"
LEAF_PNG = "T_FD_Leaf_HamahisakakiOpus.png"
COLORS = ((26, 50, 22), (34, 60, 26), (44, 72, 30), (22, 42, 20))
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.5, colors=COLORS)

MATERIALS = {LEAF: dict(color=(1, 1, 1), roughness=0.45, texture=LEAF_PNG, alpha=True)}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto", "hokuriku")


def _leaf(base, angle, length, width=0.55, n=8):
    """小さな倒卵形の葉 (先が丸く、少しへこむ)。"""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for side in (1, -1):
        for t in (np.linspace(0, 1, n) if side == 1 else np.linspace(1, 0, n)):
            w = width * length * 0.5 * math.sin(math.pi * t ** 0.7) ** 0.6 * (0.45 + 0.6 * t) * side
            if t > 0.97:
                w *= 0.6   # 先のへこみ
            pts.append((base[0] + t * length * ca - w * sa, base[1] + t * length * sa + w * ca))
    return pts


def leaf_texture(path, size=fo.TEXTURE_SIZE):
    """2x2 の小枝。主軸から左右に側枝が出て、どの枝にも小さな葉が左右 2 列に平らに並ぶ (羽根のような枝)。"""
    r = random.Random("HamahisakakiOpus")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS

    def spray(x0, y0, ang, length, s, depth):
        steps = 9
        pts = [(x0, y0)]
        for k in range(1, steps + 1):
            a = ang + math.sin(k * 0.7) * 0.06
            pts.append((pts[-1][0] + math.cos(a) * length / steps, pts[-1][1] + math.sin(a) * length / steps))
        draw.line(pts, fill=fo.TWIG_COLOR, width=max(2, s // 220))
        for k, p in enumerate(pts[1:], 1):
            for side in (1, -1):   # 左右 2 列
                la = ang + side * r.uniform(0.75, 1.05)
                ln = s * r.uniform(0.085, 0.11) * (0.7 + 0.3 * (1 - k / steps))
                k_shade = 1.1 - 0.3 * ((p[1] % s) / s)
                col = tuple(int(min(255, c * k_shade)) for c in fo._jitter(r.choice(COLORS), r))
                draw.polygon(_leaf(p, la, ln), fill=col)
            if depth and k in (2, 4, 6) and r.random() < 0.8:
                side = 1 if k % 4 == 2 else -1
                spray(p[0], p[1], ang + side * r.uniform(0.6, 0.9), length * r.uniform(0.4, 0.5), s, depth - 1)

    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy, s = i * cell, j * cell, cell
            spray(ox + s * 0.5, oy + s * 0.97, -math.pi / 2 + r.uniform(-0.15, 0.15), s * 0.86, s, 2)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


LEAVES = {LEAF: (LEAF_PNG, leaf_texture)}


def hamahisakaki(name, seed, height, width, stems, tiers, wind):
    """height: 樹高 (風上の端)、width: 樹冠の半径、tiers: 水平に重なる枝の段の数、wind: 0..1 (1 = 岬の強い風)。
    風上 (-X) ほど低く、風下 (+X) へ長く伸びる。上面は平らに刈り込まれる。"""
    rng = Rng(seed)
    m = Mesh(name)
    lean = min(width * 0.25 * wind, height * 0.15)   # 樹冠の中心は風下へずれる
    rx, ry = width * (1 + 0.15 * wind), width * 0.85
    fol = fo.Foliage(LEAF, rng, (lean, 0, height * 0.55), (rx, ry, height * 0.55))

    def top_at(x):   # 刈り込まれた上面: ほぼ平らで、風上 (-X) の側はくさびのように地面へ下がる
        u = (x - lean) / rx
        return height * (1.0 - 0.06 * wind * u - 0.8 * wind * max(0.0, -u) ** 1.2)

    stem_tops = []
    for j in range(stems):
        az = 2 * math.pi * j / stems + rng.uniform(-0.4, 0.4)
        out = rng.uniform(0.3, 0.6)
        top = np.array([math.cos(az) * rx * out + lean * 0.8, math.sin(az) * ry * out, 0.0])
        top[2] = top_at(top[0]) * rng.uniform(0.55, 0.8)
        base = np.array([math.cos(az) * 0.05, math.sin(az) * 0.05, -0.12])
        mid = base + (top - base) * np.array([0.3, 0.3, 0.55]) + [lean * 0.15, 0, 0]
        bark_tube(m, "FD_Bark", bezier(base, mid, top, 5), np.linspace(0.01 * height + 0.02, 0.01, 5), n=6)
        stem_tops.append((mid, top))
    # 枝の段: 水平な薄い層が何段も重なる。外側 (樹冠の縁) ほど層が見え、縁は上から地面近くまで葉でおおわれる
    per_tier = int(8 + 14 * width * width / tiers)
    for t in range(tiers):
        f = (t + 0.5) / tiers
        for _ in range(per_tier):
            a = rng.uniform(0, 2 * math.pi)
            rr = math.sqrt(rng.uniform(0.35, 1.0)) * (0.75 + 0.25 * f)
            x, y = lean + math.cos(a) * rx * rr, math.sin(a) * ry * rr
            top = top_at(x)
            z = max(0.06, top * (0.15 + 0.8 * f) + rng.uniform(-0.05, 0.05) * height)
            z = min(z, top - 0.05 * height)
            p = np.array([x, y, z])
            if rng.random() < 0.3:
                mid, stop = stem_tops[int(rng.integers(0, len(stem_tops)))]
                bark_tube(m, "FD_Bark", np.array([mid, (mid + p) / 2, p]), [0.014, 0.01, 0.006], n=4)
            cr = width * rng.uniform(0.15, 0.23)
            fo.clump(fol, p, cr, 5, size=cr * 1.6, flat=0.35, up_bias=0.9)
    # 上面: 刈り込まれた面をそろえて埋める
    for _ in range(int(22 + 34 * width * width)):
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 0.9))
        x, y = lean + math.cos(a) * rx * rr, math.sin(a) * ry * rr
        p = np.array([x, y, max(0.06, top_at(x) - rng.uniform(0.02, 0.08) * height)])
        cr = width * rng.uniform(0.14, 0.2)
        fo.clump(fol, p, cr, 4, size=cr * 1.6, flat=0.3, up_bias=1.0)
    return fol.write(m)


PLANTS = {
    "SM_FD_HamahisakakiOpus_A": dict(make=lambda: hamahisakaki("SM_FD_HamahisakakiOpus_A", 121, 2.3, 1.5, 6, 4, 0.5),
                                     height_m=2.3, habitat=("coast",), share=0.04, regions=REGIONS),
    "SM_FD_HamahisakakiOpus_B": dict(make=lambda: hamahisakaki("SM_FD_HamahisakakiOpus_B", 122, 1.4, 1.5, 7, 3, 0.9),
                                     height_m=1.4, habitat=("coast",), share=0.035, regions=REGIONS),
    "SM_FD_HamahisakakiOpus_C": dict(make=lambda: hamahisakaki("SM_FD_HamahisakakiOpus_C", 123, 0.8, 1.1, 5, 2, 1.0),
                                     height_m=1.0, habitat=("coast",), share=0.03, regions=REGIONS),
}
