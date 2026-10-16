"""ヤマモモ (Morella rubra)。関東より西の暖かい海に近い山や社寺林に多い常緑高木 (九州・四国・中国・関西・中部・関東)。
濃い緑の細長い葉がびっしり付き、樹冠はこんもり丸く、幹は低い所から数本に分かれる。

植物のファイルの見本 (書き方は tools/map_kit/AGENTS.md)。葉の絵は foliage.py の描き方 (style="broad") を使い、
葉の形と色だけ変えている。
"""

import math

import numpy as np

import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_Yamamomo"
LEAF_PNG = "T_FD_Leaf_Yamamomo.png"

# 葉の絵の描き方 (foliage.py の LEAF_KINDS と同じ書き方)。ヤマモモの葉は細長く、色はシイより濃い
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=360, length=(34, 50), width=0.3,
                           colors=((30, 54, 20), (40, 68, 24), (54, 84, 30), (24, 44, 18)))

MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.6, texture=LEAF_PNG, alpha=True),
}
LEAVES = {
    LEAF: (LEAF_PNG, lambda path: fo.leaf_texture(LEAF, path)),
}


def yamamomo(name, seed, height=8.0):
    """低い所で 3〜4 本に分かれた幹の上に、丸い樹冠。房は樹冠の表面近くに密に並べる。"""
    rng = Rng(seed)
    m = Mesh(name)
    half_h, big_r = height * 0.44, height * 0.46
    cz = height - half_h
    fork_z = height * 0.12
    r0 = 0.03 * height
    bark_tube(m, "FD_Bark", bezier((0, 0, -0.3), (0, 0, fork_z * 0.5), (0, 0, fork_z), 4), [r0 * 1.4, r0 * 1.2, r0 * 1.05, r0], n=14)
    fol = fo.Foliage(LEAF, rng, (0, 0, cz), (big_r, big_r, half_h))
    stems = int(rng.integers(3, 5))
    for j in range(stems):
        az = 2 * math.pi * j / stems + rng.uniform(-0.3, 0.3)
        top = np.array([math.cos(az) * big_r * 0.38, math.sin(az) * big_r * 0.38, cz + rng.uniform(-0.25, 0.15) * half_h])
        base = np.array([0, 0, fork_z])
        mid = base + (top - base) * 0.5 + [0, 0, 0.3]
        bark_tube(m, "FD_Bark", bezier(base - [0, 0, 0.2], mid, top, 6), np.linspace(r0 * 0.75, 0.05, 6), n=8)
        sr = big_r * rng.uniform(0.5, 0.62)
        for _ in range(int(rng.integers(16, 21))):
            d = rng.normal(size=3)
            d[2] = d[2] * 0.9 + 0.2
            d /= np.linalg.norm(d)
            fp = top + d * np.array([sr, sr, sr * 0.95]) * rng.uniform(0.55, 0.9)
            if rng.random() < 0.4:
                bark_tube(m, "FD_Bark", np.array([top, (top + fp) / 2 + [0, 0, 0.1], fp]), [0.045, 0.03, 0.018], n=5)
            fo.clump(fol, fp, sr * rng.uniform(0.3, 0.4), 10, size=sr * 0.5)
        fo.clump(fol, top, sr * 0.55, 10, size=sr * 0.55)  # 奥を埋める葉
    return fol.write(m)


REGIONS = ("kyushu", "shikoku", "chugoku", "kansai", "chubu", "kanto")
PLANTS = {
    "SM_FD_Yamamomo_A": dict(make=lambda: yamamomo("SM_FD_Yamamomo_A", 71, 8.0), height_m=8.0,
                             habitat=("forest", "coast"), share=0.05, regions=REGIONS),
    "SM_FD_Yamamomo_B": dict(make=lambda: yamamomo("SM_FD_Yamamomo_B", 72, 6.0), height_m=6.0,
                             habitat=("forest",), share=0.04, regions=REGIONS),
}
