"""マテバシイ (Lithocarpus edulis) の形 (Claude 版)。九州・沖縄の海に近い林や社寺林に多い常緑高木 (8〜15m)。
根元から何本もの太い幹が斜めに立つ株立ちになりやすく、幹ごとの丸い樹冠が集まって、でこぼこした大きなドーム形になる。
幹は暗い灰色でなめらか。葉は 10〜20cm と大きく厚い細長い楕円形で、枝先に集まって付く。明るめの黄みがかった緑。
"""

import math

import numpy as np

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_MatebashiiOpus"
LEAF_PNG = "T_FD_Leaf_MatebashiiOpus.png"
BARK = "FD_BarkMatebashiiOpus"
BARK_D, BARK_N = bark.texture_names(BARK)

# 葉は大きく細長い (他の木の 1.5 倍)。枝 1 本あたりの数は少なめ
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=190, length=(62, 86), width=0.34,
                           colors=((48, 72, 26), (62, 88, 32), (78, 102, 38), (40, 60, 24)))
# 樹皮は暗い灰色でなめらか、細い縦すじ
bark.BARK_KINDS[BARK] = dict(style="culm", tile=(0.6, 1.2), seed=12,
                             top=(98, 96, 90), crack=(62, 60, 56), tint=(84, 86, 78))

MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.45, texture=LEAF_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.8, texture=BARK_D, normal=BARK_N),
}
LEAVES = {LEAF: (LEAF_PNG, lambda path: fo.leaf_texture(LEAF, path))}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
# 自然に生えるのは九州・沖縄。四国・中国・関西・関東の海沿いのものは植えられて広がったものが多いので入れない
REGIONS = ("kyushu", "okinawa")


def matebashii(name, seed, height, trunks, spread, wind=0.0):
    """height: 樹高、trunks: 根元から立つ幹の数、spread: 樹冠全体の半径、wind: 潮風で風上 (-X) が低く刈り込まれる度合い。"""
    rng = Rng(seed)
    m = Mesh(name)
    shift = spread * 0.3 * wind
    fol = fo.Foliage(LEAF, rng, (shift, 0, height * 0.6), (spread, spread, height * 0.42))
    lobes = []
    for j in range(trunks):
        az = 2 * math.pi * j / trunks + rng.uniform(-0.35, 0.35)
        lean = rng.uniform(0.22, 0.45) * spread
        # 真ん中の幹ほど高く、外の幹ほど低く斜め
        tall = height * (0.92 - 0.18 * (lean / spread)) * rng.uniform(0.92, 1.0)
        if wind > 0:
            tall *= 1 - wind * 0.25 * max(0.0, -math.cos(az))
        top = np.array([math.cos(az) * lean + shift, math.sin(az) * lean, tall * 0.42])   # 幹はここで枝に分かれ、樹冠の中へ入る
        base = np.array([math.cos(az) * 0.15, math.sin(az) * 0.15, -0.3])
        mid = base + (top - base) * np.array([0.35, 0.35, 0.5])
        r0 = 0.03 * height * rng.uniform(0.75, 1.0)
        path = bezier(base, mid, top, 7)
        bark_tube(m, BARK, path, np.linspace(r0 * 1.15, r0 * 0.35, 7), n=10)
        lr = spread * rng.uniform(0.5, 0.62)          # その幹の樹冠 (房の塊) の半径
        lh = tall - top[2]
        lobes.append((top + [math.cos(az) * lr * 0.25, math.sin(az) * lr * 0.25, lh * 0.5], lr, lh * 0.56))
        # 幹の先で 3〜4 本の太い枝に分かれる
        for _ in range(int(rng.integers(3, 5))):
            a2 = az + rng.uniform(-1.3, 1.3)
            end = top + np.array([math.cos(a2) * lr * 0.7, math.sin(a2) * lr * 0.7, lh * rng.uniform(0.35, 0.75)])
            bark_tube(m, BARK, np.array([top, (top + end) / 2 + [0, 0, 0.3], end]), [r0 * 0.35, r0 * 0.22, 0.03], n=6)
    # 房: 幹ごとの樹冠の表面近く。ほかの幹の樹冠の中に深く入る房は減らす (外から見えないので)
    per_lobe = int(24 + 3.2 * height)
    for center, lr, lh in lobes:
        for _ in range(per_lobe):
            d = rng.normal(size=3)
            d[2] = d[2] * 0.9 + 0.2
            d /= np.linalg.norm(d)
            if d[2] < -0.45 and rng.random() < 0.55:
                continue
            fp = center + d * np.array([lr, lr, lh]) * rng.uniform(0.62, 0.95)
            inside = sum(1 for c2, r2, h2 in lobes if c2 is not center and
                         np.sum(((fp - c2) / [r2, r2, h2]) ** 2) < 0.55)
            if inside and rng.random() < 0.7:
                continue
            if rng.random() < 0.3:
                bark_tube(m, BARK, np.array([center - [0, 0, lh * 0.3], (center + fp) / 2, fp]), [0.04, 0.025, 0.012], n=4)
            cr = lr * rng.uniform(0.28, 0.4)
            fo.clump(fol, fp, cr, 9, size=cr * 1.2, up_bias=0.5)
        fo.clump(fol, center, lr * 0.5, 10, size=lr * 0.55)   # 奥を埋める葉
    return fol.write(m)


PLANTS = {
    "SM_FD_MatebashiiOpus_A": dict(make=lambda: matebashii("SM_FD_MatebashiiOpus_A", 111, 11.0, 5, 5.2),
                                   height_m=11.0, habitat=("forest",), share=0.04, regions=REGIONS),
    "SM_FD_MatebashiiOpus_B": dict(make=lambda: matebashii("SM_FD_MatebashiiOpus_B", 112, 8.5, 3, 3.6),
                                   height_m=8.5, habitat=("forest",), share=0.03, regions=REGIONS),
    "SM_FD_MatebashiiOpus_C": dict(make=lambda: matebashii("SM_FD_MatebashiiOpus_C", 113, 6.5, 4, 4.0, wind=0.7),
                                   height_m=6.5, habitat=("coast",), share=0.03, regions=REGIONS),
}
