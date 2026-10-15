"""景観物 (夫婦岩・鳥居・しめ縄・ガードレール・木) の形を作り、glTF で書き出す。

形は UE の座標 (X = 東, Y = 南, Z = 上, 単位 m) で組み立て、書き出すときに glTF の座標 (Y が上) へ直す。
UE の glTF 取り込みは (X, Y, Z) -> (X, Z, Y) と入れ替えて m を cm にするので、UE に入ると元の向きに戻る。

閉じた形だけを作り、面の向き (表裏) は体積の符号で自動的にそろえる。
法線は 60° より緩い角はなめらかに、それより急な角は角張って見えるように付ける。
"""

import base64
import json
import math

import random

import numpy as np

SMOOTH_ANGLE_DEG = 60.0

# 色はリニア (sRGB ではない)。同じ名前のマテリアルはどのメッシュでも同じ値にする (取り込み先で共有されるため)
MATERIALS = {
    "FD_Rock": dict(color=(0.075, 0.066, 0.056), roughness=0.85),
    "FD_RockTop": dict(color=(0.045, 0.085, 0.025), roughness=0.9),
    "FD_Shimenawa": dict(color=(0.32, 0.25, 0.11), roughness=0.95),
    "FD_ToriiWhite": dict(color=(0.80, 0.80, 0.77), roughness=0.45),
    "FD_Guardrail": dict(color=(0.72, 0.72, 0.70), roughness=0.35),
    "FD_GuardrailPost": dict(color=(0.55, 0.55, 0.54), roughness=0.5),
    # 樹皮 (tools/terrain/bark.py の絵と凹凸を貼る。UE では setup_project.py が樹皮用のマテリアルに差し替える)
    "FD_Bark": dict(color=(1, 1, 1), roughness=0.9, texture="T_FD_Bark_D.png", normal="T_FD_Bark_N.png"),
    "FD_PineBark": dict(color=(1, 1, 1), roughness=0.9, texture="T_FD_PineBark_D.png", normal="T_FD_PineBark_N.png"),
    "FD_PalmTrunk": dict(color=(1, 1, 1), roughness=0.9, texture="T_FD_PalmTrunk_D.png", normal="T_FD_PalmTrunk_N.png"),
    "FD_LeafPalm": dict(color=(0.045, 0.10, 0.025), roughness=0.6),
    "FD_LeafPalmOld": dict(color=(0.060, 0.080, 0.025), roughness=0.65),
    "FD_BambooCulm": dict(color=(1, 1, 1), roughness=0.5, texture="T_FD_BambooCulm_D.png", normal="T_FD_BambooCulm_N.png"),
    "FD_BarkCedar": dict(color=(1, 1, 1), roughness=0.9, texture="T_FD_BarkCedar_D.png", normal="T_FD_BarkCedar_N.png"),
    # 葉の板 (tools/terrain/foliage.py)。葉の絵を貼り、絵の透明な所を切り抜く。UE では setup_project.py が葉用のマテリアルに差し替える
    "FD_Leaf_Broad": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_Broad.png", alpha=True),
    "FD_Leaf_Kusu": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_Kusu.png", alpha=True),
    "FD_Leaf_Pine": dict(color=(1, 1, 1), roughness=0.7, texture="T_FD_Leaf_Pine.png", alpha=True),
    "FD_Leaf_Cedar": dict(color=(1, 1, 1), roughness=0.7, texture="T_FD_Leaf_Cedar.png", alpha=True),
    "FD_Leaf_Bamboo": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_Bamboo.png", alpha=True),
    # 花の板 (tools/terrain/flowers.py)。葉の板と同じく、UE では setup_project.py が葉用のマテリアルに差し替える
    # 落葉樹の葉の板 (tools/terrain/flowers.py)。季節で色が変わる
    "FD_Leaf_MapleGreen": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_MapleGreen.png", alpha=True),
    "FD_Leaf_MapleRed": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_MapleRed.png", alpha=True),
    "FD_Leaf_HazeRed": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_HazeRed.png", alpha=True),
    "FD_Leaf_AutumnOrange": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_AutumnOrange.png", alpha=True),
    "FD_Leaf_Turning": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Leaf_Turning.png", alpha=True),
    "FD_Flower_Nanohana": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Nanohana.png", alpha=True),
    "FD_Flower_Renge": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Renge.png", alpha=True),
    "FD_Flower_Hydrangea": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Hydrangea.png", alpha=True),
    "FD_Flower_Sunflower": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Sunflower.png", alpha=True),
    "FD_Flower_Higanbana": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Higanbana.png", alpha=True),
    "FD_Flower_Cosmos": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Cosmos.png", alpha=True),
    "FD_Flower_Suisen": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Suisen.png", alpha=True),
    "FD_Flower_Sakura": dict(color=(1, 1, 1), roughness=0.6, texture="T_FD_Flower_Sakura.png", alpha=True),
    # 草 (tools/terrain/build_grass.py)。UE では setup_project.py が草用のマテリアル (地面と同じ色のむら、風でゆれる) に差し替える
    "FD_Grass": dict(color=(0.04, 0.07, 0.025), roughness=0.6),
    # 道路の付属物
    "FD_RoadWhite": dict(color=(0.62, 0.62, 0.60), roughness=0.6),      # 区画線 (白)
    "FD_RoadYellow": dict(color=(0.70, 0.40, 0.03), roughness=0.6),     # 区画線 (黄、はみ出し禁止)
    "FD_Concrete": dict(color=(0.30, 0.29, 0.27), roughness=0.9),       # 側溝
    "FD_PoleConcrete": dict(color=(0.40, 0.39, 0.37), roughness=0.85),  # 電柱
    "FD_Steel": dict(color=(0.38, 0.38, 0.37), metallic=0.6, roughness=0.45),
    "FD_Insulator": dict(color=(0.55, 0.55, 0.57), roughness=0.3),
    "FD_Wire": dict(color=(0.02, 0.02, 0.02), roughness=0.5),
    "FD_LampBody": dict(color=(0.55, 0.56, 0.56), roughness=0.4),   # 防犯灯の本体
    # 防犯灯の光る面。UE では setup_project.py が夜だけ光るマテリアル (M_FD_LampGlow) に差し替える
    "FD_LampGlow": dict(color=(0.85, 0.85, 0.82), roughness=0.3),
    # 建物 (tools/terrain/buildings.py)。色は頂点の色。UE では setup_project.py が、窓を描いて夜に灯すマテリアル
    # (M_FD_BuildingWall) と、瓦の段を付けるマテリアル (M_FD_BuildingRoof) に差し替える
    "FD_BuildingWall": dict(color=(1, 1, 1), roughness=0.85),
    "FD_BuildingRoof": dict(color=(1, 1, 1), roughness=0.6),
    "FD_SignBack": dict(color=(0.30, 0.30, 0.30), metallic=0.5, roughness=0.5),
    "FD_SignWhite": dict(color=(0.78, 0.78, 0.78), roughness=0.4),
    "FD_SignBlue": dict(color=(0.0, 0.06, 0.30), roughness=0.4),
    "FD_SignRed": dict(color=(0.55, 0.02, 0.02), roughness=0.4),
    "FD_SignYellow": dict(color=(0.85, 0.55, 0.0), roughness=0.4),
    "FD_SignBlack": dict(color=(0.015, 0.015, 0.015), roughness=0.5),
}


