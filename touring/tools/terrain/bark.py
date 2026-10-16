"""木の幹と枝の樹皮。樹皮の絵 (色) と凹凸 (ノーマルマップ) を描き、幹と枝の筒に巻き付ける UV を付ける。

絵は上下左右につながる (タイルできる) ので、筒の周りに何回か、幹の長さに沿って何回も繰り返して貼る。
横 (U) が幹の周り、縦 (V) が幹の長さの向き。
"""

import math
import random

import numpy as np
from PIL import Image

import scenery_meshes as sm

WIDTH, HEIGHT = 512, 1024   # 絵の大きさ (横が周り、縦が長さ)

# 樹皮の種類。tile = 絵 1 枚が覆う大きさ (周り m, 長さ m)。マテリアル名は scenery_meshes.MATERIALS と同じ
BARK_KINDS = {
    "FD_PineBark": dict(style="plates", tile=(0.7, 1.4), seed=1,   # クロマツ: 亀の甲のように割れた黒っぽい厚い樹皮
                        top=(78, 72, 68), crack=(26, 20, 18), tint=(104, 74, 58)),
    "FD_Bark": dict(style="fissured", tile=(0.6, 1.2), seed=2,     # シイ・タブ・クス: 灰褐色で浅い縦の割れ目
                    top=(104, 98, 88), crack=(46, 40, 34), tint=(86, 80, 66)),
    "FD_BarkCedar": dict(style="fibrous", tile=(0.5, 1.6), seed=3,  # スギ: 赤茶色で縦に細長く裂ける
                         top=(132, 88, 62), crack=(58, 34, 24), tint=(150, 110, 84)),
    "FD_PalmTrunk": dict(style="diamond", tile=(0.9, 0.9), seed=4,  # カナリーヤシ: 葉の付け根の跡がうろこ状に並ぶ
                         top=(128, 108, 82), crack=(60, 48, 36), tint=(104, 90, 64)),
    "FD_BambooCulm": dict(style="culm", tile=(0.3, 1.2), seed=5,    # モウソウチク: 緑でなめらか、細い縦すじ
                          top=(108, 126, 66), crack=(78, 96, 48), tint=(130, 136, 92)),
}


# ---------------------------------------------------------------- タイルできるノイズ
def value_noise(cells_x, cells_y, rng, w=WIDTH, h=HEIGHT):
    """上下左右がつながる、なめらかなノイズ (0..1)。cells_x x cells_y の格子の乱数をなめらかにつなぐ。"""
    grid = np.array([[rng.random() for _ in range(cells_x)] for _ in range(cells_y)])
    x = np.arange(w) / w * cells_x
    y = np.arange(h) / h * cells_y
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    x1, y1 = (x0 + 1) % cells_x, (y0 + 1) % cells_y
    a = grid[y0][:, x0]
    b = grid[y0][:, x1]
    c = grid[y1][:, x0]
    d = grid[y1][:, x1]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(cells_x, cells_y, rng, octaves=4):
    out, amp, total = 0, 1.0, 0
    for o in range(octaves):
        out = out + value_noise(cells_x * 2 ** o, cells_y * 2 ** o, rng) * amp
        total += amp
        amp *= 0.5
    return out / total


def voronoi_edges(cells_x, cells_y, rng, jitter=0.9, warp=None, stretch=1.0, w=WIDTH, h=HEIGHT):
    """タイルできるボロノイ (F2 - F1)。割れ目 (境目) で 0、板の真ん中ほど大きい。
    warp = (横, 縦) のずらし量 (絵の幅に対する割合) で境目をゆがめ、stretch > 1 なら板を縦長にする。"""
    pts = [((i + 0.5 + (rng.random() - 0.5) * jitter) / cells_x, (j + 0.5 + (rng.random() - 0.5) * jitter) / cells_y)
           for j in range(cells_y) for i in range(cells_x)]
    xs = (np.arange(w) + 0.5) / w
    ys = (np.arange(h) + 0.5) / h
    X, Y = np.meshgrid(xs, ys)
    if warp is not None:
        X, Y = np.mod(X + warp[0], 1.0), np.mod(Y + warp[1], 1.0)
    f1 = np.full(X.shape, 9.0)
    f2 = np.full(X.shape, 9.0)
    for px, py in pts:
        dx = np.abs(X - px)
        dx = np.minimum(dx, 1 - dx) * cells_x
        dy = np.abs(Y - py)
        dy = np.minimum(dy, 1 - dy) * cells_y
        d = np.sqrt(dx * dx + (dy / stretch) ** 2)  # 格子 1 つ分を 1 とした距離
        f2 = np.where(d < f1, f1, np.minimum(f2, d))
        f1 = np.minimum(f1, d)
    return f2 - f1


