"""シャリンバイ (Rhaphiolepis indica var. umbellata) の形 (Claude 版)。基準は plants/notes/sharinbai.md。
海岸の崖や岩場、海辺の林のふちに生える常緑の低木 (1〜3m)。根元近くから分かれる株立ちで、丸くこんもりした樹冠が下の方まで茂る。
枝は黒っぽい灰褐色でやや太く、枝先で数本に車輪のように分かれ、その分かれ目に厚い葉が輪になって集まる (名前の「車輪」)。
4〜5 月は枝先に白い花の房が咲き、株全体に白が点々と散る。花の時期 (春) は花の付いた形 (`_Hana`) を同じ所に出す。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

LEAF = "FD_Leaf_SharinbaiOpus"
LEAF_PNG = "T_FD_Leaf_SharinbaiOpus.png"
HANA = "FD_Leaf_SharinbaiOpusHana"
HANA_PNG = "T_FD_Leaf_SharinbaiOpusHana.png"
BARK = "FD_BarkSharinbaiOpus"
BARK_D, BARK_N = bark.texture_names(BARK)
# 濃い緑の厚い葉。新しい葉は黄緑〜赤み
COLORS = ((28, 50, 22), (36, 60, 26), (46, 70, 30), (24, 42, 20))
NEW_COLORS = ((92, 104, 40), (110, 82, 44))
fo.LEAF_KINDS[LEAF] = dict(texture=LEAF_PNG, style="broad", leaves=0, length=(1, 1), width=0.5, colors=COLORS)
fo.LEAF_KINDS[HANA] = dict(fo.LEAF_KINDS[LEAF], texture=HANA_PNG)
# 黒っぽい灰褐色の樹皮 (浅い縦の割れ目)
bark.BARK_KINDS[BARK] = dict(style="fissured", tile=(0.4, 0.9), seed=13,
                             top=(78, 72, 66), crack=(36, 32, 28), tint=(70, 66, 60))


def _leaf(base, angle, length, width=0.42, n=10):
    """倒卵形〜長楕円形の厚い葉 (付け根が細く、先は丸い)。"""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for side in (1, -1):
        for t in (np.linspace(0, 1, n) if side == 1 else np.linspace(1, 0, n)):
            w = width * length * 0.5 * math.sin(math.pi * t ** 0.8) ** 0.65 * (0.5 + 0.55 * t) * side
            pts.append((base[0] + t * length * ca - w * sa, base[1] + t * length * sa + w * ca))
    return pts


def _texture(path, flowers, size=fo.TEXTURE_SIZE):
    """2x2 の小枝。枝が先で 3〜5 本に車輪のように分かれ、それぞれの分かれ目に葉が輪になって付く。
    flowers のときは、枝先の輪の上に白い花の房 (5 弁、中心が赤) を描く。"""
    r = random.Random("SharinbaiOpus")   # 花の有無で葉の並びを変えない (同じ乱数の順)
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    bunches = []
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy, s = i * cell, j * cell, cell
            root = (ox + s * 0.5, oy + s * 0.98)
            hub = (root[0] + r.uniform(-0.04, 0.04) * s, oy + s * 0.55)
            draw.line([root, hub], fill=(52, 44, 38), width=max(4, s // 80))
            rings = [hub]
            for k in range(r.randint(3, 5)):   # 車輪の幅: 斜め上へ放射状に
                a = -math.pi / 2 + (k - 2) * 0.62 + r.uniform(-0.12, 0.12)
                ln = s * r.uniform(0.3, 0.38)
                tip = (hub[0] + math.cos(a) * ln, hub[1] + math.sin(a) * ln)
                draw.line([hub, tip], fill=(52, 44, 38), width=max(3, s // 110))
                rings.append(tip)
            rings.sort(key=lambda t: -t[1])
            for c in rings:   # 下の輪から描き、上の輪を手前にする
                n = r.randint(7, 10)
                young = r.random() < 0.3 and c is not hub
                for q in range(n):
                    a = 2 * math.pi * q / n + r.uniform(-0.2, 0.2)
                    ln = s * r.uniform(0.18, 0.25) * (0.75 if math.sin(a) > 0.4 else 1.0)
                    k = 1.08 - 0.28 * ((c[1] - oy) / s)
                    base = r.choice(NEW_COLORS) if young and q % 3 == 0 else r.choice(COLORS)
                    col = tuple(int(min(255, v * k)) for v in fo._jitter(base, r))
                    draw.polygon(_leaf(c, a, ln), fill=col)
                    end = (c[0] + math.cos(a) * ln * 0.85, c[1] + math.sin(a) * ln * 0.85)
                    draw.line([c, end], fill=tuple(int(v * 0.75) for v in col), width=2)
                if c is not hub:
                    bunches.append((c, s))
    if flowers:
        for (cx, cy), s in bunches:   # 枝先の輪の中心に、小さな花が 8〜12 輪の房
            for _ in range(r.randint(8, 12)):
                fx = cx + r.uniform(-0.07, 0.07) * s
                fy = cy + r.uniform(-0.08, 0.03) * s
                rad = s * r.uniform(0.016, 0.022)
                for q in range(5):
                    a = 2 * math.pi * q / 5 + r.uniform(-0.2, 0.2)
                    px, py = fx + math.cos(a) * rad * 0.6, fy + math.sin(a) * rad * 0.6
                    w = (r.randint(236, 250),) * 2 + (r.randint(228, 242),)
                    draw.ellipse([px - rad * 0.55, py - rad * 0.55, px + rad * 0.55, py + rad * 0.55], fill=w + (255,))
                draw.ellipse([fx - rad * 0.25, fy - rad * 0.25, fx + rad * 0.25, fy + rad * 0.25], fill=(176, 56, 52, 255))
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


MATERIALS = {
    LEAF: dict(color=(1, 1, 1), roughness=0.45, texture=LEAF_PNG, alpha=True),
    HANA: dict(color=(1, 1, 1), roughness=0.45, texture=HANA_PNG, alpha=True),
    BARK: dict(color=(1, 1, 1), roughness=0.85, texture=BARK_D, normal=BARK_N),
}
LEAVES = {
    LEAF: (LEAF_PNG, lambda path: _texture(path, False)),
    HANA: (HANA_PNG, lambda path: _texture(path, True)),
}
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto")


def sharinbai(name, seed, height, width, stems, wind=0.0, leaf=LEAF):
    """height: 樹高、width: 樹冠の半径、stems: 根元近くから立つ幹の数、wind: 潮風で風上 (-X) が低くなる度合い。
    leaf を変えても形は同じ (乱数の順番が同じ)。"""
    rng = Rng(seed)
    m = Mesh(name)
    half_h = height * 0.52
    cz = height - half_h
    shift = min(width * 0.2 * wind, height * 0.15)
    fol = fo.Foliage(leaf, rng, (shift, 0, cz), (width, width * 0.9, half_h))
    hubs = []
    for j in range(stems):
        az = 2 * math.pi * j / stems + rng.uniform(-0.4, 0.4)
        base = np.array([math.cos(az) * 0.06, math.sin(az) * 0.06, -0.15])
        out = rng.uniform(0.25, 0.5) * width
        top = np.array([math.cos(az) * out + shift, math.sin(az) * out * 0.9, cz + rng.uniform(-0.1, 0.3) * half_h])
        mid = base + (top - base) * np.array([0.35, 0.35, 0.55])
        r0 = 0.01 * height + 0.014
        bark_tube(m, BARK, bezier(base, mid, top, 5), np.linspace(r0, r0 * 0.45, 5), n=6)
        # 幹の先で車輪のように 3〜5 本に分かれる
        for _ in range(int(rng.integers(3, 6))):
            a2 = az + rng.uniform(-1.4, 1.4)
            end = top + np.array([math.cos(a2) * width * 0.28, math.sin(a2) * width * 0.25, half_h * rng.uniform(0.15, 0.45)])
            bark_tube(m, BARK, np.array([top, (top + end) / 2, end]), [r0 * 0.45, r0 * 0.32, 0.01], n=5)
            hubs.append(end)
    # 房: 楕円体の表面近く。枝先の輪ごとに小さくまとまり、でこぼこの丸い輪郭
    n_clumps = int(34 * width * width + 34)
    for _ in range(n_clumps):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.8 + 0.22
        d /= np.linalg.norm(d)
        if d[2] < -0.45 and rng.random() < 0.4:
            continue
        r = rng.uniform(0.66, 0.92)
        fp = np.array([shift, 0, cz]) + d * np.array([width, width * 0.9, half_h]) * r
        if wind > 0:
            fp[2] -= wind * 0.3 * half_h * max(0.0, -d[0]) * max(0.0, d[2])
        fp[2] = max(fp[2], 0.06)
        if rng.random() < 0.3:
            near = min(hubs, key=lambda p: float(np.sum((p - fp) ** 2)))
            bark_tube(m, BARK, np.array([near, (near + fp) / 2, fp]), [0.014, 0.01, 0.006], n=4)
        cr = min(width, half_h) * rng.uniform(0.2, 0.3)
        fo.clump(fol, fp, cr, 6, size=cr * 1.55, up_bias=0.6)
    for p in hubs[::2]:   # 奥を埋める葉
        fo.clump(fol, p, min(width, half_h) * 0.35, 5, size=min(width, half_h) * 0.45)
    return fol.write(m)


LEAF_SEASONS = 2 | 4 | 8   # 夏・秋・冬は葉だけ
HANA_SEASONS = 1           # 春 (4〜5 月) は白い花
SHAPES = {"A": (131, 2.6, 1.5, 5, 0.2), "B": (132, 1.7, 1.3, 6, 0.7), "C": (133, 1.0, 0.75, 4, 0.4)}
SHARES = {"A": 0.035, "B": 0.03, "C": 0.025}
PLANTS = {}
for _k, (_seed, _h, _w, _st, _wind) in SHAPES.items():
    _base = f"SM_FD_SharinbaiOpus_{_k}"
    PLANTS[_base] = dict(make=lambda s=_seed, h=_h, w=_w, st=_st, wi=_wind, n=_base: sharinbai(n, s, h, w, st, wi),
                         height_m=_h, habitat=("coast",), share=SHARES[_k], seasons=LEAF_SEASONS, regions=REGIONS)
    PLANTS[_base + "_Hana"] = dict(
        make=lambda s=_seed, h=_h, w=_w, st=_st, wi=_wind, n=_base + "_Hana": sharinbai(n, s, h, w, st, wi, leaf=HANA),
        height_m=_h, habitat=("coast",), share=SHARES[_k], seasons=HANA_SEASONS, regions=REGIONS, place_with=_base)