class Rng:
    """numpy.random の代わり (Windows のアプリ制御で numpy.random の DLL が止められる PC があるため)。
    使う関数だけを、標準の random で同じ呼び方にしたもの。"""

    def __init__(self, seed):
        self.r = random.Random(seed)

    def _fill(self, size, f):
        if size is None:
            return f()
        return np.array([f() for _ in range(int(np.prod(size)))]).reshape(size)

    def uniform(self, lo=0.0, hi=1.0, size=None):
        return self._fill(size, lambda: self.r.uniform(lo, hi))

    def normal(self, size=None):
        return self._fill(size, lambda: self.r.gauss(0.0, 1.0))

    def random(self, size=None):
        return self._fill(size, self.r.random)

    def integers(self, lo, hi):
        return self.r.randrange(lo, hi)

    def choice(self, items, size):
        return np.array([self.r.choice(items) for _ in range(size)])


class Mesh:
    def __init__(self, name, flat=False):
        self.name = name
        self.parts = []  # (material, verts (N,3) UE m, tris (M,3))
        self.cards = []  # (material, verts, tris, normals, uvs, shade)。add_cards を参照
        self.flat = flat  # True なら面ごとの法線 (角張った細長い形。大きなメッシュでも書き出しが速い)

    def add(self, material, verts, tris):
        self.parts.append((material, np.asarray(verts, float), np.asarray(tris, int)))
        return self

    def add_cards(self, material, verts, tris, normals, uvs, shade, orient=False, uv1=None):
        """開いた面 (葉の板・樹皮の筒・草の葉)。法線・UV・頂点の明るさ (0..1、(N,3) なら頂点の色 RGB) をそのまま書き出す。
        orient=True なら、各面の表を頂点の法線の側へ向ける (葉の板は表裏 2 枚を重ねるので向きを直さない)。
        uv1 は 2 つ目の UV (建物ごとの乱数など、マテリアルへ渡す値。glTF の TEXCOORD_1)。"""
        self.cards.append((material, np.asarray(verts, float), np.asarray(tris, int), np.asarray(normals, float),
                           np.asarray(uvs, float), np.asarray(shade, float), orient,
                           None if uv1 is None else np.asarray(uv1, float)))
        return self

    def merge(self, other, offset=(0, 0, 0)):
        for mat, v, t in other.parts:
            self.parts.append((mat, v + np.asarray(offset, float), t))
        return self

    def bounds(self):
        v = np.concatenate([p[1] for p in self.parts] + [c[1] for c in self.cards])
        return v.min(0), v.max(0)


# ---------------------------------------------------------------- 形の部品
def sweep(rings, cap_start=True, cap_end=True):
    """同じ点数の輪を順につないだ筒。両端はふたをする。rings: (K, N, 3)。"""
    rings = np.asarray(rings, float)
    k, n, _ = rings.shape
    verts = list(rings.reshape(-1, 3))
    tris = []
    for i in range(k - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c, d = (i + 1) * n + (j + 1) % n, (i + 1) * n + j
            tris += [(a, b, c), (a, c, d)]
    if cap_start:
        verts.append(rings[0].mean(0))
        c0 = len(verts) - 1
        tris += [(c0, (j + 1) % n, j) for j in range(n)]
    if cap_end:
        verts.append(rings[-1].mean(0))
        cl = len(verts) - 1
        base = (k - 1) * n
        tris += [(cl, base + j, base + (j + 1) % n) for j in range(n)]
    return np.array(verts), np.array(tris)


def ring(center, radius_x, radius_y, n, phase=0.0):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False) + phase
    cx, cy, cz = center
    return np.stack([cx + radius_x * np.cos(a), cy + radius_y * np.sin(a), np.full(n, cz)], 1)


