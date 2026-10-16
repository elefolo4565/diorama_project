"""ウバメガシ (Quercus phillyraeoides) の株立ちの低木の形 (Claude 版)。背の高い木の形は ubamegashi/ (Codex 版) で、両方を半分ずつ置く。
海岸の崖や岩場の常緑樹。根元から何本もの細い幹が立ち、小さく厚い葉が地面近くまでびっしり付く。
潮風の当たる所では、風上の枝が育たず、樹冠が風下へ流れて低く刈り込まれたような形になる。
"""

import math

import numpy as np

import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_UbamegashiOpus"
LEAF_PNG = "T_FD_Leaf_UbamegashiOpus.png"

# 葉は小さく (2〜3cm) 丸みのある楕円で、濃いつやのある緑。小枝 1 本にたくさん付く
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=520, length=(20, 28), width=0.62,
                           colors=((30, 52, 22), (40, 64, 26), (52, 78, 32), (62, 82, 40)))

MATERIALS = {LEAF: dict(color=(1, 1, 1), roughness=0.5, texture=LEAF_PNG, alpha=True)}
LEAVES = {LEAF: (LEAF_PNG, lambda path: fo.leaf_texture(LEAF, path))}
REGIONS = ("kyushu", "shikoku", "chugoku", "kansai", "chubu", "kanto")


def ubamegashi(name, seed, height, width, stems, wind=0.0, skirt=0.15):
    """height: 樹高、width: 樹冠の半径、stems: 根元から立つ幹の数、wind: 風下への流れ (0..1)、
    skirt: 葉が始まる高さ (樹高に対する割合。小さいほど地面近くまで茂る)。風下は +X。"""
    rng = Rng(seed)
    m = Mesh(name)
    half_h = height * (1 - skirt) / 2
    cz = height - half_h
    lean = np.array([width * 0.42 * wind, 0.0])
    fol = fo.Foliage(LEAF, rng, (lean[0], lean[1], cz), (width, width * 0.85, half_h))
    tops = []
    for j in range(stems):
        az = 2 * math.pi * j / stems + rng.uniform(-0.4, 0.4)
        base = np.array([math.cos(az) * 0.12, math.sin(az) * 0.12, -0.2])
        spread = rng.uniform(0.35, 0.7) * width
        top = np.array([math.cos(az) * spread + lean[0] * rng.uniform(0.8, 1.4),
                        math.sin(az) * spread * 0.85 + lean[1], cz + rng.uniform(-0.35, 0.35) * half_h])
        mid = base + (top - base) * 0.45 + np.array([lean[0] * 0.3, 0, -0.1 * height])
        r0 = 0.018 * height * rng.uniform(0.8, 1.2)
        bark_tube(m, "FD_Bark", bezier(base, mid, top, 6), np.linspace(r0, 0.03, 6), n=7)
        tops.append((top, mid))
    # 房: 樹冠の楕円体の表面近く。風上 (-X) の上の方は潮風で育たないので減らす
    n_clumps = int(70 * width * width / 4 + (50 if height >= 3 else 24))
    for _ in range(n_clumps):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.85 + 0.15
        d /= np.linalg.norm(d)
        if wind > 0 and d[0] < -0.2 and d[2] > 0.2 and rng.random() < wind * 0.8:
            continue
        r = rng.uniform(0.55, 0.92)
        fp = np.array([lean[0], lean[1], cz]) + d * np.array([width, width * 0.85, half_h]) * r
        if wind > 0:
            fp[2] -= wind * 0.25 * half_h * max(0.0, -d[0])   # 風上ほど低く刈り込まれる
        fp[2] = max(fp[2], height * skirt * 0.6)
        top, mid = tops[int(rng.integers(0, len(tops)))]
        if rng.random() < 0.35:
            bark_tube(m, "FD_Bark", np.array([mid, (mid + fp) / 2 + [0, 0, 0.1], fp]), [0.03, 0.02, 0.012], n=5)
        cr = min(width, half_h) * rng.uniform(0.28, 0.4)
        fo.clump(fol, fp, cr, 11 if height >= 3 else 9, size=cr * 1.15, up_bias=0.3)
    for top, _ in tops:  # 奥を埋める葉
        fo.clump(fol, top, min(width, half_h) * 0.55, 16, size=min(width, half_h) * 0.55)
    return fol.write(m)


PLANTS = {
    "SM_FD_UbamegashiOpus_A": dict(make=lambda: ubamegashi("SM_FD_UbamegashiOpus_A", 81, 4.8, 2.4, 5, wind=0.15, skirt=0.2),
                                   height_m=4.8, habitat=("coast", "ridge"), share=0.02, regions=REGIONS),
    "SM_FD_UbamegashiOpus_B": dict(make=lambda: ubamegashi("SM_FD_UbamegashiOpus_B", 82, 3.4, 2.3, 6, wind=0.75, skirt=0.12),
                                   height_m=3.4, habitat=("coast", "ridge"), share=0.0175, regions=REGIONS),
    "SM_FD_UbamegashiOpus_C": dict(make=lambda: ubamegashi("SM_FD_UbamegashiOpus_C", 83, 2.4, 1.5, 7, wind=0.4, skirt=0.04),
                                   height_m=2.4, habitat=("coast",), share=0.0125, regions=REGIONS),
}
