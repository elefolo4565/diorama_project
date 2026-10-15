"""建物の壁と屋根の絵 (色のむらと凹凸)。build_scenery.py から呼ぶ。

どれも上下左右につながる (タイルできる) 512 x 512 の絵。色の絵は明るさだけ (灰色) で、
UE のマテリアル (M_FD_BuildingWall / M_FD_BuildingRoof) が頂点の色 (壁や屋根の色) に掛ける。
UE ではワールド座標から貼る (壁は横 = 壁に沿った向き、縦 = 高さ。屋根は横 = 軒に沿った向き、縦 = 流れの上向き)。
凹凸の絵は R = 絵の右向き、G = 絵の上向き (壁の上・屋根の棟の向き) の傾き。

- WallSiding  窯業系サイディング。幅 455mm の横張りの板の継ぎ目の溝と、板ごとの浅い石目・木目の模様 (1.82m 四方)
- WallPlaster モルタルのかき落とし・吹き付け。細かいざらつきと、ゆるい雨だれのしみ (2m 四方)
- RoofKawara  和瓦 (いぶし瓦・釉薬瓦)。波打つ瓦の列 (幅 0.3m) と、段の重なりの影 (1.2m 四方)
- RoofMetal   金属の屋根 (瓦棒・折板)。0.45m おきの立ち上がりと薄いさびのむら (1.8m 四方)
- Concrete    平らな屋根と基礎のコンクリート (2m 四方)
"""

import random

import numpy as np
from PIL import Image

from bark import value_noise, voronoi_edges

SIZE = 512

# 名前: 絵 1 枚が覆う大きさ (m)。UE のマテリアルもこの大きさで貼る
TEXTURES = {
    "WallSiding": 1.82,
    "WallPlaster": 2.0,
    "RoofKawara": 1.2,
    "RoofMetal": 1.8,
    "Concrete": 2.0,
}


def names(kind):
    return f"T_FD_{kind}_D.png", f"T_FD_{kind}_N.png"


def _fbm(cells, rng, octaves=4):
    out, amp, total = 0, 1.0, 0
    for o in range(octaves):
        out = out + value_noise(cells * 2 ** o, cells * 2 ** o, rng, SIZE, SIZE) * amp
        total += amp
        amp *= 0.5
    return out / total


