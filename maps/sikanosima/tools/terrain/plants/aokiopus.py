"""アオキ (Aucuba japonica) の形 (Claude 版)。基準は plants/notes/aoki.md。
暗い森の足もとの常緑低木 (1〜2m)。根元から緑色の太い茎が何本も立ち、上の方で 2 つずつ (対生で) 分かれる。
株は縦長の丸い形で、すき間が多くまばら。葉は 10〜20cm の大きな楕円で縁に粗い鋸歯、濃い緑で強いつや。茎の先に集まる。
野生のものなので斑のない緑。一年中ほぼ同じなので形は 1 つ。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_AokiOpus"
LEAF_PNG = "T_FD_Leaf_AokiOpus.png"
BARK = "FD_BarkAokiOpus"
BARK_D, BARK_N = bark.texture_names(BARK)
# 濃い緑で強いつや (光る所は明るい緑に見える)
COLORS = ((30, 58, 24), (38, 70, 28), (26, 50, 22), (46, 80, 32))
STEM = (86, 112, 56)
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.45, colors=COLORS)
# 茎は名前のとおり緑〜灰緑でなめらか
bark.BARK_KINDS[BARK] = dict(style="culm", tile=(0.15, 0.6), seed=17,
                             top=(92, 112, 64), crack=(64, 80, 46), tint=(88, 106, 62))


def _leaf(draw, r, base, angle, length, col):
    """大きな楕円の葉。縁の上半分に粗い鋸歯、中央の葉脈は明るく、つやの明るい帯を少し入れる。"""
    ca, sa = math.cos(angle), math.sin(angle)
    width = 0.42
    left, right = [], []
    n = 16
    for k in range(n + 1):
        t = k / n
        w = width * length * 0.5 * math.sin(math.pi * t) ** 0.75 * (1 - 0.15 * t)
        if t > 0.35 and k % 2:
            w *= 0.9   # 粗い鋸歯
        x = t * length
        left.append((base[0] + x * ca - w * sa, base[1] + x * sa + w * ca))
        right.append((base[0] + x * ca + w * sa, base[1] + x * sa - w * ca))
    draw.polygon(left + right[::-1], fill=col)
    hi = tuple(min(255, int(c * 1.35)) for c in col)   # つや
    k0, k1 = int(n * 0.25), int(n * 0.7)
    draw.line([((left[k][0] + base[0] + k / n * length * ca) / 2, (left[k][1] + base[1] + k / n * length * sa) / 2)
               for k in range(k0, k1)], fill=hi, width=max(3, int(length * 0.05)))
    tip = (base[0] + ca * length * 0.92, base[1] + sa * length * 0.92)
    draw.line([base, tip], fill=tuple(min(255, int(c * 1.5)) for c in col), width=2)


def leaf_texture(path, size=fo.TEXTURE_SIZE):
    """2x2。緑の茎の先で 2 つに分かれ、それぞれの先に大きな葉が 5〜8 枚、向かい合って放射状に付く。"""
    r = random.Random("AokiOpus")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy, s = i * cell, j * cell, cell
            root = (ox + s * 0.5, oy + s * 0.99)
            fork = (ox + s * r.uniform(0.46, 0.54), oy + s * 0.68)
            draw.line([root, fork], fill=STEM, width=max(6, s // 70))
            tips = [(fork[0] - s * r.uniform(0.12, 0.18), oy + s * r.uniform(0.4, 0.48)),
                    (fork[0] + s * r.uniform(0.12, 0.18), oy + s * r.uniform(0.38, 0.46))]
            for t in tips:
                draw.line([fork, t], fill=STEM, width=max(5, s // 90))
            for t in tips:
                n = r.randint(5, 8)
                for q in range(n):
                    a = -math.pi / 2 + (q - (n - 1) / 2) * (3.6 / n) + r.uniform(-0.12, 0.12)
                    ln = s * r.uniform(0.28, 0.36) * (0.75 if math.sin(a) > 0.2 else 1.0)
                    k = 1.08 - 0.25 * ((t[1] - oy) / s)
                    col = tuple(int(min(255, c * k)) for c in fo._jitter(r.choice(COLORS), r, 10))
                    _leaf(draw, r, t, a, ln, col)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.3, texture=LEAF_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.6, texture=BARK_D, normal=BARK_N),
}
LEAVES = {LEAF: (LEAF_PNG, leaf_texture)}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu", "shikoku", "chugoku", "kansai", "chubu", "kanto", "tohoku", "hokuriku")


def aoki(name, seed, height, stems):
    """height: 株の高さ、stems: 根元から立つ茎の数。茎は上の方で 2 つずつ分かれ、先に葉が集まる。"""
    rng = Rng(seed)
    m = Mesh(name)
    width = height * 0.36
    fol = fo.Foliage(LEAF, rng, (0, 0, height * 0.62), (width, width, height * 0.42))
    r0 = 0.008 * height + 0.008
    tips = []
    for j in range(stems):
        az = 2 * math.pi * j / stems + rng.uniform(-0.5, 0.5)
        lean = rng.uniform(0.15, 0.4) * width
        top = np.array([math.cos(az) * lean, math.sin(az) * lean, height * rng.uniform(0.28, 0.42)])
        base = np.array([math.cos(az) * 0.03, math.sin(az) * 0.03, -0.08])
        bark_tube(m, BARK, bezier(base, base + (top - base) * [0.3, 0.3, 0.55], top, 4),
                  np.linspace(r0, r0 * 0.75, 4), n=5)
        # 上の方で 2 つずつ分かれる (3 回)。分かれ目にも葉が残る
        level = [(top, az)]
        nodes = [top]
        for depth in range(3):
            nxt = []
            for p, a in level:
                for side in (1, -1):
                    a2 = a + side * rng.uniform(0.6, 1.1)
                    ln = height * rng.uniform(0.15, 0.21) * (1.0 - 0.25 * depth)
                    q = p + np.array([math.cos(a2) * ln * 0.55, math.sin(a2) * ln * 0.55, ln])
                    q[2] = min(q[2], height * 0.97)
                    bark_tube(m, BARK, np.array([p, (p + q) / 2, q]), [r0 * 0.7, r0 * 0.6, r0 * 0.5], n=4)
                    nxt.append((q, a2))
            level = nxt
            nodes += [p for p, _ in nxt[::2]] if depth < 2 else []
        tips += [p for p, _ in level] + nodes
    # 葉: 茎の先ごとに大きな葉の房。房の間はすき間を残す (まばらな株)
    for p in tips:
        cr = height * rng.uniform(0.1, 0.14)
        fo.clump(fol, p + [0, 0, cr * 0.2], cr, 4, size=cr * 2.0, flat=0.6, up_bias=0.8)
    return fol.write(m)


PLANTS = {
    "SM_FD_AokiOpus_A": dict(make=lambda: aoki("SM_FD_AokiOpus_A", 181, 1.9, 5),
                             height_m=1.9, habitat=("understory",), share=0.05, regions=REGIONS),
    "SM_FD_AokiOpus_B": dict(make=lambda: aoki("SM_FD_AokiOpus_B", 182, 1.3, 4),
                             height_m=1.3, habitat=("understory",), share=0.05, regions=REGIONS),
    "SM_FD_AokiOpus_C": dict(make=lambda: aoki("SM_FD_AokiOpus_C", 183, 0.8, 3),
                             height_m=0.8, habitat=("understory",), share=0.04, regions=REGIONS),
}