def cylinder(p0, p1, r0, r1=None, n=16):
    """p0 から p1 へ向かう円柱 (円すい台)。"""
    r1 = r0 if r1 is None else r1
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    axis = p1 - p0
    axis /= np.linalg.norm(axis)
    u = np.cross(axis, [0, 0, 1] if abs(axis[2]) < 0.9 else [1, 0, 0])
    u /= np.linalg.norm(u)
    w = np.cross(axis, u)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    circ = np.cos(a)[:, None] * u + np.sin(a)[:, None] * w
    return sweep([p0 + r0 * circ, p1 + r1 * circ])


def box(center, size, yaw_deg=0.0):
    sx, sy, sz = np.asarray(size, float) / 2
    c = np.asarray(center, float)
    sq = np.array([[sx, sy], [-sx, sy], [-sx, -sy], [sx, -sy]])
    t = math.radians(yaw_deg)
    rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    sq = sq @ rot.T
    lo = np.c_[sq, np.full(4, -sz)] + c
    hi = np.c_[sq, np.full(4, sz)] + c
    return sweep([lo, hi])


def swept_rect(path, width, height):
    """path (K,3) に沿って、幅 width (水平) x 高さ height の長方形断面を流した棒。"""
    path = np.asarray(path, float)
    rings = []
    for i, p in enumerate(path):
        t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        side = np.cross([0, 0, 1], t)
        side /= np.linalg.norm(side)
        up = np.cross(t, side)
        hw, hh = width / 2, height / 2
        rings.append([p + side * hw + up * hh, p - side * hw + up * hh, p - side * hw - up * hh, p + side * hw - up * hh])
    return sweep(rings)


def icosphere(subdiv=2):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    verts = [np.array(p, float) / np.linalg.norm(p) for p in v]
    for _ in range(subdiv):
        cache, nf = {}, []

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = verts[a] + verts[b]
                verts.append(m / np.linalg.norm(m))
                cache[key] = len(verts) - 1
            return cache[key]

        for a, b, c in f:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return np.array(verts), np.array(f)


class Noise:
    """方向ベクトルや座標に対するなめらかな揺らぎ (いくつかの正弦波の和)。"""

    def __init__(self, rng, octaves=((2.0, 0.5), (4.5, 0.3), (9.0, 0.15))):
        self.waves = []
        for freq, amp in octaves:
            for _ in range(3):
                d = rng.normal(size=3)
                self.waves.append((d / np.linalg.norm(d) * freq, rng.uniform(0, 2 * math.pi), amp / 3))

    def __call__(self, p):
        p = np.atleast_2d(p)
        return sum(a * np.sin(p @ w + ph) for w, ph, a in self.waves)


def blob(center, radii, rng, subdiv=2, roughness=0.25):
    """でこぼこの球 (葉のかたまり・茂み)。"""
    v, f = icosphere(subdiv)
    n = Noise(rng)
    v = v * (1 + roughness * n(v))[:, None]
    return v * np.asarray(radii, float) + np.asarray(center, float), f


# ---------------------------------------------------------------- 景観物
def meoto_rock(name, height, radius, seed, top_green=True):
    """夫婦岩の片方。海底 (-4m) から海面上 height m までの、上がすぼまった岩の柱。"""
    rng = Rng(seed)
    noise = Noise(rng, ((1.2, 0.7), (3.0, 0.45), (7.0, 0.25)))
    n_around, levels = 28, 18
    zs = np.linspace(-4.0, height, levels)
    rings = []
    for z in zs:
        t = max(z, 0) / height
        # 下は太く上は丸くすぼまる。てっぺんは小さな平らな面になる
        r = radius * (1.0 - 0.35 * t ** 1.6) * (math.sqrt(max(1 - t ** 6, 0.04)))
        a = np.linspace(0, 2 * math.pi, n_around, endpoint=False)
        dirs = np.stack([np.cos(a), np.sin(a) * 0.82, np.full(n_around, z / height * 0.8)], 1)
        # 縦の割れ目 (高い周波数を角度方向に強く) と、全体のゆがみ
        rr = r * (1 + 0.32 * noise(dirs) + 0.10 * np.sin(a * 7 + 2.1 * noise(dirs * 3)) ** 3)
        rings.append(np.stack([rr * np.cos(a), rr * np.sin(a) * 0.82, np.full(n_around, z)], 1))
    mesh = Mesh(name).add("FD_Rock", *sweep(rings))
    if top_green:
        top_r = radius * 0.65 * 0.4
        v, f = blob((0, 0, height + 0.1), (top_r * 1.4, top_r * 1.2, 0.9), rng, roughness=0.35)
        mesh.add("FD_RockTop", v, f)
    return mesh


