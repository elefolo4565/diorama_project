"""ヤブツバキ (Camellia japonica) の形 (Claude 版)。暖かい地方の林の中や社寺林に生える常緑の小高木 (3〜8m)。
幹は灰白色でなめらか。低い所から 1〜3 本に分かれ、枝は斜め上へ伸びる。樹冠は縦長の卵形で、こんもり密に茂る。
葉は厚くつやのある濃い緑の楕円形。冬から春 (12〜4 月) に、赤い花が葉の間にたくさん咲く。
花の咲く季節 (冬・春) は花の付いた葉の絵の形 (`_Hana`) を、同じ所に入れ替えて出す。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_YabutsubakiOpus"
LEAF_PNG = "T_FD_Leaf_YabutsubakiOpus.png"
HANA = "FD_Leaf_YabutsubakiOpusHana"
HANA_PNG = "T_FD_Leaf_YabutsubakiOpusHana.png"
BARK = "FD_BarkYabutsubakiOpus"
BARK_D, BARK_N = bark.texture_names(BARK)

# 葉は 5〜10cm の楕円形で厚くつやがある。シイより濃く、少し青みのある緑
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=330, length=(40, 56), width=0.44,
                           colors=((22, 44, 20), (30, 56, 26), (42, 70, 34), (18, 36, 18)))
fo.LEAF_KINDS[HANA] = dict(fo.LEAF_KINDS[LEAF], texture=HANA_PNG)
# 樹皮は灰白色でなめらか (細かいすじとまだらがあるだけ)
bark.BARK_KINDS[BARK] = dict(style="culm", tile=(0.4, 1.0), seed=11,
                             top=(150, 146, 134), crack=(104, 100, 92), tint=(128, 126, 112))


def hana_texture(path, size=fo.TEXTURE_SIZE):
    """葉の絵の上に、ヤブツバキの花 (筒のように半ば開いた赤い 5 枚の花びらと、黄色いおしべの束) を描く。"""
    fo.leaf_texture(HANA, path, size)
    img = Image.open(path).convert("RGBA")
    alpha = np.asarray(img)[:, :, 3]
    draw = ImageDraw.Draw(img)
    r = random.Random("YabutsubakiOpusHana")
    cell = size // fo.CELLS
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            placed = 0
            for _ in range(200):
                if placed >= 4:
                    break
                x = i * cell + r.uniform(0.15, 0.85) * cell
                y = j * cell + r.uniform(0.1, 0.75) * cell
                if alpha[int(y), int(x)] < 200:   # 葉のある所にだけ咲かせる
                    continue
                rad = cell * r.uniform(0.035, 0.048)
                red = (r.randint(170, 200), r.randint(18, 34), r.randint(30, 46))
                for k in range(5):   # 花びら
                    a = 2 * math.pi * k / 5 + r.uniform(-0.2, 0.2)
                    px, py = x + math.cos(a) * rad * 0.5, y + math.sin(a) * rad * 0.5
                    col = tuple(int(c * r.uniform(0.85, 1.05)) for c in red)
                    draw.ellipse([px - rad * 0.62, py - rad * 0.62, px + rad * 0.62, py + rad * 0.62], fill=col + (255,))
                draw.ellipse([x - rad * 0.3, y - rad * 0.3, x + rad * 0.3, y + rad * 0.3], fill=(226, 200, 92, 255))
                placed += 1
    img.save(path)


MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.4, texture=LEAF_PNG, alpha=True),
    HANA: dict(color=(1, 1, 1), roughness=0.4, texture=HANA_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.8, texture=BARK_D, normal=BARK_N),
}
LEAVES = {
    LEAF: (LEAF_PNG, lambda path: fo.leaf_texture(LEAF, path)),
    HANA: (HANA_PNG, hana_texture),
}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto", "tohoku", "hokuriku")


def yabutsubaki(name, seed, height, trunks, slim=1.0, leaf=LEAF):
    """height: 樹高、trunks: 低い所で分かれる幹の数、slim: 樹冠の細さ (大きいほど細長い)。
    leaf を変えても形は同じ (乱数の順番が同じ) なので、花の形と葉だけの形が同じ所でぴったり重なる。"""
    rng = Rng(seed)
    m = Mesh(name)
    crown_lo = height * 0.1                        # 樹冠の下の端。下枝が低くまで残り、幹は根元の少しだけ見える
    half_h = (height - crown_lo) / 2
    cz = crown_lo + half_h
    width = height * 0.25 / slim
    fol = fo.Foliage(leaf, rng, (0, 0, cz), (width, width, half_h))
    r0 = 0.022 * height
    split = height * rng.uniform(0.08, 0.16)
    bark_tube(m, BARK, bezier((0, 0, -0.25), (0, 0, split * 0.5), (0, 0, split), 3), [r0 * 1.35, r0 * 1.1, r0], n=10)
    leaders = []
    for j in range(trunks):
        az = 2 * math.pi * j / trunks + rng.uniform(-0.3, 0.3)
        off = 0.0 if trunks == 1 else width * 0.28
        top = np.array([math.cos(az) * off, math.sin(az) * off, height * rng.uniform(0.86, 0.93)])
        mid = np.array([math.cos(az) * off * 0.6, math.sin(az) * off * 0.6, (split + top[2]) * 0.45])
        path = bezier((0, 0, split - 0.1), mid, top, 7)
        radii = np.linspace(r0 * (1.0 if trunks == 1 else 0.75), 0.02, 7)
        bark_tube(m, BARK, path, radii, n=8)
        leaders.append(path)
    # 枝: 幹のいろいろな高さから斜め上へ。先に房を付け、樹冠の表面を作る
    n_branch = int(14 + 2.2 * height)
    tips = []
    for _ in range(n_branch):
        path = leaders[int(rng.integers(0, len(leaders)))]
        t = rng.uniform(0.08, 0.9) ** 0.8
        k = min(int(t * (len(path) - 1)), len(path) - 2)
        start = path[k] + (path[k + 1] - path[k]) * (t * (len(path) - 1) - k)
        az = rng.uniform(0, 2 * math.pi)
        # 卵形の表面のその高さでの半径まで伸ばす
        dz = (start[2] - cz) / half_h
        reach = width * math.sqrt(max(0.05, 1 - dz * dz)) * rng.uniform(0.6, 0.85)
        end = start + np.array([math.cos(az) * reach, math.sin(az) * reach, reach * rng.uniform(0.35, 0.8)])
        end[2] = min(end[2], height * 0.97)
        bark_tube(m, BARK, np.array([start, (start + end) / 2 + [0, 0, 0.1], end]), [0.04, 0.025, 0.012], n=5)
        tips.append(end)
    # 房: 楕円体の表面近く。下の方はまばらにし、縁をばらす
    n_clumps = int(30 + 5.5 * height * height / slim)
    for _ in range(n_clumps):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.9 + 0.12
        d /= np.linalg.norm(d)
        if d[2] < -0.6 and rng.random() < 0.6:
            continue
        fp = np.array([0, 0, cz]) + d * np.array([width, width, half_h]) * rng.uniform(0.62, 0.92)
        near = min(tips, key=lambda p: float(np.sum((p - fp) ** 2)))
        if rng.random() < 0.3:
            bark_tube(m, BARK, np.array([near, (near + fp) / 2, fp]), [0.015, 0.011, 0.007], n=4)
        cr = width * rng.uniform(0.22, 0.32)
        fo.clump(fol, fp, cr, 9, size=cr * 1.15, up_bias=0.4)
    for p in tips[::2]:   # 奥を埋める葉
        fo.clump(fol, p, width * 0.3, 5, size=width * 0.35)
    return fol.write(m)


LEAF_SEASONS = 2 | 4    # 夏・秋は葉だけ
HANA_SEASONS = 1 | 8    # 冬・春は花が咲く
SHAPES = {"A": (101, 7.0, 1, 1.0), "B": (102, 5.2, 2, 0.9), "C": (103, 3.4, 1, 1.3)}
SHARES = {"A": 0.03, "B": 0.03, "C": 0.02}
PLANTS = {}
for _k, (_seed, _h, _tr, _slim) in SHAPES.items():
    _base = f"SM_FD_YabutsubakiOpus_{_k}"
    PLANTS[_base] = dict(make=lambda s=_seed, h=_h, t=_tr, sl=_slim, n=_base: yabutsubaki(n, s, h, t, sl),
                         height_m=_h, habitat=("forest",), share=SHARES[_k], seasons=LEAF_SEASONS, regions=REGIONS)
    PLANTS[_base + "_Hana"] = dict(
        make=lambda s=_seed, h=_h, t=_tr, sl=_slim, n=_base + "_Hana": yabutsubaki(n, s, h, t, sl, leaf=HANA),
        height_m=_h, habitat=("forest",), share=SHARES[_k], seasons=HANA_SEASONS, regions=REGIONS, place_with=_base)
