"""アカメガシワ (Mallotus japonicus) の形 (Claude 版)。基準は plants/notes/akamegashiwa.md。
道ばた・畑のふち・伐採跡に先に生える落葉樹 (5〜10m)。幹は 1〜3 本で低い所から分かれ、枝は横〜斜め上に大きく広がる。
樹冠は横に広い傘形で、葉の層の間にすき間が多く明るい。葉は大きな卵形〜ひし形で、長い赤い葉柄の先に水平に広がる。
季節の形は 4 つ: 夏 = 明るい緑 (基本の形)、春 = 赤〜赤紫の新芽 (`_Haru`)、秋 = 黄葉 (`_Aki`)、冬 = 葉を落とした灰白色の枝だけ (`_Fuyu`)。
どれも同じ乱数の順で作るので、枝の形は 4 つとも同じ。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import bark
import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

NAME = "AkamegashiwaOpus"
BARK = "FD_BarkAkamegashiwaOpus"
BARK_D, BARK_N = bark.texture_names(BARK)
# 灰褐色〜灰白色、縦に浅い割れ目
bark.BARK_KINDS[BARK] = dict(style="fissured", tile=(0.5, 1.1), seed=15,
                             top=(140, 134, 122), crack=(88, 82, 74), tint=(130, 126, 116))

# 季節ごとの葉の色 (葉の並びは同じで、色だけ変える)
PALETTES = {
    "": ((78, 112, 40), (92, 126, 46), (104, 138, 52), (68, 98, 36)),           # 夏: 明るい緑、つやは弱い
    "Haru": ((156, 40, 52), (132, 34, 62), (176, 66, 58), (110, 92, 44)),        # 春: 赤〜赤紫の新芽 (古い葉が少し緑)
    "Aki": ((206, 172, 56), (188, 146, 46), (170, 124, 40), (150, 140, 52)),     # 秋: 黄葉 (少し黄緑が残る)
}
PETIOLE = {"": (150, 54, 46), "Haru": (170, 46, 52), "Aki": (164, 92, 46)}
LEAVES, MATERIALS = {}, {BARK: dict(color=(1, 1, 1), roughness=0.85, texture=BARK_D, normal=BARK_N)}


def _leaf(base, angle, length, width=0.72, n=10):
    """卵形〜ひし形の大きな葉 (付け根は丸く、中ほどが一番広く、先がとがる)。"""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for side in (1, -1):
        for t in (np.linspace(0, 1, n) if side == 1 else np.linspace(1, 0, n)):
            w = width * length * 0.5 * math.sin(math.pi * min(1.0, t * 1.15) ** 1.1) ** 0.7 * (1 - 0.35 * t) * side
            pts.append((base[0] + t * length * ca - w * sa, base[1] + t * length * sa + w * ca))
    return pts


def _texture(path, season, size=fo.TEXTURE_SIZE):
    """2x2 の枝先。短い枝の先に、長い赤い葉柄の大きな葉が 5〜8 枚、水平に放射状に広がる (上から見た傘のよう)。"""
    r = random.Random(NAME)   # 季節で葉の並びを変えない (同じ乱数の順)
    colors = PALETTES[season]
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy, s = i * cell, j * cell, cell
            root = (ox + s * 0.5, oy + s * 0.98)
            hubs = [(ox + s * r.uniform(0.38, 0.62), oy + s * r.uniform(0.42, 0.55))]
            hubs.append((hubs[0][0] + s * r.uniform(-0.22, -0.12), hubs[0][1] + s * r.uniform(0.1, 0.2)))
            hubs.append((hubs[0][0] + s * r.uniform(0.12, 0.22), hubs[0][1] + s * r.uniform(0.08, 0.18)))
            for h in hubs:
                draw.line([root, h], fill=(96, 88, 78), width=max(4, s // 100))
            for hk, h in enumerate(hubs):
                n = r.randint(5, 8)
                for q in range(n):
                    a = -math.pi / 2 + (q - (n - 1) / 2) * (2.6 / n) + r.uniform(-0.15, 0.15)
                    if hk and r.random() < 0.3:
                        a += math.pi * 0.9   # 下の枝先は下向きの葉も
                    pet = s * r.uniform(0.08, 0.13)
                    b = (h[0] + math.cos(a) * pet, h[1] + math.sin(a) * pet)
                    draw.line([h, b], fill=PETIOLE[season], width=max(2, s // 220))
                    ln = s * r.uniform(0.2, 0.27) * (0.8 if hk else 1.0)
                    k = 1.1 - 0.28 * ((b[1] - oy) / s)
                    base = r.choice(colors)
                    if season == "Haru" and hk and r.random() < 0.5:
                        base = PALETTES[""][r.randrange(4)]   # 下の古い葉は緑のまま
                    col = tuple(int(min(255, c * k)) for c in fo._jitter(base, r))
                    draw.polygon(_leaf(b, a, ln), fill=col)
                    end = (b[0] + math.cos(a) * ln * 0.85, b[1] + math.sin(a) * ln * 0.85)
                    draw.line([b, end], fill=tuple(int(c * 0.72) for c in col), width=2)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


for _s in PALETTES:
    _leaf_name, _png = f"FD_Leaf_{NAME}{_s}", f"T_FD_Leaf_{NAME}{_s}.png"
    fo.LEAF_KINDS[_leaf_name] = dict(texture=_png, style="broad", leaves=0, length=(1, 1), width=0.6, colors=PALETTES[_s])
    MATERIALS[_leaf_name] = dict(color=(1, 1, 1), roughness=0.6, texture=_png, alpha=True)
    LEAVES[_leaf_name] = (_png, lambda path, s=_s: _texture(path, s))
BARKS = {BARK: (BARK_D, BARK_N, lambda c, n: bark.bark_textures(BARK, c, n))}
REGIONS = ("kyushu", "okinawa", "shikoku", "chugoku", "kansai", "chubu", "kanto", "tohoku", "hokuriku")


def akamegashiwa(name, seed, height, trunks, season=""):
    """height: 樹高、trunks: 低い所で分かれる幹の数、season: "" 夏 / "Haru" / "Aki" / "Fuyu" (冬は葉なし)。"""
    rng = Rng(seed)
    m = Mesh(name)
    width = height * 0.55                      # 樹冠の半径 (横に広い傘形)
    half_h = height * 0.32
    cz = height - half_h
    leaf = f"FD_Leaf_{NAME}{season}" if season != "Fuyu" else f"FD_Leaf_{NAME}"
    fol = fo.Foliage(leaf, rng, (0, 0, cz), (width, width, half_h))
    r0 = 0.024 * height
    split = rng.uniform(0.5, 1.1) if trunks > 1 else height * 0.32
    bark_tube(m, BARK, bezier((0, 0, -0.25), (0, 0, split * 0.5), (0, 0, split), 3), [r0 * 1.4, r0 * 1.15, r0], n=10)
    ends = []
    for j in range(trunks):
        az = 2 * math.pi * j / trunks + rng.uniform(-0.4, 0.4)
        off = 0.0 if trunks == 1 else width * 0.22
        top = np.array([math.cos(az) * off, math.sin(az) * off, height * rng.uniform(0.3, 0.38)])
        path = bezier((0, 0, split - 0.1), (top[0] * 0.4, top[1] * 0.4, (split + top[2]) * 0.5), top, 6)
        bark_tube(m, BARK, path, np.linspace(r0 * (1.0 if trunks == 1 else 0.78), r0 * 0.55, 6), n=9)
        # 幹の先で枝が横〜斜め上へ大きく広がる (幹ごとに外側を向き、全体で樹冠をうめる)
        n_limbs = int(rng.integers(3, 5)) if trunks > 1 else int(rng.integers(6, 8))
        for li in range(n_limbs):
            a2 = (az if trunks > 1 else 0.0) + 2 * math.pi * li / n_limbs * (0.55 if trunks > 1 else 1.0) \
                - (math.pi * 0.55 * (n_limbs - 1) / n_limbs if trunks > 1 else 0.0) + rng.uniform(-0.25, 0.25)
            reach = width * rng.uniform(0.6, 0.95)
            end = top + np.array([math.cos(a2) * reach, math.sin(a2) * reach, 0])
            end[2] = cz + half_h * rng.uniform(-0.45, 0.6) * (1.0 - 0.4 * reach / width)
            mid = top + (end - top) * 0.4 + [0, 0, half_h * 0.25]
            limb = bezier(top, mid, end, 6)
            bark_tube(m, BARK, limb, np.linspace(r0 * 0.5, 0.03, 6), n=7)
            for t in (0.4, 0.7, 1.0):
                ends.append(limb[min(int(t * (len(limb) - 1)), len(limb) - 1)])
    # 枝先: 水平に広がる葉の層。層のあいだはすき間を残す (空が見える明るい樹冠)
    tips = []
    for p in ends:
        for _ in range(int(rng.integers(3, 5))):
            a = rng.uniform(0, 2 * math.pi)
            d = width * rng.uniform(0.18, 0.32)
            q = p + np.array([math.cos(a) * d, math.sin(a) * d, d * rng.uniform(0.1, 0.45)])
            rr = math.hypot(q[0], q[1])
            if rr > width * 1.05:
                q[:2] *= width * 1.05 / rr
            q[2] = min(q[2], height * 0.98)
            # 細い小枝 (冬に見える)。先で 2 本に分かれる
            bark_tube(m, BARK, np.array([p, (p + q) / 2 + [0, 0, 0.08], q]), [0.035, 0.022, 0.012], n=4)
            for _ in range(2):
                b = rng.uniform(-0.8, 0.8)
                tw = q + np.array([math.cos(a + b), math.sin(a + b), rng.uniform(0.3, 0.9)]) * width * 0.09
                bark_tube(m, BARK, np.array([q, (q + tw) / 2, tw]), [0.012, 0.009, 0.005], n=3)
            tips.append(q)
    for q in tips:
        cr = width * rng.uniform(0.14, 0.2)
        fo.clump(fol, q + [0, 0, 0.1], cr, 5, size=cr * 1.5, flat=0.35, up_bias=0.9)
    if season == "Fuyu":
        return m   # 冬は葉を落とした幹と枝だけ (乱数はほかの季節と同じだけ使っている)
    return fol.write(m)


SEASON_BITS = {"": 2, "Haru": 1, "Aki": 4, "Fuyu": 8}
SHAPES = {"A": (151, 8.5, 2), "B": (152, 6.5, 1), "C": (153, 5.0, 3)}
SHARES = {"A": 0.04, "B": 0.04, "C": 0.03}
PLANTS = {}
for _k, (_seed, _h, _tr) in SHAPES.items():
    _base = f"SM_FD_{NAME}_{_k}"
    for _s, _bits in SEASON_BITS.items():
        _n = _base + (f"_{_s}" if _s else "")
        PLANTS[_n] = dict(make=lambda s=_seed, h=_h, t=_tr, se=_s, n=_n: akamegashiwa(n, s, h, t, se),
                          height_m=_h, habitat=("farm",), share=SHARES[_k], seasons=_bits, regions=REGIONS,
                          **({"place_with": _base} if _s else {}))