def shimenawa(p0, p1, sag=3.0, radius=0.28, n=10, segments=24):
    """p0 と p1 (岩の上の結び目) を結ぶ、垂れ下がった太い縄。原点は p0 と p1 の中点の真下に置く。"""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    origin = (p0 + p1) / 2
    origin[2] = min(p0[2], p1[2]) - sag
    pts = []
    for i in range(segments + 1):
        s = i / segments
        p = p0 + (p1 - p0) * s
        p[2] -= sag * 4 * s * (1 - s)
        pts.append(p - origin)
    pts = np.array(pts)
    rings = []
    for i, p in enumerate(pts):
        t = pts[min(i + 1, segments)] - pts[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        u = np.cross(t, [0, 0, 1])
        u /= np.linalg.norm(u)
        w = np.cross(u, t)
        a = np.linspace(0, 2 * math.pi, n, endpoint=False)
        # 縄をなったねじれを、半径の揺らぎで少しだけ出す
        r = radius * (1 + 0.12 * np.cos(3 * a + i * 1.3))
        rings.append(p + (np.cos(a) * r)[:, None] * u + (np.sin(a) * r)[:, None] * w)
    return Mesh("SM_FD_Shimenawa").add("FD_Shimenawa", *sweep(rings)), origin


def torii(pillar_span=4.6, pillar_height=5.4, pillar_r=0.27):
    """白い明神鳥居。原点は2本の柱の間の地面。通り抜ける向きが +X、柱が並ぶ向きが Y。"""
    m = Mesh("SM_FD_Torii")
    hy = pillar_span / 2
    for y in (-hy, hy):
        m.add("FD_ToriiWhite", *cylinder((0, y, -0.5), (0, y, pillar_height), pillar_r * 1.06, pillar_r, n=24))
        m.add("FD_ToriiWhite", *cylinder((0, y, -0.05), (0, y, 0.45), pillar_r * 1.35, pillar_r * 1.3, n=24))  # 亀腹
    # 貫 (柱を貫いて少し外へ出る横木)
    m.add("FD_ToriiWhite", *box((0, 0, pillar_height - 1.25), (0.26, pillar_span + 1.3, 0.36)))
    # 額束
    m.add("FD_ToriiWhite", *box((0, 0, pillar_height - 0.55), (0.22, 0.42, 1.05)))
    # 島木と笠木 (両端が反り上がる)
    span = pillar_span + 2.4
    ys = np.linspace(-span / 2, span / 2, 25)
    lift = 0.38 * (np.abs(ys) / (span / 2)) ** 2.4
    path = np.stack([np.zeros_like(ys), ys, pillar_height + 0.2 + lift], 1)
    m.add("FD_ToriiWhite", *swept_rect(path[2:-2], 0.42, 0.34))
    m.add("FD_ToriiWhite", *swept_rect(path + [0, 0, 0.32], 0.56, 0.3))
    return m


def guardrail(length=4.0):
    """白いガードレール1区間 (長さ length m)。+X 方向に伸び、支柱は区間の中央。
    道路は -Y 側 (ビームは支柱の -Y 側に付く)。原点は支柱の根元の地面。"""
    m = Mesh("SM_FD_Guardrail")
    m.add("FD_GuardrailPost", *cylinder((0, 0.05, -0.4), (0, 0.05, 0.78), 0.07, n=12))
    m.add("FD_GuardrailPost", *box((0, -0.06, 0.6), (0.1, 0.12, 0.2)))  # ブラケット
    # W 形のビームを3本の板で近似 (上の山・くぼみ・下の山)
    m.add("FD_Guardrail", *box((0, -0.16, 0.68), (length + 0.02, 0.05, 0.13)))
    m.add("FD_Guardrail", *box((0, -0.13, 0.6), (length + 0.02, 0.03, 0.06)))
    m.add("FD_Guardrail", *box((0, -0.16, 0.52), (length + 0.02, 0.05, 0.13)))
    return m


# ---------------------------------------------------------------- 木の部品 (葉のある木は foliage.py)


def bezier(p0, p1, p2, k=6):
    t = np.linspace(0, 1, k)[:, None]
    return (1 - t) ** 2 * np.asarray(p0, float) + 2 * (1 - t) * t * np.asarray(p1, float) + t ** 2 * np.asarray(p2, float)


def tube(path, radii, n=8):
    """path (K,3) に沿って、太さが radii (K) で変わる筒 (幹・枝)。曲がってもねじれないよう断面の向きを引き継ぐ。"""
    path = np.asarray(path, float)
    radii = np.broadcast_to(np.asarray(radii, float), (len(path),))
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rings, u = [], None
    for i, p in enumerate(path):
        t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        if u is None:
            u = np.cross(t, [0, 0, 1] if abs(t[2]) < 0.9 else [1, 0, 0])
        u = u - t * (u @ t)
        u /= np.linalg.norm(u)
        w = np.cross(t, u)
        rings.append(p + radii[i] * (np.cos(a)[:, None] * u + np.sin(a)[:, None] * w))
    return sweep(rings)


def palm(name, seed, height=7.0):
    """カナリーヤシ。太い幹のてっぺんから、羽の形の大きな葉が放射状に垂れる (糸島の海沿いに植えられている)。"""
    rng = Rng(seed)
    m = Mesh(name)
    lean = rng.normal(size=2) * 0.05 * height
    top = np.array([lean[0], lean[1], height])
    k = 24
    s = np.linspace(0, 1, k)
    pts = np.c_[lean[0] * s ** 2, lean[1] * s ** 2, s * height]
    pts[0, 2] -= 0.3
    # 葉の付け根の跡で幹がうろこ状にでこぼこしているのを、太さの段で出す
    radii = 0.42 * (1 - 0.15 * s) * np.where(np.arange(k) % 2, 0.94, 1.04)
    from bark import bark_tube  # bark は scenery_meshes を読み込むので、ここで読む
    bark_tube(m, "FD_PalmTrunk", pts, radii, n=14)
    m.add("FD_PalmTrunk", *cylinder(top - [0, 0, 0.1], top + [0, 0, 0.6], 0.5, 0.3, n=14))  # 葉の付け根のふくらみ
    n_fronds = 24
    for f_i in range(n_fronds):
        az = 2 * math.pi * f_i / n_fronds + rng.uniform(-0.1, 0.1)
        up = rng.uniform(-0.25, 0.9)  # 若い葉は上向き、古い葉は垂れる
        mat = "FD_LeafPalm" if up > 0.25 else "FD_LeafPalmOld"
        length = rng.uniform(3.6, 4.6)
        d = np.array([math.cos(az), math.sin(az), 0.0])
        spine = np.array([top + [0, 0, 0.4] + d * length * t + [0, 0, length * (up * t - 0.75 * t * t)]
                          for t in np.linspace(0, 1, 22)])
        m.add(mat, *swept_rect(spine, 0.08, 0.05))  # 葉軸
        side = np.cross([0, 0, 1], d)
        for i in range(1, len(spine) - 1):
            t = i / (len(spine) - 1)
            leaf_len = 0.95 * math.sin(math.pi * min(t * 1.15, 1.0)) + 0.15
            for sgn in (1, -1):
                droop = rng.uniform(0.15, 0.35)
                tip = spine[i] + side * sgn * leaf_len + d * 0.25 + [0, 0, -droop * leaf_len]
                m.add(mat, *swept_rect(np.array([spine[i], (spine[i] + tip) / 2 + [0, 0, 0.05], tip]), 0.12, 0.02))
    return m




# ---------------------------------------------------------------- 道路の付属物
# 電線は +X 方向に長さ WIRE_SPAN_M の形で作り、UE で X だけ拡大して長さを合わせる
WIRE_SPAN_M = 35.0
WIRE_ORIGIN_Z_M = 9.0   # 電線の形の原点の高さ (電柱の根元から)。傾けたときのずれが小さくなるよう、電線の高さの中ほどにする
POLE_HEIGHT_M = 11.6
POLE_WIRES = (  # (横の位置 m (+Y 側), 高さ m, たるみ m, 太さ m)
    (-0.80, 11.05, 0.45, 0.011), (-0.35, 11.05, 0.45, 0.011), (0.80, 11.05, 0.45, 0.011),  # 高圧線 (腕金の上)
    (-0.30, 9.55, 0.60, 0.013),    # 低圧線
    (0.28, 6.00, 0.85, 0.024),     # 通信ケーブル
)


def profile_sweep(centers, outward, profile):
    """道路に沿った細長い形。centers (K,3) m の各点で、水平の外向き outward (K,2) と上 (Z) で張った面に
    断面 profile [(外向きの位置, 高さ) ...] (凸多角形) を置き、順につなぐ。"""
    centers = np.asarray(centers, float)
    out = np.c_[np.asarray(outward, float), np.zeros(len(centers))]
    prof = np.asarray(profile, float)
    rings = centers[:, None, :] + out[:, None, :] * prof[None, :, 0:1] + np.array([0, 0, 1.0]) * prof[None, :, 1:2]
    return sweep(rings)


def guardrail_post():
    """ガードレールの支柱とブラケット (ビームは道路に沿った1本の形で別に作る)。原点は根元の地面、+Y が道路の外。"""
    m = Mesh("SM_FD_GuardrailPost")
    m.add("FD_GuardrailPost", *cylinder((0, 0.05, -0.4), (0, 0.05, 0.78), 0.07, n=12))
    m.add("FD_GuardrailPost", *box((0, -0.06, 0.6), (0.1, 0.12, 0.2)))  # ブラケット
    return m


# ガードレールのビームの断面 (外向きの位置 m, 高さ m)。支柱の中心から道路側。W 形を3本の板で近似 (上の山・くぼみ・下の山)
GUARDRAIL_BEAMS = (
    ((-0.135, 0.745), (-0.185, 0.745), (-0.185, 0.615), (-0.135, 0.615)),
    ((-0.115, 0.63), (-0.145, 0.63), (-0.145, 0.57), (-0.115, 0.57)),
    ((-0.135, 0.585), (-0.185, 0.585), (-0.185, 0.455), (-0.135, 0.455)),
)


def utility_pole(name, transformer=False):
    """コンクリートの電柱。原点は根元の地面。腕金は Y 方向 (電線は X 方向に張る)。"""
    m = Mesh(name)
    m.add("FD_PoleConcrete", *cylinder((0, 0, -0.5), (0, 0, POLE_HEIGHT_M), 0.17, 0.095, n=14))
    m.add("FD_Steel", *box((0, -0.02, 10.92), (0.09, 2.0, 0.09)))                 # 腕金
    m.add("FD_Steel", *box((0, 0.35, 10.6), (0.05, 0.05, 0.8), 0.0))             # 腕金の支え
    for y, z, _, _ in POLE_WIRES[:3]:
        m.add("FD_Insulator", *cylinder((0, y, 10.96), (0, y, z), 0.05, 0.035, n=8))
    m.add("FD_Steel", *box((0, -0.15, 9.55), (0.06, 0.4, 0.06)))                  # 低圧線の金具
    m.add("FD_Insulator", *cylinder((0, -0.30, 9.5), (0, -0.30, 9.6), 0.04, n=8))
    m.add("FD_Steel", *box((0, 0.17, 6.0), (0.05, 0.25, 0.05)))                   # 通信ケーブルの金具
    if transformer:  # 柱上変圧器
        m.add("FD_Steel", *box((0, 0.22, 8.3), (0.08, 0.3, 0.6)))
        m.add("FD_Steel", *cylinder((0, 0.48, 7.8), (0, 0.48, 8.75), 0.24, n=14))
        m.add("FD_Steel", *cylinder((0, 0.48, 8.75), (0, 0.48, 8.85), 0.18, n=14))
        m.add("FD_Wire", *tube([(0, 0.48, 8.85), (0, 0.3, 9.4), (0, -0.30, 9.55)], 0.008, n=5))
    return m


LAMP_LIGHT_M = (0.0, 1.02, 5.13)   # 防犯灯の光の出る所 (電柱の根元から。+Y が道路の側)


def pole_lamp():
    """電柱に付ける LED の防犯灯。原点は電柱の根元 (電柱と同じ置き方)、腕は +Y (道路の側) へ伸びる。"""
    m = Mesh("SM_FD_RoadLamp")
    _, hy, hz = LAMP_LIGHT_M
    m.add("FD_LampBody", *cylinder((0, 0, 4.92), (0, 0, 5.06), 0.15, n=14))   # 電柱に巻く金具
    m.add("FD_LampBody", *tube([(0, 0.12, 4.99), (0, 0.5, 5.1), (0, hy - 0.12, hz + 0.08)], 0.025, n=8))  # 腕
    m.add("FD_LampBody", *box((0, hy, hz + 0.055), (0.2, 0.44, 0.07)))       # 灯具
    m.add("FD_LampGlow", *box((0, hy, hz + 0.015), (0.15, 0.32, 0.012)))     # 下を向いた光る面
    return m


def power_lines(n_points=15):
    """電柱1区間 (WIRE_SPAN_M) の電線。原点は始めの電柱の根元から WIRE_ORIGIN_Z_M の高さ。たるみは放物線。"""
    m = Mesh("SM_FD_RoadWires")
    t = np.linspace(0.0, 1.0, n_points)
    for y, z, sag, r in POLE_WIRES:
        path = np.stack([t * WIRE_SPAN_M, np.full_like(t, y), z - WIRE_ORIGIN_Z_M - 4 * sag * t * (1 - t)], 1)
        m.add("FD_Wire", *tube(path, r, n=5))
    return m


def plate(poly_uv, x0, x1, cz):
    """標識の板。poly_uv は正面から見た (右, 上) の凸多角形 (m)。+X を向き、厚さは x0..x1。"""
    poly = np.asarray(poly_uv, float)
    # 正面 (+X の側) から見ると、右は -Y
    ring_at = lambda x: np.stack([np.full(len(poly), x), -poly[:, 0], poly[:, 1] + cz], 1)
    return sweep([ring_at(x0), ring_at(x1)])


def disc(r, n=32):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.stack([r * np.cos(a), r * np.sin(a)], 1)


def stroke(p0, p1, w):
    """正面から見た太さ w の線分 (四角形)。"""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = (p1 - p0) / np.linalg.norm(p1 - p0)
    n = np.array([-d[1], d[0]]) * w / 2
    return [p0 + n, p1 + n, p1 - n, p0 - n]


SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
            "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg"}