# ---------------------------------------------------------------- 樹皮の高さ (凹凸) の模様
def bark_height(style, rng):
    """0..1 の高さ (1 = 樹皮の表面、0 = 割れ目の底)。"""
    if style == "plates":
        # 縦長でいびつな厚い板が、太さの揃わない深い溝で区切られる。板の表面もうろこ状にはがれてざらつく
        warp = ((fbm(4, 8, rng) - 0.5) * 0.12, (fbm(4, 8, rng) - 0.5) * 0.12)
        e = voronoi_edges(5, 5, rng, warp=warp, stretch=1.8)
        width = 0.18 + 0.25 * fbm(6, 12, rng)       # 溝の太さのむら
        plates = np.clip(e / width, 0, 1) ** 0.5
        flakes = voronoi_edges(14, 22, rng, warp=warp)   # 板の上の細かいはがれ
        surface = 0.7 + 0.2 * np.clip(flakes / 0.3, 0, 1) + 0.1 * fbm(32, 64, rng)
        return np.clip(plates * surface, 0, 1)
    if style == "fissured":
        # 浅い縦の割れ目がところどころ途切れながら続き、表面には細かいざらつきと皮目 (小さな点) がある
        ridges = 1 - np.abs(fbm(10, 3, rng) * 2 - 1)
        cracks = np.clip((ridges - 0.55) / 0.3, 0, 1) * np.clip(fbm(4, 8, rng) * 1.6, 0, 1)
        grain = fbm(48, 96, rng, octaves=2)
        dots = np.clip((value_noise(60, 120, rng) - 0.82) / 0.1, 0, 1)
        return np.clip(1 - 0.7 * cracks + 0.25 * (grain - 0.5) - 0.25 * dots, 0, 1)
    if style == "fibrous":
        # 細い縦のすじが重なる
        strips = fbm(28, 2, rng, octaves=3)
        fine = fbm(64, 4, rng, octaves=2)
        return np.clip(0.2 + 0.9 * (strips * 0.7 + fine * 0.3) ** 1.5, 0, 1)
    if style == "diamond":
        # 斜めの格子 (葉の付け根の跡) が上下に重なって並ぶ
        xs = np.arange(WIDTH) / WIDTH * 6
        ys = np.arange(HEIGHT) / HEIGHT * 6
        X, Y = np.meshgrid(xs, ys)
        X = X + (fbm(4, 4, rng) - 0.5) * 0.4  # 並びを少しゆがめる
        Y = Y + (fbm(4, 4, rng) - 0.5) * 0.4
        a, b = np.mod(X + Y, 1.0), np.mod(X - Y, 1.0)
        diamond = np.minimum(np.minimum(a, 1 - a), np.minimum(b, 1 - b)) * 2
        scale = np.clip(diamond / 0.5, 0, 1) ** 0.5
        return np.clip(scale * (0.75 + 0.25 * fbm(6, 6, rng)) + 0.2 * (fbm(32, 32, rng) - 0.5), 0, 1)
    if style == "culm":
        return 0.85 + 0.15 * fbm(40, 2, rng, octaves=2)
    raise ValueError(style)


def normal_map(height, strength):
    """高さから接空間のノーマルマップ (RGB) を作る。つながりを保つよう端は反対側を参照する。"""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5
    n = np.stack([-dx * strength, dy * strength, np.ones_like(height)], 2)  # 絵の下向き = V の増える向き (UE は緑 = 上)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def bark_textures(kind, color_path, normal_path):
    spec = BARK_KINDS[kind]
    rng = random.Random(f"{kind}{spec['seed']}")
    h = bark_height(spec["style"], rng)
    top, crack, tint = (np.array(spec[k], float) for k in ("top", "crack", "tint"))
    # 盛り上がった所は表面の色、割れ目は暗い色。大きなむらで別の色合いを混ぜる
    mix = fbm(3, 6, rng)[:, :, None]
    surface = top * (1 - 0.35 * mix) + tint * 0.35 * mix
    col = crack + (surface - crack) * h[:, :, None] ** 0.8
    col *= (0.85 + 0.3 * fbm(16, 32, rng))[:, :, None]
    Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(color_path)
    strength = {"plates": 14.0, "fissured": 9.0, "fibrous": 7.0, "diamond": 12.0, "culm": 2.0}[spec["style"]]
    Image.fromarray(normal_map(h, strength)).save(normal_path)


def texture_names(kind):
    base = kind.replace("FD_", "T_FD_")
    return f"{base}_D.png", f"{base}_N.png"


# ---------------------------------------------------------------- 樹皮を巻いた筒
def bark_tube(mesh, kind, path, radii, n=8):
    """path (K,3) に沿った筒に、樹皮の絵を巻き付ける UV と外向きの法線を付けて mesh に足す (端のふたは付けない)。"""
    tile_w, tile_h = BARK_KINDS[kind]["tile"]
    path = np.asarray(path, float)
    radii = np.broadcast_to(np.asarray(radii, float), (len(path),))
    repeats = max(1, round(2 * math.pi * radii.max() / tile_w))
    a = np.linspace(0, 2 * math.pi, n + 1)  # 継ぎ目の列は 2 回 (U = 0 と 1) 置く
    verts, normals, uvs = [], [], []
    u, length = None, 0.0
    v_offset = (hash(round(float(path[0][2]), 3)) % 97) / 97.0  # 筒ごとに模様の縦位置をずらす
    for i, p in enumerate(path):
        t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        if u is None:
            u = np.cross(t, [0, 0, 1] if abs(t[2]) < 0.9 else [1, 0, 0])
        u = u - t * (u @ t)
        u /= np.linalg.norm(u)
        w = np.cross(t, u)
        if i:
            length += np.linalg.norm(p - path[i - 1])
        out = np.cos(a)[:, None] * u + np.sin(a)[:, None] * w
        verts.extend(p + radii[i] * out)
        normals.extend(out)
        uvs.extend(np.c_[a / (2 * math.pi) * repeats, np.full(n + 1, v_offset + length / tile_h)])
    k = len(path)
    tris = []
    for i in range(k - 1):
        for j in range(n):
            q0, q1 = i * (n + 1) + j, i * (n + 1) + j + 1
            r0, r1 = q0 + n + 1, q1 + n + 1
            tris += [(q0, r1, q1), (q0, r0, r1)]
    v = np.array(verts)
    # 面の表裏は書き出すときに法線の向きへそろえる (orient=True)
    mesh.add_cards(kind, v, np.array(tris), np.array(normals), np.array(uvs), np.ones(len(v)), orient=True)
    return mesh
