"""アラカシ (Quercus glauca) の形 (Claude 版)。基準は plants/notes/arakashi.md。
里山の林や社寺林に多い常緑高木 (6〜15m)。単幹で、地上 2〜3m で太い枝 3〜5 本に分かれて斜め上へ伸びる。
樹冠は丸い卵形〜半球形で密、輪郭は小さな房のでこぼこ。林のふちでは下枝が地面近くまで残る。
幹は灰色〜緑がかった灰色でなめらか、白っぽい斑が点々とある。葉は 7〜12cm の長い楕円で、表は濃い緑でつや、裏は白っぽい。
春 (4〜5 月) は赤茶色〜銅色の新芽と黄褐色の垂れた花が出て、樹冠が茶色がかる。その季節は新芽の形 (`_Haru`) を同じ所に出す。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_ArakashiOpus"
LEAF_PNG = "T_FD_Leaf_ArakashiOpus.png"
HARU = "FD_Leaf_ArakashiOpusHaru"
HARU_PNG = "T_FD_Leaf_ArakashiOpusHaru.png"
BARK = "FD_BarkArakashiOpus"
BARK_D, BARK_N = bark.texture_names(BARK)
# 濃い緑の表と、白っぽい灰緑の裏 (ところどころ裏返って見える)
COLORS = ((26, 48, 22), (32, 56, 26), (40, 66, 30), (22, 40, 20))
UNDER = ((118, 132, 108), (132, 144, 120))
COPPER = ((150, 82, 44), (128, 70, 40), (164, 104, 56), (112, 84, 44))
CATKIN = (168, 140, 74)
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.4, colors=COLORS)
fo.LEAF_KINDS[HARU] = dict(fo.LEAF_KINDS[LEAF], texture=HARU_PNG)
# 灰色〜緑がかった灰色でなめらか、白っぽい斑
bark.BARK_KINDS[BARK] = dict(style="culm", tile=(0.7, 1.4), seed=14,
                             top=(118, 120, 110), crack=(78, 80, 72), tint=(132, 138, 122))


def _texture(path, spring, size=fo.TEXTURE_SIZE):
    """2x2 の小枝。長い楕円の葉が互い違いに付き、枝先ほど密。spring のときは枝先の葉を銅色にし、黄褐色の垂れた花を描く。"""
    r = random.Random("ArakashiOpus")   # 季節で葉の並びを変えない (同じ乱数の順)
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    hangs = []
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy, s = i * cell, j * cell, cell
            twigs = fo._twigs(r, s, s * 0.5, 7, spread=0.42)
            for tw in twigs:
                draw.line([(ox + p[0], oy + p[1]) for p in tw], fill=fo.TWIG_COLOR, width=max(2, s // 130))
            for (p, a) in fo._points_along(twigs, r, 150):
                ang = a + r.choice((1, -1)) * r.uniform(0.5, 1.2)
                ln = r.uniform(70, 98) * s / 512
                tip_ness = 1 - p[1] / s                          # 上 (枝先) ほど 1
                if r.random() < 0.12:
                    base = r.choice(UNDER)                       # 裏返った葉
                elif spring and tip_ness > 0.45 and r.random() < 0.6:
                    base = r.choice(COPPER)                      # 春の新芽
                else:
                    base = r.choice(COLORS)
                k = 1.1 - 0.3 * (p[1] / s)
                col = tuple(int(min(255, c * k)) for c in fo._jitter(base, r))
                b = (ox + p[0] + math.cos(ang) * 3, oy + p[1] + math.sin(ang) * 3)
                draw.polygon(fo._leaf_polygon(b, ang, ln, 0.34), fill=col)
                tip = (b[0] + math.cos(ang) * ln * 0.9, b[1] + math.sin(ang) * ln * 0.9)
                draw.line([b, tip], fill=tuple(int(c * 0.78) for c in col), width=1)
                if tip_ness > 0.5 and r.random() < 0.08:
                    hangs.append((b, s))
    if spring:
        for (x, y), s in hangs:   # 垂れた花の房 (細い黄褐色のひも)
            ln = s * r.uniform(0.07, 0.11)
            pts = [(x + math.sin(t * 2.5) * s * 0.006, y + t * ln) for t in np.linspace(0, 1, 8)]
            draw.line(pts, fill=CATKIN, width=max(3, s // 120))
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.45, texture=LEAF_PNG, alpha=True),
    HARU: dict(color=(1, 1, 1), roughness=0.5, texture=HARU_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.8, texture=BARK_D, normal=BARK_N),
}
LEAVES = {
    LEAF: (LEAF_PNG, lambda path: _texture(path, False)),
    HARU: (HARU_PNG, lambda path: _texture(path, True)),
}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu", "shikoku", "chugoku", "kansai", "chubu", "kanto", "tohoku", "hokuriku")


def arakashi(name, seed, height, limbs, skirt, wide=1.0, leaf=LEAF):
    """height: 樹高、limbs: 幹が分かれる太い枝の数、skirt: 樹冠の下の端 (樹高に対する割合。林のふちでは小さい)、
    wide: 樹冠の幅の倍率。leaf を変えても形は同じ (乱数の順番が同じ)。"""
    rng = Rng(seed)
    m = Mesh(name)
    crown_lo = height * skirt
    half_h = (height - crown_lo) / 2
    cz = crown_lo + half_h
    width = height * 0.36 * wide
    fol = fo.Foliage(leaf, rng, (0, 0, cz), (width, width, half_h))
    r0 = 0.03 * height
    fork = min(height * rng.uniform(0.18, 0.24), 3.0)
    bark_tube(m, BARK, bezier((0, 0, -0.3), (0, 0, fork * 0.5), (0, 0, fork), 4),
              [r0 * 1.35, r0 * 1.12, r0 * 1.02, r0], n=12)
    ends = []
    for j in range(limbs):
        az = 2 * math.pi * j / limbs + rng.uniform(-0.3, 0.3)
        reach = width * rng.uniform(0.35, 0.55)
        top = np.array([math.cos(az) * reach, math.sin(az) * reach, cz + rng.uniform(-0.05, 0.35) * half_h])
        mid = np.array([math.cos(az) * reach * 0.4, math.sin(az) * reach * 0.4, (fork + top[2]) * 0.48])
        path = bezier((0, 0, fork - 0.2), mid, top, 7)
        bark_tube(m, BARK, path, np.linspace(r0 * 0.72, 0.04, 7), n=9)
        ends.append(top)
        # 太い枝の途中から外へ出る枝 (下枝は林のふちほど低く、水平ぎみ)
        for t in (0.35, 0.6, 0.8):
            p0 = path[int(t * (len(path) - 1))]
            a2 = az + rng.uniform(-0.9, 0.9)
            dz = (p0[2] - cz) / half_h
            out = width * math.sqrt(max(0.1, 1 - dz * dz)) * rng.uniform(0.6, 0.85)
            end = p0 + np.array([math.cos(a2) * out * 0.75, math.sin(a2) * out * 0.75, out * rng.uniform(0.15, 0.5)])
            bark_tube(m, BARK, np.array([p0, (p0 + end) / 2 + [0, 0, 0.15], end]), [r0 * 0.3, r0 * 0.2, 0.025], n=6)
            ends.append(end)
    # 房: 楕円体の表面近くに小さめの房を密に。房の大きさをばらつかせ、輪郭を小さなでこぼこにする
    n_clumps = int(60 + 1.5 * height * height * wide)
    for _ in range(n_clumps):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.9 + 0.15
        d /= np.linalg.norm(d)
        if d[2] < -0.55 and rng.random() < 0.5:
            continue
        fp = np.array([0, 0, cz]) + d * np.array([width, width, half_h]) * rng.uniform(0.66, 0.94)
        fp[2] = max(fp[2], crown_lo * 0.7)
        if rng.random() < 0.25:
            near = min(ends, key=lambda p: float(np.sum((p - fp) ** 2)))
            bark_tube(m, BARK, np.array([near, (near + fp) / 2, fp]), [0.03, 0.02, 0.01], n=4)
        cr = width * rng.uniform(0.17, 0.27)
        fo.clump(fol, fp, cr, 8, size=cr * 1.25, up_bias=0.45)
    for p in ends[::2]:   # 奥を埋める葉
        fo.clump(fol, p, width * 0.3, 5, size=width * 0.35)
    return fol.write(m)


LEAF_SEASONS = 2 | 4 | 8   # 夏・秋・冬は濃い緑
HARU_SEASONS = 1           # 春は銅色の新芽と黄褐色の花
SHAPES = {"A": (141, 12.0, 4, 0.3, 1.0), "B": (142, 8.5, 3, 0.1, 1.1), "C": (143, 6.0, 3, 0.2, 0.85)}
SHARES = {"A": 0.04, "B": 0.035, "C": 0.03}
PLANTS = {}
for _k, (_seed, _h, _l, _sk, _w) in SHAPES.items():
    _base = f"SM_FD_ArakashiOpus_{_k}"
    PLANTS[_base] = dict(make=lambda s=_seed, h=_h, l=_l, sk=_sk, w=_w, n=_base: arakashi(n, s, h, l, sk, w),
                         height_m=_h, habitat=("forest",), share=SHARES[_k], seasons=LEAF_SEASONS, regions=REGIONS)
    PLANTS[_base + "_Haru"] = dict(
        make=lambda s=_seed, h=_h, l=_l, sk=_sk, w=_w, n=_base + "_Haru": arakashi(n, s, h, l, sk, w, leaf=HARU),
        height_m=_h, habitat=("forest",), share=SHARES[_k], seasons=HARU_SEASONS, regions=REGIONS, place_with=_base)
