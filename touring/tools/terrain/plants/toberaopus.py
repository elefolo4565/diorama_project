"""トベラ (Pittosporum tobira) の形 (Claude 版)。海岸の岩場や砂浜の後ろに生える常緑の低木 (1〜3m)。
根元から何本もの幹が立ち、横に広いお椀を伏せたような丸い樹冠が地面近くまで下がる。
葉は枝先に輪のように集まって付き (ロゼット)、表面がつやのある明るめの緑。そのため樹冠の表面は小さな房のでこぼこになる。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_ToberaOpus"
LEAF_PNG = "T_FD_Leaf_ToberaOpus.png"

# 葉は 5〜10cm の、先が丸く広い倒卵形。つやのある黄緑がかった緑
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=300, length=(40, 58), width=0.5,
                           colors=((46, 74, 26), (60, 92, 32), (76, 108, 40), (40, 62, 24)))

MATERIALS = {LEAF: dict(color=(1, 1, 1), roughness=0.45, texture=LEAF_PNG, alpha=True)}


def _obovate(base, angle, length, width, n=10):
    """先が丸く広い倒卵形の葉 (付け根が細く、先の 3 分の 2 あたりがいちばん広い)。"""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for side in (1, -1):
        for t in (np.linspace(0, 1, n) if side == 1 else np.linspace(1, 0, n)):
            w = width * length * 0.5 * math.sin(math.pi * t ** 0.75) ** 0.7 * (0.35 + 0.75 * t) * side
            pts.append((base[0] + t * length * ca - w * sa, base[1] + t * length * sa + w * ca))
    return pts


def leaf_texture(path, size=fo.TEXTURE_SIZE):
    """2x2 の小枝。1 本の枝が 3〜4 本に分かれ、それぞれの枝先に葉が輪 (ロゼット) になって付く。"""
    r = random.Random("ToberaOpus")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    colors = fo.LEAF_KINDS[LEAF]["colors"]
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy, s = i * cell, j * cell, cell
            root = (ox + s * 0.5, oy + s * 0.98)
            tips = []
            fork = (root[0], root[1] - s * 0.3)
            draw.line([root, fork], fill=fo.TWIG_COLOR, width=max(3, s // 100))
            for k in range(6):   # 上の 4 本と、横へ低く出る 2 本
                low = k >= 4
                a = (-math.pi / 2 + (k - 1.5) * 0.42 if not low else (-0.25 if k == 4 else -math.pi + 0.25))
                a += r.uniform(-0.12, 0.12)
                ln = s * (r.uniform(0.34, 0.44) if not low else r.uniform(0.26, 0.32))
                start = fork if not low else (root[0], root[1] - s * 0.16)
                tip = (start[0] + math.cos(a) * ln, start[1] + math.sin(a) * ln)
                draw.line([start, tip], fill=fo.TWIG_COLOR, width=max(2, s // 140))
                tips.append(tip)
            tips.sort(key=lambda t: -t[1])
            for tip in tips:   # 下の輪から描き、上の輪の葉を手前にする
                n = r.randint(8, 11)
                for q in range(n):
                    a = 2 * math.pi * q / n + r.uniform(-0.2, 0.2)
                    ln = s * r.uniform(0.17, 0.23) * (0.75 if math.sin(a) > 0.3 else 1.0)
                    k = 1.1 - 0.3 * ((tip[1] - oy) / s)
                    col = tuple(int(min(255, c * k)) for c in fo._jitter(r.choice(colors), r))
                    poly = _obovate(tip, a, ln, 0.5)
                    draw.polygon(poly, fill=col)
                    end = (tip[0] + math.cos(a) * ln * 0.9, tip[1] + math.sin(a) * ln * 0.9)
                    draw.line([tip, end], fill=tuple(int(c * 0.8) for c in col), width=2)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


LEAVES = {LEAF: (LEAF_PNG, leaf_texture)}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto", "tohoku", "hokuriku")


def tobera(name, seed, height, width, stems, wind=0.0):
    """height: 樹高、width: 樹冠の半径 (樹高より広い)、stems: 根元から立つ幹の数、wind: 潮風で風上 (-X) が刈り込まれる度合い。"""
    rng = Rng(seed)
    m = Mesh(name)
    half_h = height * 0.55
    cz = height - half_h          # 楕円体の中心。下の端はほぼ地面
    shift = width * 0.25 * wind   # 風下 (+X) へ寄る
    fol = fo.Foliage(LEAF, rng, (shift, 0, cz), (width, width * 0.9, half_h))
    tips = []
    for j in range(stems):
        az = 2 * math.pi * j / stems + rng.uniform(-0.4, 0.4)
        base = np.array([math.cos(az) * 0.06, math.sin(az) * 0.06, -0.15])
        out = rng.uniform(0.45, 0.75) * width
        top = np.array([math.cos(az) * out + shift, math.sin(az) * out * 0.9, cz + rng.uniform(0.0, 0.5) * half_h])
        mid = base + (top - base) * np.array([0.35, 0.35, 0.6])   # 根元から斜めに開く
        bark_tube(m, "FD_Bark", bezier(base, mid, top, 5), np.linspace(0.012 * height + 0.015, 0.012, 5), n=6)
        tips.append((mid, top))
    # 房 (枝先のロゼット): 楕円体の表面近くに小さく密に並べる。下半分は少しまばらにして縁をばらす
    n_clumps = int(36 * width * width + 34)
    for _ in range(n_clumps):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.8 + 0.25
        d /= np.linalg.norm(d)
        if d[2] < -0.35 and rng.random() < 0.35:
            continue
        if wind > 0 and d[0] < -0.1 and d[2] > 0.0 and rng.random() < wind * 0.7:
            continue
        r = rng.uniform(0.66, 0.9)
        fp = np.array([shift, 0, cz]) + d * np.array([width, width * 0.9, half_h]) * r
        if wind > 0:
            fp[2] -= wind * 0.3 * half_h * max(0.0, -d[0]) * max(0.0, d[2])
        fp[2] = max(fp[2], 0.06)
        mid, top = tips[int(rng.integers(0, len(tips)))]
        if rng.random() < 0.25:
            bark_tube(m, "FD_Bark", np.array([mid, (mid + fp) / 2, fp]), [0.018, 0.012, 0.008], n=4)
        cr = min(width, half_h) * rng.uniform(0.2, 0.3)
        fo.clump(fol, fp, cr, 6, size=cr * 1.3, up_bias=0.6)
    for mid, top in tips:  # 奥を埋める葉
        fo.clump(fol, top, min(width, half_h) * 0.45, 10, size=min(width, half_h) * 0.5)
    return fol.write(m)


PLANTS = {
    "SM_FD_ToberaOpus_A": dict(make=lambda: tobera("SM_FD_ToberaOpus_A", 91, 2.6, 1.7, 6, wind=0.1),
                               height_m=2.6, habitat=("coast",), share=0.04, regions=REGIONS),
    "SM_FD_ToberaOpus_B": dict(make=lambda: tobera("SM_FD_ToberaOpus_B", 92, 1.8, 1.4, 7, wind=0.7),
                               height_m=1.8, habitat=("coast",), share=0.035, regions=REGIONS),
    "SM_FD_ToberaOpus_C": dict(make=lambda: tobera("SM_FD_ToberaOpus_C", 93, 1.1, 0.8, 5, wind=0.3),
                               height_m=1.1, habitat=("coast",), share=0.025, regions=REGIONS),
}