def digits(m, material, text, cx, cy, h, x, cz):
    """7 セグメントの数字 (正面から見た中心 cx, cy、高さ h)。"""
    w, t = h * 0.55, h * 0.14
    step = w + h * 0.22
    for i, ch in enumerate(text):
        ox = cx + (i - (len(text) - 1) / 2) * step
        l, r, top, mid, bot = ox - w / 2 + t / 2, ox + w / 2 - t / 2, cy + h / 2 - t / 2, cy, cy - h / 2 + t / 2
        seg = {"a": ((l - t / 2, top), (r + t / 2, top)), "g": ((l, mid), (r, mid)), "d": ((l - t / 2, bot), (r + t / 2, bot)),
               "f": ((l, top), (l, mid)), "b": ((r, top), (r, mid)), "e": ((l, mid), (l, bot)), "c": ((r, mid), (r, bot))}
        for s in SEGMENTS[ch]:
            m.add(material, *plate(stroke(*seg[s], t), x, x + 0.004, cz))


def sign_post(name, center_z=2.4, top_z=None):
    m = Mesh(name)
    m.add("FD_Steel", *cylinder((-0.05, 0, -0.4), (-0.05, 0, top_z or center_z + 0.25), 0.03, n=10))
    return m


def route_sign(ref):
    """都道府県道の番号の標識 (青い六角形、白い縁と数字)。"""
    cz = 2.5
    m = sign_post(f"SM_FD_RoadSignRoute{ref}", cz)
    hexagon = lambda w, h: [(w / 2, 0), (w / 2 - h * 0.25, h / 2), (-w / 2 + h * 0.25, h / 2), (-w / 2, 0),
                            (-w / 2 + h * 0.25, -h / 2), (w / 2 - h * 0.25, -h / 2)]
    m.add("FD_SignBack", *plate(hexagon(0.82, 0.62), -0.02, -0.01, cz))
    m.add("FD_SignWhite", *plate(hexagon(0.82, 0.62), -0.01, 0.0, cz))
    m.add("FD_SignBlue", *plate(hexagon(0.74, 0.54), 0.0, 0.003, cz))
    m.add("FD_SignWhite", *plate(stroke((-0.12, 0.17), (0.12, 0.17), 0.035), 0.003, 0.007, cz))  # 県名の代わりの帯
    digits(m, "FD_SignWhite", ref, 0.0, -0.04, 0.28, 0.003, cz)
    return m


