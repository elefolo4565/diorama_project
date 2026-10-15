"""木の葉。葉の絵 (透過 PNG) を描き、その絵を貼る板 (葉の板) を枝先に何百枚も並べて木を作る。

葉の絵は 2x2 に4種類の小枝を並べた 1 枚の画像で、板ごとにどれか 1 つを貼る。
板は表と裏の 2 枚を重ね (どちらも同じ法線)、法線は樹冠の中心から外向きにそろえる。
こうすると、一枚一枚の板ではなく樹冠全体が丸く光を受けたように見える (ゲームの木のよくある作り方)。
頂点の色 (R) は樹冠の奥ほど暗くした値で、UE のマテリアルが葉の色に掛ける (奥の葉の陰)。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import scenery_meshes as sm
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

TEXTURE_SIZE = 1024
CELLS = 2  # 2x2 の小枝

# 葉の種類: 絵の描き方と色 (sRGB)。マテリアル名は scenery_meshes.MATERIALS と UE の setup_project.py の LEAF_TEXTURES と同じ
LEAF_KINDS = {
    "FD_Leaf_Broad": dict(texture="T_FD_Leaf_Broad.png", style="broad", leaves=300, length=(36, 54), width=0.42,
                          colors=((38, 62, 22), (52, 80, 28), (70, 98, 36), (30, 50, 20))),
    "FD_Leaf_Kusu": dict(texture="T_FD_Leaf_Kusu.png", style="broad", leaves=380, length=(28, 40), width=0.45,
                         colors=((52, 84, 28), (68, 102, 34), (86, 118, 42), (40, 68, 24))),
    "FD_Leaf_Pine": dict(texture="T_FD_Leaf_Pine.png", style="pine",
                         colors=((24, 44, 22), (34, 58, 28), (46, 72, 34), (20, 36, 20))),
    "FD_Leaf_Cedar": dict(texture="T_FD_Leaf_Cedar.png", style="cedar",
                          colors=((26, 46, 24), (36, 60, 30), (50, 74, 36), (60, 62, 34))),
    "FD_Leaf_Bamboo": dict(texture="T_FD_Leaf_Bamboo.png", style="bamboo",
                           colors=((64, 102, 34), (84, 124, 42), (104, 140, 52), (50, 84, 30))),
}
TWIG_COLOR = (58, 46, 34)


# ---------------------------------------------------------------- 葉の絵
def _jitter(rgb, r, amount=14):
    k = r.uniform(-amount, amount)
    return tuple(int(max(0, min(255, c + k + r.uniform(-4, 4)))) for c in rgb)


def _leaf_polygon(base, angle, length, width, n=10):
    """先のとがった楕円の葉 (付け根 base から angle の向きに length)。"""
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for side in (1, -1):
        ts = np.linspace(0, 1, n) if side == 1 else np.linspace(1, 0, n)
        for t in ts:
            w = width * length * 0.5 * math.sin(math.pi * t) ** 0.8 * (1 - 0.25 * t) * side
            x, y = t * length, w
            pts.append((base[0] + x * ca - y * sa, base[1] + x * sa + y * ca))
    return pts


def _twigs(r, s, cx, count, spread=0.36):
    """小枝の線: 下の中央から上へ伸びる主軸と、そこから斜めに出る枝。(点の列のリスト)"""
    main = [(cx, s * 0.97)]
    x, y = cx, s * 0.97
    for _ in range(8):
        x += r.uniform(-0.03, 0.03) * s
        y -= 0.1 * s
        main.append((x, y))
    twigs = [main]
    for i in range(count):
        k = r.randrange(2, len(main) - 1)
        x, y = main[k]
        side = 1 if i % 2 else -1
        ang = -math.pi / 2 + side * r.uniform(0.5, 1.1)
        length = r.uniform(0.18, spread) * s
        pts = [(x, y)]
        for t in (0.5, 1.0):
            pts.append((x + math.cos(ang) * length * t, y + math.sin(ang) * length * t - 0.03 * s * t))
        twigs.append(pts)
    return twigs


def _points_along(twigs, r, count):
    out = []
    for _ in range(count):
        tw = twigs[r.randrange(len(twigs))]
        k = r.randrange(len(tw) - 1)
        t = r.random()
        (x0, y0), (x1, y1) = tw[k], tw[k + 1]
        out.append(((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t), math.atan2(y1 - y0, x1 - x0)))
    return out


def _draw_cell(draw, r, kind, s, ox, oy):
    """1 つの小枝を s x s の範囲 (左上 ox, oy) に描く。"""
    spec = LEAF_KINDS[kind]
    style, colors = spec["style"], spec["colors"]

    def P(p):
        return (ox + p[0], oy + p[1])

    def shade(col, y):  # 上の葉ほど明るい
        k = 1.12 - 0.3 * (y / s)
        return tuple(int(min(255, c * k)) for c in col)

    if style == "broad":
        twigs = _twigs(r, s, s * 0.5, 10, spread=0.46)
        for tw in twigs:
            draw.line([P(p) for p in tw], fill=TWIG_COLOR, width=max(2, s // 120))
        for (p, a) in _points_along(twigs, r, spec["leaves"]):
            ang = a + r.choice((1, -1)) * r.uniform(0.4, 1.4)
            length = r.uniform(*spec["length"]) * s / 512
            col = shade(_jitter(r.choice(colors), r), p[1])
            base = (p[0] + math.cos(ang) * 3, p[1] + math.sin(ang) * 3)
            poly = [P(q) for q in _leaf_polygon(base, ang, length, spec["width"])]
            draw.polygon(poly, fill=col)
            tip = (base[0] + math.cos(ang) * length * 0.9, base[1] + math.sin(ang) * length * 0.9)
            draw.line([P(base), P(tip)], fill=tuple(int(c * 0.75) for c in col), width=1)  # 葉脈
    elif style == "pine":
        twigs = _twigs(r, s, s * 0.5, 8, spread=0.4)
        for tw in twigs:
            draw.line([P(p) for p in tw], fill=TWIG_COLOR, width=max(3, s // 90))
        # 針のような葉が束になって、枝先へ向かって扇形に出る
        for (p, a) in _points_along(twigs, r, 130):
            col = shade(_jitter(r.choice(colors), r), p[1])
            for _ in range(14):
                ang = a + r.uniform(-1.0, 1.0)
                length = r.uniform(45, 75) * s / 512
                q = (p[0] + math.cos(ang) * length, p[1] + math.sin(ang) * length)
                draw.line([P(p), P(q)], fill=col, width=max(1, s // 300))
    elif style == "cedar":
        twigs = _twigs(r, s, s * 0.5, 12, spread=0.45)
        for tw in twigs:
            draw.line([P(p) for p in tw], fill=TWIG_COLOR, width=max(2, s // 130))
        # スギの葉は短い鱗のような葉が小枝をびっしり覆う。小さな楕円を重ねて、少し垂れた房にする
        for (p, a) in _points_along(twigs, r, 2600):
            col = shade(_jitter(r.choice(colors[:3]) if r.random() < 0.93 else colors[3], r, 10), p[1])
            ex, ey = r.uniform(5, 9) * s / 512, r.uniform(2.5, 4.5) * s / 512
            x, y = p[0] + r.uniform(-9, 9) * s / 512, p[1] + r.uniform(-6, 9) * s / 512
            draw.ellipse([P((x - ex, y - ey)), P((x + ex, y + ey))], fill=col)
    elif style == "bamboo":
        twigs = _twigs(r, s, s * 0.5, 8, spread=0.4)
        for tw in twigs:
            draw.line([P(p) for p in tw], fill=(96, 110, 52), width=max(2, s // 150))
        # 細長い笹の葉が、小枝の先から数枚ずつ垂れ下がる
        tips = [tw[-1] for tw in twigs] + [p for p, _ in _points_along(twigs, r, 22)]
        for p in tips:
            for _ in range(r.randrange(4, 7)):
                ang = math.pi / 2 + r.uniform(-1.3, 1.3)
                length = r.uniform(80, 130) * s / 512
                col = shade(_jitter(r.choice(colors), r), p[1])
                poly = [P(q) for q in _leaf_polygon(p, ang, length, 0.14, n=12)]
                draw.polygon(poly, fill=col)


def _bleed(img):
    """透明な所の色を、近くの葉の色で埋める (縮小したときに縁が黒くにじまないように)。"""
    arr = np.asarray(img).astype(np.float32)
    rgb, a = arr[:, :, :3], arr[:, :, 3:4] / 255
    out = rgb.copy()
    filled = a >= 0.5
    pre_img = Image.fromarray(np.clip(rgb * a, 0, 255).astype(np.uint8))
    a_img = Image.fromarray(np.clip(a[:, :, 0] * 255, 0, 255).astype(np.uint8))
    for radius in (2, 6, 16, 40, 100):
        pre = np.asarray(pre_img.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)
        al = np.asarray(a_img.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)[:, :, None] / 255
        new = ~filled & (al > 0.02)
        out = np.where(new, pre / np.maximum(al, 1e-3), out)
        filled = filled | new
    mean = (rgb * a).sum((0, 1)) / max(a.sum(), 1e-3)
    out = np.where(filled, out, mean)
    return np.concatenate([np.clip(out, 0, 255), a * 255], 2).astype(np.uint8)


def leaf_texture(kind, path, size=TEXTURE_SIZE, seed=7):
    """葉の種類 kind の絵 (2x2 の小枝、透過 PNG) を path に書く。"""
    r = random.Random(f"{kind}{seed}")
    big = size * 2  # 2 倍で描いて縮小し、縁をなめらかにする
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // CELLS
    for j in range(CELLS):
        for i in range(CELLS):
            _draw_cell(draw, r, kind, cell, i * cell, j * cell)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(_bleed(img)).save(path)


# ---------------------------------------------------------------- 葉の板
class Foliage:
    """1 本の木の葉の板をためて、Mesh に書き込む。center / radii は樹冠全体の楕円体 (法線と陰の基準)。"""

    def __init__(self, material, rng, center, radii):
        self.material, self.rng = material, rng
        self.center, self.radii = np.asarray(center, float), np.asarray(radii, float)
        self.verts, self.normals, self.uvs, self.colors = [], [], [], []

    def card(self, p, up, size, aspect=1.0, facing=None, light=None):
        """p を中心に、葉の絵の上向きが up になる板を 1 枚置く。facing は板の表の向きの目安 (省略時はランダム)。"""
        rng = self.rng
        up = np.asarray(up, float)
        up /= np.linalg.norm(up)
        f = np.asarray(facing, float) if facing is not None else rng.normal(size=3)
        side = np.cross(up, f)
        if np.linalg.norm(side) < 1e-6:
            side = np.cross(up, [0.3, 0.2, 1.0])
        side /= np.linalg.norm(side)
        roll = rng.uniform(-0.6, 0.6)  # 少しねじって板どうしの向きをばらす
        side = side * math.cos(roll) + np.cross(up, side) * math.sin(roll)
        w, h = size * aspect * 0.5, size * 0.5
        p = np.asarray(p, float)
        corners = [p - side * w - up * h, p + side * w - up * h, p + side * w + up * h, p - side * w + up * h]
        ci, cj = rng.integers(0, CELLS), rng.integers(0, CELLS)
        u0, u1 = ci / CELLS, (ci + 1) / CELLS
        v0, v1 = cj / CELLS, (cj + 1) / CELLS
        if rng.random() < 0.5:  # 左右反転で絵の種類を倍に見せる
            u0, u1 = u1, u0
        uv = [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
        for c, t in zip(corners, uv):
            d = (c - self.center) / self.radii
            dist = np.linalg.norm(d)
            n = d / max(dist, 1e-6) * 0.8 + np.array([0, 0, 0.2])
            self.normals.append(n / np.linalg.norm(n))
            if light is None:
                # 樹冠の外側・上ほど明るく、奥と下は暗い (奥の葉は周りの葉の陰になる)
                lit = 0.3 + 0.55 * min(dist, 1.0) ** 1.5 + 0.15 * max(d[2], 0.0)
            else:
                lit = light
            self.colors.append(min(lit, 1.0))
            self.verts.append(c)
            self.uvs.append(t)

    def write(self, mesh):
        if not self.verts:
            return mesh
        v = np.array(self.verts)
        k = len(v) // 4
        q = np.arange(k)[:, None] * 4
        front = np.concatenate([q + [0, 1, 2], q + [0, 2, 3]])
        back = front[:, ::-1]  # 裏面 (同じ法線)。表裏どちらから見ても樹冠の光り方が同じになる
        mesh.add_cards(self.material, v, np.concatenate([front, back]), np.array(self.normals), np.array(self.uvs),
                       np.array(self.colors))
        return mesh


def clump(fol, center, radius, count, size, flat=1.0, up_bias=0.5):
    """center のまわり radius の楕円体の中に、葉の板を count 枚。板の上向きは外向き (枝先へ伸びる向き) にする。"""
    rng = fol.rng
    c = np.asarray(center, float)
    for _ in range(count):
        d = rng.normal(size=3)
        d[2] = d[2] * 0.8 + up_bias * 0.5
        d /= np.linalg.norm(d)
        p = c + d * np.array([radius, radius, radius * flat]) * rng.uniform(0.25, 1.0) ** 0.5
        out = p - fol.center
        out[2] = abs(out[2]) * 0.5 + 0.5 * np.linalg.norm(out[:2]) * 0.3
        up = d * 0.6 + out / max(np.linalg.norm(out), 1e-6) * 0.4 + [0, 0, 0.4]
        fol.card(p, up, size * rng.uniform(0.8, 1.2), facing=d)


# ---------------------------------------------------------------- 木
BROADLEAF_KINDS = {
    # trunk = 枝分かれまでの高さ、width = 樹冠の半径、depth = 樹冠の半分の高さ (どれも樹高に対する割合)
    "shii": dict(trunk=0.25, width=0.5, depth=0.42, subs=(5, 7), leaf="FD_Leaf_Broad"),   # スダジイ: こんもり丸い
    "tabu": dict(trunk=0.28, width=0.55, depth=0.4, subs=(6, 8), leaf="FD_Leaf_Broad"),   # タブノキ: 少しいびつ
    "kusu": dict(trunk=0.25, width=0.72, depth=0.36, subs=(7, 9), leaf="FD_Leaf_Kusu"),   # クスノキ: 横に広く明るい緑
}


def broadleaf(name, seed, height=9.0, kind="shii"):
    """シイ・タブ・クスノキのような常緑広葉樹。幹から太い枝が数本に分かれ、その先の小枝に葉の房がこんもり付く。"""
    p = BROADLEAF_KINDS[kind]
    rng = Rng(seed)
    m = Mesh(name)
    th, big_r, half_h = height * p["trunk"], height * p["width"], height * p["depth"]
    cz = height - half_h
    lean = rng.normal(size=2) * 0.04 * height
    fork = np.array([lean[0], lean[1], th])
    r0 = 0.033 * height
    trunk = bezier((0, 0, -0.3), (lean[0] * 0.2, lean[1] * 0.2, th * 0.5), fork, 6)
    bark_tube(m, "FD_Bark", trunk, np.linspace(r0 * 1.35, r0 * 0.9, 6), n=16)
    fol = Foliage(p["leaf"], rng, (lean[0], lean[1], cz), (big_r, big_r, half_h))
    k = int(rng.integers(*p["subs"]) + 1)
    for j in range(k):
        if j == 0:
            az, el = 0.0, math.pi / 2  # てっぺん
        else:
            az, el = 2 * math.pi * j / (k - 1) + rng.uniform(-0.35, 0.35), rng.uniform(-0.4, 0.8)
        dist = rng.uniform(0.45, 0.62)
        sc = np.array([big_r * dist * math.cos(el) * math.cos(az) + lean[0],
                       big_r * dist * math.cos(el) * math.sin(az) + lean[1], cz + half_h * dist * math.sin(el)])
        sr = big_r * rng.uniform(0.42, 0.56)
        inner = fork + (sc - fork) * 0.9
        mid = fork + (inner - fork) * 0.5 + [0, 0, -0.1 * height * (1 - math.sin(el))]
        bark_tube(m, "FD_Bark", bezier(fork - [0, 0, 0.3], mid, inner, 6), np.linspace(r0 * 0.6, 0.05, 6), n=7)
        # 房 (小枝の先の葉のかたまり) を丸みの表面近くに並べ、太い枝の先から細い枝でつなぐ
        for _ in range(int(rng.integers(12, 17))):
            d = rng.normal(size=3)
            d[2] = d[2] * 0.8 + 0.45
            d /= np.linalg.norm(d)
            fp = sc + d * np.array([sr, sr, sr * 0.8]) * rng.uniform(0.6, 0.9)
            if rng.random() < 0.45:
                bark_tube(m, "FD_Bark", np.array([inner, (inner + fp) / 2 + [0, 0, 0.15], fp]), [0.05, 0.035, 0.02], n=5)
            clump(fol, fp, sr * rng.uniform(0.3, 0.42), 11, size=sr * 0.55)
        clump(fol, sc, sr * 0.55, 10, size=sr * 0.6)  # 奥を埋める葉 (すき間から空が抜けすぎないように)
    return fol.write(m)


def bush(name, seed):
    """低木 (トベラ・シャリンバイなど) の茂み。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = Foliage("FD_Leaf_Broad", rng, (0, 0, 0.5), (1.3, 1.3, 0.8))
    for _ in range(3):
        c = (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0.45, 0.7))
        clump(fol, c, rng.uniform(0.6, 0.85), 22, size=0.75, flat=0.75)
    return fol.write(m)


