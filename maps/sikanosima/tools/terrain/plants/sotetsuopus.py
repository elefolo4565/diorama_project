"""ソテツ (Cycas revoluta) の形 (Claude 版)。基準は plants/notes/sotetsu.md。
南九州の海岸の崖・岩場に生える。太い幹の頂に羽状の葉が放射状に広がる (ヤシに似るがヤシではない)。
幹の高さ 0.5〜2m、太さ 20〜40cm で、傾いたりくねったりし、古い株は 2〜3 本に分かれる。根元から子株が出て、低い株が固まる。
幹は古い葉の付け根のうろこで覆われ、暗い灰褐色〜黒褐色でごつごつ。葉は長さ 0.8〜1.5m、1 本の頂に 30〜60 枚が噴水のように立ち、
外側は水平〜下へ垂れる。小葉は細い針のようで硬く、濃い緑で強いつや。枯れた茶色の葉が頂の下に垂れ下がって残る。
一年中ほぼ同じなので形は 1 つ。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_SotetsuOpus"
LEAF_PNG = "T_FD_Leaf_SotetsuOpus.png"
BARK = "FD_BarkSotetsuOpus"
BARK_D, BARK_N = bark.texture_names(BARK)
GREEN = ((26, 58, 26), (34, 70, 30), (22, 48, 22), (44, 82, 36))   # 濃い緑で強いつや
DEAD = ((150, 118, 70), (128, 98, 58), (110, 84, 52))
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.2, colors=GREEN)
# 古い葉の付け根のうろこ: 暗い灰褐色〜黒褐色でごつごつ
bark.BARK_KINDS[BARK] = dict(style="plates", tile=(0.25, 0.3), seed=19,
                             top=(84, 74, 62), crack=(40, 34, 28), tint=(76, 68, 58))
FRONT_CELLS = ((0, 0), (1, 0), (0, 1))
DEAD_CELL = (1, 1)


def _frond(draw, r, ox, oy, s, colors, rachis):
    """区画の下の中央から上へ 1 枚の羽状の葉。軸の左右に細い針のような小葉が密に、斜め前へ並ぶ。"""
    x0, y0 = ox + s * 0.5, oy + s * 0.99
    n = 60
    pts = [(x0 + math.sin(t / n * 1.5) * s * 0.02, y0 - t / n * s * 0.96) for t in range(n + 1)]
    draw.line(pts, fill=rachis, width=max(3, s // 180))
    for k in range(4, n):
        t = k / n
        p = pts[k]
        ln = s * 0.4 * (math.sin(math.pi * min(1.0, t * 1.05)) ** 0.5) * (1.0 - 0.35 * t)
        for side in (1, -1):
            a = -math.pi / 2 + side * r.uniform(0.95, 1.15)   # 斜め前 (葉の先の方) へ
            e = (p[0] + math.cos(a) * ln, p[1] + math.sin(a) * ln)
            col = fo._jitter(r.choice(colors), r, 10)
            draw.line([p, e], fill=col, width=max(4, s // 100))


def leaf_texture(path, size=fo.TEXTURE_SIZE):
    r = random.Random("SotetsuOpus")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for (i, j) in FRONT_CELLS:
        _frond(draw, r, i * cell, j * cell, cell, GREEN, (70, 84, 44))
    _frond(draw, r, DEAD_CELL[0] * cell, DEAD_CELL[1] * cell, cell, DEAD, (110, 86, 56))
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.3, texture=LEAF_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.9, texture=BARK_D, normal=BARK_N),
}
LEAVES = {LEAF: (LEAF_PNG, leaf_texture)}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu",)   # 自然に生えるのは南九州 (と沖縄だが、沖縄は別に作る)


def _frond_card(fol, base, out_dir, rise, length, width, cell):
    """1 枚の葉を 2 つの板で弓なりに: 付け根の板は rise の角度で立ち、先の板は垂れる。絵は 2 つの板にまたがって貼る。"""
    ci, cj = cell
    u0, u1 = ci / fo.CELLS, (ci + 1) / fo.CELLS
    v_lo, v_hi = (cj + 1) / fo.CELLS, cj / fo.CELLS
    v_mid = (v_lo + v_hi) / 2
    h = np.array([out_dir[0], out_dir[1], 0.0])
    h /= np.linalg.norm(h)
    d1 = h * math.cos(rise) + np.array([0, 0, math.sin(rise)])
    droop = rise - 0.9
    d2 = h * math.cos(droop) + np.array([0, 0, math.sin(droop)])
    side = np.cross([0, 0, 1.0], h)
    b = np.asarray(base, float)
    m = b + d1 * length * 0.5
    t = m + d2 * length * 0.5
    rows = [(b, v_lo, 0.55), (m, v_mid, 0.85), (t, v_hi, 1.0)]
    for (p0, va, la), (p1, vb, lb) in zip(rows[:-1], rows[1:]):
        corners = [p0 - side * width / 2, p0 + side * width / 2, p1 + side * width / 2, p1 - side * width / 2]
        for c, uv, lit in zip(corners, [(u0, va), (u1, va), (u1, vb), (u0, vb)], (la, la, lb, lb)):
            dv = (c - fol.center) / fol.radii
            n = dv / max(np.linalg.norm(dv), 1e-6) * 0.5 + np.array([0, 0, 0.5])
            fol.normals.append(n / np.linalg.norm(n))
            fol.colors.append(lit)
            fol.verts.append(c)
            fol.uvs.append(uv)


def sotetsu(name, seed, trunks, frond_len):
    """trunks: [(幹の高さ, 傾き, 根元のずれ), ...]、frond_len: 葉の長さ。"""
    rng = Rng(seed)
    m = Mesh(name)
    top_h = max(t[0] for t in trunks)
    fol = fo.Foliage(LEAF, rng, (0, 0, top_h), (frond_len, frond_len, frond_len * 0.6))
    for th, lean, off in trunks:
        az = rng.uniform(0, 2 * math.pi)
        base = np.array([math.cos(az) * off, math.sin(az) * off, -0.1])
        top = base + np.array([math.cos(az) * lean * th, math.sin(az) * lean * th, th + 0.1])
        mid = (base + top) / 2 + [rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), 0]   # くねり
        r0 = 0.09 + 0.025 * th
        bark_tube(m, BARK, bezier(base, mid, top, 5), [r0 * 1.15, r0, r0 * 0.95, r0 * 0.92, r0 * 0.85], n=10)
        bark_tube(m, BARK, np.array([top, top + [0, 0, 0.08], top + [0, 0, 0.14]]), [r0 * 0.85, r0 * 0.5, 0.02], n=10)   # 頂を閉じる
        n = int(30 + 8 * th)
        for k in range(n):   # 噴水のように放射状: 内側は立ち、外側は水平〜下へ
            a = 2 * math.pi * k / n * 2.618 + rng.uniform(-0.1, 0.1)
            ring = (k % 4) / 3.0
            rise = math.radians(62 - 60 * ring + rng.uniform(-8, 8))
            ln = frond_len * rng.uniform(0.8, 1.05) * (0.75 + 0.25 * ring)
            _frond_card(fol, top + [0, 0, 0.05], (math.cos(a), math.sin(a)), rise, ln, ln * 0.38,
                        FRONT_CELLS[int(rng.integers(0, 3))])
        for k in range(int(6 + 2 * th)):   # 頂の下に垂れ下がる枯れた葉
            a = rng.uniform(0, 2 * math.pi)
            ln = frond_len * rng.uniform(0.6, 0.85)
            _frond_card(fol, top - [0, 0, 0.12], (math.cos(a), math.sin(a)), math.radians(rng.uniform(-35, -10)) + 0.9,
                        ln, ln * 0.28, DEAD_CELL)
    return fol.write(m)


PLANTS = {
    # 古い株: 途中で分かれた 3 本の幹と子株
    "SM_FD_SotetsuOpus_A": dict(make=lambda: sotetsu("SM_FD_SotetsuOpus_A", 221,
                                                     [(1.9, 0.25, 0.1), (1.3, 0.35, 0.2), (0.5, 0.2, 0.45)], 1.4),
                                height_m=2.8, habitat=("coast",), share=0.03, regions=REGIONS),
    # 1 本の幹が海側へ傾く
    "SM_FD_SotetsuOpus_B": dict(make=lambda: sotetsu("SM_FD_SotetsuOpus_B", 222, [(1.3, 0.3, 0.0)], 1.3),
                                height_m=2.1, habitat=("coast",), share=0.03, regions=REGIONS),
    # 岩場の低い株の固まり
    "SM_FD_SotetsuOpus_C": dict(make=lambda: sotetsu("SM_FD_SotetsuOpus_C", 223, [(0.5, 0.1, 0.1), (0.3, 0.2, 0.4)], 1.0),
                                height_m=1.2, habitat=("coast",), share=0.02, regions=REGIONS),
}