def speed_sign(limit="40"):
    """最高速度の標識 (赤い輪、白地に青い数字)。"""
    cz = 2.4
    m = sign_post(f"SM_FD_RoadSignSpeed{limit}", cz)
    m.add("FD_SignBack", *plate(disc(0.30), -0.02, -0.01, cz))
    m.add("FD_SignRed", *plate(disc(0.30), -0.01, 0.0, cz))
    m.add("FD_SignWhite", *plate(disc(0.235), 0.0, 0.003, cz))
    digits(m, "FD_SignBlue", limit, 0.0, 0.0, 0.26, 0.003, cz)
    return m


def curve_sign(right):
    """この先カーブの警戒標識 (黄色のひし形、黒い縁と矢印)。right なら右へ曲がる。"""
    cz = 2.4
    m = sign_post("SM_FD_RoadSignCurve" + ("R" if right else "L"), cz)
    diamond = lambda r: [(r, 0), (0, r), (-r, 0), (0, -r)]
    m.add("FD_SignBack", *plate(diamond(0.44), -0.02, -0.01, cz))
    m.add("FD_SignBlack", *plate(diamond(0.44), -0.01, 0.0, cz))
    m.add("FD_SignYellow", *plate(diamond(0.40), 0.0, 0.003, cz))
    k = 1 if right else -1
    w = 0.05
    pts = [(-0.06 * k, -0.20), (-0.06 * k, 0.0), (0.08 * k, 0.12)]
    for a, b in zip(pts, pts[1:]):
        m.add("FD_SignBlack", *plate(stroke(a, b, w), 0.003, 0.007, cz))
    m.add("FD_SignBlack", *plate(disc(w / 2, 10) + pts[1], 0.003, 0.007, cz))  # 折れ目の角を丸く
    d = np.subtract(pts[2], pts[1])
    d = d / np.linalg.norm(d)
    n = np.array([-d[1], d[0]])
    tip = np.add(pts[2], d * 0.07)
    m.add("FD_SignBlack", *plate([tip, pts[2] + n * 0.07, pts[2] - n * 0.07], 0.003, 0.007, cz))
    return m