def pine(name, seed, height=9.0):
    """クロマツ。海風で傾いて曲がった幹から横へ枝を張り、枝先に針葉の平たい段 (雲のような房) が付く。"""
    rng = Rng(seed)
    m = Mesh(name)
    az = rng.uniform(0, 2 * math.pi)
    lean_d = np.array([math.cos(az), math.sin(az), 0.0])
    side = np.cross([0, 0, 1], lean_d)
    lean, phase = rng.uniform(0.12, 0.28) * height, rng.uniform(0, 2 * math.pi)
    s = np.linspace(0, 1, 10)
    trunk = (lean_d * (lean * s ** 1.6)[:, None] + side * (0.05 * height * np.sin(s * math.pi * 1.5 + phase))[:, None]
             + np.c_[np.zeros((10, 2)), s * height * 0.9])
    trunk[0, 2] -= 0.3
    r0 = 0.035 * height
    bark_tube(m, "FD_PineBark", trunk, np.linspace(r0 * 1.3, r0 * 0.3, 10), n=16)
    top = trunk[-1]
    fol = Foliage("FD_Leaf_Pine", rng, (top[0] * 0.7, top[1] * 0.7, height * 0.72), (height * 0.4, height * 0.4, height * 0.3))

    def at(t):
        return np.array([np.interp(t, s, trunk[:, k]) for k in range(3)])

    def pad(c, r):
        # 平たい段: 板はほぼ水平に、絵の上向きは外 (枝先) へ
        for _ in range(int(r * 40)):
            a, q = rng.uniform(0, 2 * math.pi), math.sqrt(rng.uniform(0, 1))
            p = c + [r * q * math.cos(a), r * q * math.sin(a), 0.25 * r * (1 - q * q) + rng.uniform(-0.12, 0.12) * r]
            out = np.array([math.cos(a), math.sin(a), 0.0])
            up = out * 0.8 + [0, 0, rng.uniform(0.1, 0.6)]
            fol.card(p, up, r * rng.uniform(0.65, 0.95), facing=[0, 0, 1] + rng.normal(size=3) * 0.35)

    n_pads = int(rng.integers(6, 10))
    for t in sorted(rng.uniform(0.45, 0.92, size=n_pads)):
        base = at(t)
        a = rng.uniform(0, 2 * math.pi)
        d = np.array([math.cos(a), math.sin(a), rng.uniform(0.05, 0.35)])
        d /= np.linalg.norm(d)
        length = (1.15 - t) * height * 0.38 * rng.uniform(0.8, 1.2) + 0.6
        end = base + d * length
        path = bezier(base, base + d * length * 0.5 - [0, 0, 0.25], end, 6)
        bark_tube(m, "FD_PineBark", path, np.linspace(r0 * 0.45 * (1.1 - t), 0.04, 6), n=6)
        pad(end + [0, 0, 0.2], rng.uniform(1.1, 1.7) * (1.2 - t * 0.4))
    pad(top + [0, 0, 0.1], rng.uniform(1.6, 2.2))
    return fol.write(m)