def normal_map(height, strength):
    """R = 絵の右へ、G = 絵の上へ傾いた面の向き。端は反対側につながる。"""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5
    n = np.stack([-dx * strength, dy * strength, np.ones_like(height)], 2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def grid():
    t = (np.arange(SIZE) + 0.5) / SIZE
    return np.meshgrid(t, t)  # X: 右へ 0..1、Y: 下へ 0..1


def siding(rng):
    X, Y = grid()
    boards = 4                       # 1.82m に 455mm の板が 4 枚
    yb = Y * boards
    row = np.floor(yb).astype(int)
    fy = yb - row
    # 板の継ぎ目 (横の溝)。上の板の下端が少し出る、さねの段
    groove = np.clip(fy / 0.04, 0, 1) * np.clip((1 - fy) / 0.02, 0, 1)
    lap = 0.12 * (1 - fy)            # 板の下ほど手前に出る
    # 縦の継ぎ目: 板ごとにずらした位置に 1 本 (910mm の継ぎを 1.82m に 2 本)
    offs = np.array([rng.random() for _ in range(boards)])
    fx = np.mod(X * 2 + offs[row], 1.0)
    joint = np.clip(np.minimum(fx, 1 - fx) / 0.006, 0, 1)
    # 板の表面の浅い模様 (石目の目地を細かく)
    stone = np.clip(voronoi_edges(10, 20, rng, w=SIZE, h=SIZE) / 0.12, 0, 1)
    grain = _fbm(24, rng, 3)
    h = groove * joint * (0.75 + lap + 0.12 * stone + 0.08 * grain)
    tint = np.array([0.92 + 0.08 * rng.random() for _ in range(boards * 2)])
    shade = tint[(row * 2 + (fx > 0.5)) % len(tint)]
    col = shade * (0.82 + 0.18 * h) * (0.94 + 0.06 * _fbm(6, rng, 3))
    return col, h, 5.0


def plaster(rng):
    X, Y = grid()
    fine = _fbm(64, rng, 3)
    bumps = np.clip((value_noise(90, 90, rng, SIZE, SIZE) - 0.55) / 0.3, 0, 1)
    h = 0.5 * fine + 0.5 * bumps
    # 雨だれ: 縦にのびた薄いしみ
    streak = value_noise(14, 2, rng, SIZE, SIZE)
    streak = np.clip((streak - 0.6) / 0.4, 0, 1) * (0.6 + 0.4 * _fbm(4, rng, 2))
    col = (0.9 + 0.1 * fine) * (1 - 0.12 * streak) * (0.95 + 0.05 * _fbm(5, rng, 3))
    return col, h, 3.0


def kawara(rng):
    X, Y = grid()
    cols, rows = 4, 4                # 1.2m に 0.3m の列と段
    xc = X * cols
    fx = xc - np.floor(xc)
    yr = Y * rows
    row = np.floor(yr).astype(int)
    fy = yr - row                    # 段の中で上 (0) から下 (1) へ
    # 桟瓦の波: 山と谷が交互 (片側がふくらんだ形)
    wave = 0.5 + 0.5 * np.sin(2 * np.pi * (fx - 0.15)) * (0.75 + 0.25 * np.sin(2 * np.pi * fx))
    # 段の重なり: 段の下端 (次の段の上にかぶさる所) ほど高く、すぐ下は低い
    over = 0.35 * fy + 0.25 * np.clip((fy - 0.9) / 0.1, 0, 1)
    h = 0.6 * wave + over
    edge = np.clip((1 - fy) / 0.04, 0, 1)
    tile_id = (np.floor(xc).astype(int) + 7 * row) % 97
    tint = np.array([0.9 + 0.2 * rng.random() for _ in range(97)])
    col = tint[tile_id] * (0.72 + 0.28 * wave) * (0.55 + 0.45 * edge) * (0.94 + 0.06 * _fbm(12, rng, 3))
    return col, h, 10.0


def metal(rng):
    X, Y = grid()
    ribs = 4                         # 1.8m に 0.45m おき
    fx = np.mod(X * ribs, 1.0)
    rib = np.clip(1 - np.abs(fx - 0.5) / 0.025, 0, 1)   # 立ち上がり
    h = 0.3 + 0.7 * rib + 0.03 * _fbm(20, rng, 2)
    rust = np.clip((_fbm(5, rng, 4) - 0.6) / 0.3, 0, 1) * (0.5 + 0.5 * value_noise(12, 3, rng, SIZE, SIZE))
    col = (0.9 + 0.1 * rib) * (1 - 0.15 * rust) * (0.96 + 0.04 * value_noise(40, 1, rng, SIZE, SIZE))
    return col, h, 6.0


def concrete(rng):
    fine = _fbm(48, rng, 3)
    pores = np.clip((value_noise(120, 120, rng, SIZE, SIZE) - 0.85) / 0.1, 0, 1)
    h = 0.6 * fine - 0.3 * pores
    col = (0.85 + 0.15 * _fbm(6, rng, 4)) * (1 - 0.15 * pores) * (0.95 + 0.05 * fine)
    return col, h, 2.0


MAKERS = {"WallSiding": siding, "WallPlaster": plaster, "RoofKawara": kawara, "RoofMetal": metal, "Concrete": concrete}


def write_all(folder):
    """絵を folder に書き、{名前: [色の絵, 凹凸の絵, 大きさ m]} を返す。"""
    out = {}
    for kind, make in MAKERS.items():
        rng = random.Random(f"building-{kind}")
        col, h, strength = make(rng)
        d, n = names(kind)
        g = np.clip(col / max(col.max(), 1e-6), 0, 1)
        Image.fromarray((g * 255).astype(np.uint8)).convert("RGB").save(f"{folder}/{d}")
        Image.fromarray(normal_map(h, strength)).save(f"{folder}/{n}")
        out[kind] = [d, n, TEXTURES[kind]]
    return out


if __name__ == "__main__":
    import os
    import sys
    os.makedirs(sys.argv[1], exist_ok=True)
    print(write_all(sys.argv[1]))