# ---------------------------------------------------------------- glTF への書き出し
def to_gltf_space(v):
    return v[:, [0, 2, 1]]


def orient_closed(v, f):
    """体積が正 (glTF の右手系で面が外向き) になるよう、必要なら面を裏返す。"""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6
    return f[:, ::-1] if vol < 0 else f


def corner_normals(v, f, angle_deg=SMOOTH_ANGLE_DEG):
    """三角形の角ごとの法線。角度の近い隣の面とだけなめらかにつなぐ。"""
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    area2 = np.linalg.norm(fn, axis=1, keepdims=True)
    unit = fn / np.maximum(area2, 1e-12)
    cos_t = math.cos(math.radians(angle_deg))
    # 頂点 -> 面の一覧
    by_vertex = [[] for _ in range(len(v))]
    for fi, tri in enumerate(f):
        for vi in tri:
            by_vertex[vi].append(fi)
    out = np.zeros((len(f), 3, 3))
    for fi, tri in enumerate(f):
        for k, vi in enumerate(tri):
            adj = by_vertex[vi]
            near = [g for g in adj if unit[g] @ unit[fi] >= cos_t]
            s = fn[near].sum(0)
            out[fi, k] = s / max(np.linalg.norm(s), 1e-12)
    return out


def write_gltf(mesh, path):
    """1つのノード・1つのメッシュ (マテリアルごとにプリミティブ) の .gltf を書く。"""
    by_mat = {}
    for mat, v, f in mesh.parts:
        by_mat.setdefault(mat, []).append((v, f))
    blob_bytes = bytearray()
    accessors, views, prims, materials = [], [], [], []

    def add_view(data, target):
        while len(blob_bytes) % 4:
            blob_bytes.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob_bytes), "byteLength": len(data), "target": target})
        blob_bytes.extend(data)
        return len(views) - 1

    images, textures, tex_index = [], [], {}

    def add_prim(mat, pos, nrm, uv, col, idx, uv1=None):
        acc = {}
        attrs = [("POSITION", pos, "VEC3"), ("NORMAL", nrm, "VEC3"), ("TEXCOORD_0", uv, "VEC2")]
        if uv1 is not None:
            attrs.append(("TEXCOORD_1", uv1, "VEC2"))
        if col is not None:
            attrs.append(("COLOR_0", col, "VEC4"))
        for key, arr, typ in attrs:
            view = add_view(arr.tobytes(), 34962)
            a = {"bufferView": view, "componentType": 5126, "count": len(arr), "type": typ}
            if key == "POSITION":
                a["min"], a["max"] = pos.min(0).tolist(), pos.max(0).tolist()
            accessors.append(a)
            acc[key] = len(accessors) - 1
        view = add_view(idx.tobytes(), 34963)
        accessors.append({"bufferView": view, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
        spec = MATERIALS[mat]
        m = {"name": mat, "pbrMetallicRoughness": {
            "baseColorFactor": [*spec["color"], 1.0], "metallicFactor": spec.get("metallic", 0.0),
            "roughnessFactor": spec["roughness"]}}
        for key, slot in (("texture", "baseColorTexture"), ("normal", "normalTexture")):  # 同じフォルダの PNG
            if key in spec:
                uri = spec[key]
                if uri not in tex_index:
                    images.append({"uri": uri})
                    textures.append({"source": len(images) - 1})
                    tex_index[uri] = len(textures) - 1
                if slot == "normalTexture":
                    m[slot] = {"index": tex_index[uri]}
                else:
                    m["pbrMetallicRoughness"][slot] = {"index": tex_index[uri]}
        if spec.get("alpha"):  # 葉の絵の透明な所を切り抜く
            m.update(alphaMode="MASK", alphaCutoff=0.4, doubleSided=True)
        materials.append(m)
        prims.append({"attributes": acc, "indices": len(accessors) - 1, "material": len(materials) - 1})

    # マテリアルごとに 1 つのプリミティブにまとめる (分けると UE でセクションが増え、64 を超えると Nanite にできない)
    groups = {}  # マテリアル -> [(pos, nrm, uv, col または None, idx, uv1 または None)]
    for mat, pieces in by_mat.items():
        pos, nrm = [], []
        for v, f in pieces:
            g = to_gltf_space(v)
            f = orient_closed(g, f)
            pos.append(g[f].reshape(-1, 3))
            if mesh.flat:
                fn = np.cross(g[f[:, 1]] - g[f[:, 0]], g[f[:, 2]] - g[f[:, 0]])
                fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
                nrm.append(np.repeat(fn, 3, axis=0))
            else:
                nrm.append(corner_normals(g, f).reshape(-1, 3))
        pos = np.concatenate(pos)
        uv = np.stack([pos[:, 0] + pos[:, 2], pos[:, 1]], 1) * 0.5
        groups.setdefault(mat, []).append((pos, np.concatenate(nrm), uv, None, np.arange(len(pos)), None))
    for mat, v, f, n, uv, shade, orient, uv1 in mesh.cards:
        g, gn = to_gltf_space(v), to_gltf_space(n)
        if orient:
            fn = np.cross(g[f[:, 1]] - g[f[:, 0]], g[f[:, 2]] - g[f[:, 0]])
            flip = np.einsum("ij,ij->i", fn, gn[f].sum(1)) < 0
            f = np.where(flip[:, None], f[:, ::-1], f)
        rgb = shade if shade.ndim == 2 else np.repeat(shade[:, None], 3, 1)  # (N,3) なら RGB を別々に書く
        col = np.c_[rgb, np.ones(len(shade))]
        groups.setdefault(mat, []).append((g, gn, uv, col, f.reshape(-1), uv1))
    for mat, items in groups.items():
        has_col = any(it[3] is not None for it in items)
        has_uv1 = any(it[5] is not None for it in items)
        pos, nrm, uvs, cols, idx, uv1s, base = [], [], [], [], [], [], 0
        for p_, n_, uv_, col_, idx_, uv1_ in items:
            pos.append(p_)
            nrm.append(n_)
            uvs.append(uv_)
            if has_col:
                cols.append(col_ if col_ is not None else np.ones((len(p_), 4)))
            if has_uv1:
                uv1s.append(uv1_ if uv1_ is not None else np.zeros((len(p_), 2)))
            idx.append(idx_ + base)
            base += len(p_)
        add_prim(mat, np.concatenate(pos).astype(np.float32), np.concatenate(nrm).astype(np.float32),
                 np.concatenate(uvs).astype(np.float32), np.concatenate(cols).astype(np.float32) if has_col else None,
                 np.concatenate(idx).astype(np.uint32), np.concatenate(uv1s).astype(np.float32) if has_uv1 else None)

    doc = {
        "asset": {"version": "2.0", "generator": "fukuoka_drive tools/terrain/scenery_meshes.py"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mesh.name, "mesh": 0}],
        "meshes": [{"name": mesh.name, "primitives": prims}],
        "materials": materials,
        **({"images": images, "textures": textures} if images else {}),
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(blob_bytes),
                     "uri": "data:application/octet-stream;base64," + base64.b64encode(bytes(blob_bytes)).decode()}],
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(doc, fp)
    return sum(len(f) for _, _, f in mesh.parts) + sum(len(c[2]) for c in mesh.cards)