def cedar(name, seed, height=18.0):
    """スギ (山の植林地)。まっすぐな幹の下の方は枝打ちされて裸で、上は輪のように出た枝の房が細長い円すい形の樹冠を作る。"""
    rng = Rng(seed)
    m = Mesh(name)
    lean = rng.normal(size=2) * 0.01 * height
    s = np.linspace(0, 1, 6)
    trunk = np.c_[lean[0] * s, lean[1] * s, s * height * 0.97]
    trunk[0, 2] -= 0.3
    bark_tube(m, "FD_BarkCedar", trunk, np.linspace(0.018 * height, 0.03, 6), n=14)
    crown_base = height * rng.uniform(0.3, 0.4)
    mid_z = (crown_base + height) / 2
    fol = Foliage("FD_Leaf_Cedar", rng, (lean[0], lean[1], mid_z), (height * 0.13, height * 0.13, (height - crown_base) / 2))

    def radius_at(z):
        t = (z - crown_base) / (height - crown_base)
        return 0.45 + (1 - t) * height * 0.12

    z = crown_base
    while z < height - 0.4:
        rz = radius_at(z)
        nb, ph = int(rng.integers(4, 7)), rng.uniform(0, 2 * math.pi)
        axis = np.array([lean[0] * z / height, lean[1] * z / height, z])
        for b in range(nb):
            a = ph + 2 * math.pi * b / nb + rng.uniform(-0.3, 0.3)
            d = np.array([math.cos(a), math.sin(a), rng.uniform(-0.35, -0.1)])
            d /= np.linalg.norm(d)
            bark_tube(m, "FD_BarkCedar", np.array([axis, axis + d * rz * 0.9]), [0.03, 0.012], n=4)
            # 枝に沿って、少し垂れた房の板を外向きに並べる
            for q in np.linspace(0.2, 1.0, 5):
                p = axis + d * rz * q + rng.normal(size=3) * 0.15
                fol.card(p, d + [0, 0, -0.15], rz * 0.8 + 0.5, aspect=0.9, facing=[0, 0, 1] + rng.normal(size=3) * 0.7)
        z += rng.uniform(0.45, 0.65)
    for _ in range(3):  # てっぺん
        fol.card(trunk[-1] + [0, 0, 0.3], [0, 0, 1], 1.0, aspect=0.6)
    return fol.write(m)


