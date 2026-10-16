"""イスノキ (Distylium racemosum) の形 (Claude 版)。基準は plants/notes/isunoki.md。
社寺林や暖かい山の林の常緑高木 (10〜20m)。単幹で、老木は幹の根元が大きく広がり、うねる筋があってねじれる。
地上 2〜4m で太い枝 3〜5 本に分かれ、くねりながら斜め上へ伸びる。樹冠は丸く密。若木は縦長の卵形で下枝まで葉が付く。
幹は灰白色〜淡い赤褐色で、老木はうろこ状に薄くはがれてまだら。葉は 4〜8cm の小さめの楕円で、濃い緑、つやは弱め。
"""

import math

import numpy as np

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_IsunokiOpus"
LEAF_PNG = "T_FD_Leaf_IsunokiOpus.png"
BARK = "FD_BarkIsunokiOpus"
BARK_D, BARK_N = bark.texture_names(BARK)
# 小さめの楕円の葉が枝に密に付く。濃い緑でつやは弱め (シイより少し青みが少ない)
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=420, length=(28, 42), width=0.46,
                           colors=((30, 50, 26), (38, 60, 30), (48, 70, 34), (26, 42, 22)))
# 灰白色〜淡い赤褐色。うろこ状に薄くはがれたまだら
bark.BARK_KINDS[BARK] = dict(style="plates", tile=(0.5, 0.8), seed=16,
                             top=(146, 136, 124), crack=(110, 88, 76), tint=(136, 124, 112))

MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.6, texture=LEAF_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.85, texture=BARK_D, normal=BARK_N),
}
LEAVES = {LEAF: (LEAF_PNG, lambda path: fo.leaf_texture(LEAF, path))}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto")


def _wiggle(rng, path, amount, keep=1):
    """枝の途中を横にずらしてくねらせる (両端と、根元から keep 個目までは動かさない)。"""
    path = np.array(path, float)
    for i in range(keep, len(path) - 1):
        path[i, :2] += rng.normal(size=2) * amount
    return path


def isunoki(name, seed, height, limbs, skirt, wide, old):
    """height: 樹高、limbs: 太い枝の数、skirt: 樹冠の下の端 (樹高に対する割合)、wide: 樹冠の幅の倍率、
    old: 0..1 (1 = 社寺林の老木。根元が広がり、幹が太くねじれる)。"""
    rng = Rng(seed)
    m = Mesh(name)
    crown_lo = height * skirt
    half_h = (height - crown_lo) / 2
    cz = crown_lo + half_h
    width = height * 0.33 * wide
    fol = fo.Foliage(LEAF, rng, (0, 0, cz), (width, width, half_h))
    r0 = (0.028 + 0.012 * old) * height
    fork = min(height * rng.uniform(0.16, 0.22), 4.0)
    trunk = _wiggle(rng, bezier((0, 0, -0.2), (0, 0, fork * 0.5), (0, 0, fork), 5), r0 * 0.25, keep=2)
    bark_tube(m, BARK, trunk, [r0 * (1.5 + 0.5 * old), r0 * 1.15, r0 * 1.05, r0, r0 * 0.95], n=14)
    # 老木: 根元から広がる板根のような張り出しと、幹のうねる筋
    n_root = int(3 + 3 * old)
    for j in range(n_root):
        az = 2 * math.pi * j / n_root + rng.uniform(-0.3, 0.3)
        out = r0 * (1.0 + 0.9 * old)
        p0 = np.array([math.cos(az) * out, math.sin(az) * out, 0.05])
        p1 = np.array([math.cos(az) * r0 * 0.5, math.sin(az) * r0 * 0.5, fork * (0.18 + 0.25 * old)])
        mid = np.array([p0[0] * 0.55, p0[1] * 0.55, p1[2] * 0.22])   # 根元で外へ反る (幹に沿ってせり上がる)
        bark_tube(m, BARK, bezier(p0, mid, p1, 4), [r0 * 0.42, r0 * 0.4, r0 * 0.3, r0 * 0.15], n=7)
    ends = []
    for j in range(limbs):
        az = 2 * math.pi * j / limbs + rng.uniform(-0.35, 0.35)
        reach = width * rng.uniform(0.35, 0.55)
        top = np.array([math.cos(az) * reach, math.sin(az) * reach, cz + rng.uniform(0.0, 0.4) * half_h])
        mid = np.array([math.cos(az) * reach * 0.35, math.sin(az) * reach * 0.35, (fork + top[2]) * 0.45])
        path = _wiggle(rng, bezier((0, 0, fork - 0.2), mid, top, 7), r0 * 0.5)
        bark_tube(m, BARK, path, np.linspace(r0 * 0.66, 0.04, 7), n=9)
        ends.append(top)
        # 太い枝の途中から外へ出る枝 (樹冠の表面まで)
        for t in (0.3, 0.5, 0.7, 0.85):
            p0 = path[int(t * (len(path) - 1))]
            a2 = az + rng.uniform(-1.0, 1.0)
            dz = (p0[2] - cz) / half_h
            out = width * math.sqrt(max(0.1, 1 - dz * dz)) * rng.uniform(0.55, 0.85)
            end = p0 + np.array([math.cos(a2) * out * 0.75, math.sin(a2) * out * 0.75, out * rng.uniform(0.1, 0.5)])
            bark_tube(m, BARK, np.array([p0, (p0 + end) / 2 + [0, 0, 0.12], end]), [r0 * 0.28, r0 * 0.18, 0.025], n=6)
            ends.append(end)
    # 房: 楕円体の表面近くに密に。小さめの房を多くして、輪郭を細かいでこぼこにする
    n_clumps = int(70 + 1.35 * height * height * wide)
    for _ in range(n_clumps):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.9 + 0.12
        d /= np.linalg.norm(d)
        if d[2] < -0.6 and rng.random() < 0.5:
            continue
        fp = np.array([0, 0, cz]) + d * np.array([width, width, half_h]) * rng.uniform(0.68, 0.95)
        fp[2] = max(fp[2], crown_lo * 0.75)
        if rng.random() < 0.25:
            near = min(ends, key=lambda p: float(np.sum((p - fp) ** 2)))
            bark_tube(m, BARK, np.array([near, (near + fp) / 2, fp]), [0.03, 0.02, 0.01], n=4)
        cr = width * rng.uniform(0.15, 0.24)
        fo.clump(fol, fp, cr, 8, size=cr * 1.2, up_bias=0.4)
    for p in ends[::2]:   # 奥を埋める葉
        fo.clump(fol, p, width * 0.28, 5, size=width * 0.33)
    return fol.write(m)


PLANTS = {
    # 社寺林の老木: 太くねじれた幹、丸く大きな樹冠
    "SM_FD_IsunokiOpus_A": dict(make=lambda: isunoki("SM_FD_IsunokiOpus_A", 171, 15.0, 5, 0.28, 1.05, 1.0),
                                height_m=15.0, habitat=("forest",), share=0.03, regions=REGIONS),
    # 林の中の成木
    "SM_FD_IsunokiOpus_B": dict(make=lambda: isunoki("SM_FD_IsunokiOpus_B", 172, 11.0, 4, 0.22, 0.95, 0.4),
                                height_m=11.0, habitat=("forest",), share=0.03, regions=REGIONS),
    # 若木: 縦長の卵形で、下枝まで葉が付く
    "SM_FD_IsunokiOpus_C": dict(make=lambda: isunoki("SM_FD_IsunokiOpus_C", 173, 7.0, 3, 0.08, 0.72, 0.0),
                                height_m=7.0, habitat=("forest",), share=0.02, regions=REGIONS),
}