def bamboo(name, seed, height=14.0):
    """モウソウチクの竹林のひとかたまり。まっすぐな稈 (節のふくらみ付き) の先がしなり、上の方の細い枝に笹の葉が垂れる。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = Foliage("FD_Leaf_Bamboo", rng, (0, 0, height * 0.72), (3.5, 3.5, height * 0.3))
    for _ in range(int(rng.integers(10, 14))):
        base = np.array([rng.uniform(-2.0, 2.0), rng.uniform(-2.0, 2.0), -0.3])
        h = height * rng.uniform(0.8, 1.1)
        r = 0.075 * rng.uniform(0.8, 1.15)
        bend = rng.normal(size=2) * 0.1 * h
        s = np.linspace(0, 1, 14)
        path = base + np.c_[bend[0] * s ** 3, bend[1] * s ** 3, s * h]
        bark_tube(m, "FD_BambooCulm", path, r * (1 - 0.65 * s), n=8)
        for z in np.arange(0.4, h * 0.55, rng.uniform(0.35, 0.45)):  # 節
            q = base + [bend[0] * (z / h) ** 3, bend[1] * (z / h) ** 3, z]
            m.add("FD_BambooCulm", *sm.cylinder(q - [0, 0, 0.02], q + [0, 0, 0.02], r * 1.12 * (1 - 0.65 * z / h), n=8))
        flow = np.array([bend[0], bend[1], 0.0]) / max(np.linalg.norm(bend), 1e-6)
        for t in np.linspace(0.45, 0.97, 9):
            node = base + [bend[0] * t ** 3, bend[1] * t ** 3, t * h]
            for _ in range(3):
                a = rng.uniform(0, 2 * math.pi)
                d = np.array([math.cos(a), math.sin(a), 0.0]) + flow * 0.8 + [0, 0, rng.uniform(-0.2, 0.3)]
                d /= np.linalg.norm(d)
                length = rng.uniform(0.7, 1.3) * (1.3 - t * 0.6)
                end = node + d * length
                bark_tube(m, "FD_BambooCulm", np.array([node, (node + end) / 2 + [0, 0, 0.05], end]), [0.015, 0.011, 0.007], n=4)
                for q in (0.35, 0.7, 1.0):
                    fol.card(node + (end - node) * q, d + [0, 0, 0.2], rng.uniform(0.8, 1.2) * (1.25 - t * 0.4),
                             facing=[0, 0, 1] + rng.normal(size=3) * 0.6)
    return fol.write(m)
