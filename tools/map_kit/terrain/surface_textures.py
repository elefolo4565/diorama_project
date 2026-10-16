"""神社と名所の石・白木・銅板・白壁などの模様と凹凸の絵。build_scenery.py から呼ぶ。

建物の絵 (building_textures.py) と同じく、上下左右につながる 512 x 512 の絵で、色の絵は明るさだけ (灰色)。
UE のマテリアル (setup_project.py の setup_surfaces) が、マテリアルの色 (scenery_meshes.MATERIALS の color) に掛け、
ワールド座標から貼る (横 = 面に沿った水平の向き、縦 = 面に沿った上の向き。上を向いた面は東西と南北)。
どのマテリアルにどの絵を貼るかは、scenery_meshes.MATERIALS (と名所・植物の MATERIALS) の "surface" に書く。

- StoneGranite  石の鳥居・灯籠・石段・基礎・碑: 花崗岩の細かい斑点と小さなくぼみ、薄い色むら (1.0m 四方)
- StoneRough    自然石・石積み: 大きな凹凸と割れ目のある石の面 (1.6m 四方)
- WoodGrain     白木の柱・壁・縁: 縦の木目と節、板の継ぎ目 (幅 0.24m の板、1.2m 四方)
- CopperSheet   緑青の銅板葺き: 縦のはぜ (0.36m おき) と横の継ぎ目 (0.9m おき)、緑青のむら (1.8m 四方)
- Plaster       白壁・漆喰 (building_textures の plaster)
- Concrete      展望台などのコンクリート (building_textures の concrete)
- Kawara        瓦屋根 (building_textures の kawara)
"""

import random

import numpy as np
from PIL import Image

import building_textures as bt
from bark import value_noise, voronoi_edges

SIZE = bt.SIZE

# 名前: 絵 1 枚が覆う大きさ (m)。UE のマテリアルもこの大きさで貼る
TEXTURES = {
    "StoneGranite": 1.0,
    "StoneRough": 1.6,
    "WoodGrain": 1.2,
    "CopperSheet": 1.8,
    "Plaster": 2.0,
    "Concrete": 2.0,
    "Kawara": 1.2,
}


def names(kind):
    return f"T_FD_Surf{kind}_D.png", f"T_FD_Surf{kind}_N.png"


def granite(rng):
    fine = bt._fbm(80, rng, 3)
    speck = value_noise(160, 160, rng, SIZE, SIZE)
    dark = np.clip((speck - 0.72) / 0.12, 0, 1)            # 黒雲母の黒い粒
    light = np.clip((0.22 - speck) / 0.12, 0, 1)           # 長石の白い粒
    pits = np.clip((value_noise(110, 110, rng, SIZE, SIZE) - 0.88) / 0.08, 0, 1)
    blotch = bt._fbm(4, rng, 4)
    h = 0.35 * fine - 0.5 * pits + 0.1 * blotch
    col = (0.88 + 0.12 * blotch) * (1 - 0.45 * dark) * (1 + 0.12 * light) * (1 - 0.15 * pits) * (0.95 + 0.05 * fine)
    return col, h, 4.0


def rough_stone(rng):
    cracks = np.clip(voronoi_edges(5, 5, rng, w=SIZE, h=SIZE) / 0.08, 0, 1)
    big = bt._fbm(6, rng, 5)
    fine = bt._fbm(60, rng, 3)
    lichen = np.clip((bt._fbm(9, rng, 4) - 0.62) / 0.2, 0, 1)
    h = 0.7 * big + 0.2 * fine + 0.5 * cracks
    col = (0.75 + 0.25 * big) * (0.55 + 0.45 * cracks) * (0.93 + 0.07 * fine) * (1 + 0.15 * lichen)
    return col, h, 6.0


def wood(rng):
    X, Y = bt.grid()
    planks = 5                                              # 1.2m に幅 0.24m の板
    xp = X * planks
    idx = np.floor(xp).astype(int)
    fx = xp - idx
    offs = np.array([rng.random() * 10 for _ in range(planks)])
    # 縦の木目: 板ごとにずらした、ゆらぐ縦縞
    warp = bt._fbm(3, rng, 4) * 2.2 + value_noise(2, 8, rng, SIZE, SIZE) * 0.8
    rings = np.sin(2 * np.pi * (fx * (4 + 2 * (idx % 3)) + offs[idx] + warp))
    rings = np.sign(rings) * np.abs(rings) ** 0.5 * (0.7 + 0.3 * bt._fbm(40, rng, 2))   # 年輪の縁を細く
    grain = 0.5 + 0.5 * rings
    # 節: 板ごとに 0〜1 個の暗い楕円
    knot = np.zeros_like(X)
    for i in range(planks):
        if rng.random() < 0.6:
            kx, ky = (i + 0.3 + 0.4 * rng.random()) / planks, rng.random()
            d = np.hypot((X - kx) * planks * 4.0, np.minimum(np.abs(Y - ky), 1 - np.abs(Y - ky)) * 10.0)
            knot = np.maximum(knot, np.clip(1 - d, 0, 1))
    joint = np.clip(np.minimum(fx, 1 - fx) / 0.012, 0, 1)    # 板の継ぎ目の溝
    tint = np.array([0.9 + 0.2 * rng.random() for _ in range(planks)])
    h = joint * (0.8 + 0.12 * grain - 0.3 * knot)
    col = tint[idx] * (0.78 + 0.22 * grain) * (1 - 0.45 * knot) * (0.5 + 0.5 * joint) * (0.94 + 0.06 * bt._fbm(8, rng, 3))
    return col, h, 4.0


def copper(rng):
    X, Y = bt.grid()
    cols, rows = 5, 2                                       # 1.8m に 0.36m のはぜ、0.9m の段
    fx = np.mod(X * cols, 1.0)
    yr = Y * rows
    row = np.floor(yr).astype(int)
    fy = yr - row
    seam = np.clip(1 - np.abs(fx - 0.5) / 0.03, 0, 1)      # 縦のはぜ (立ち上がり)
    lap = np.clip((fy - 0.94) / 0.06, 0, 1)                # 横の継ぎ目の重なり
    patina = bt._fbm(5, rng, 5)
    streak = np.clip((value_noise(16, 2, rng, SIZE, SIZE) - 0.5) / 0.5, 0, 1)
    h = 0.25 + 0.65 * seam + 0.25 * lap + 0.03 * bt._fbm(30, rng, 2)
    col = (0.72 + 0.28 * patina) * (1 + 0.15 * streak) * (0.9 + 0.1 * seam) * (1 - 0.25 * lap)
    return col, h, 5.0


MAKERS = {"StoneGranite": granite, "StoneRough": rough_stone, "WoodGrain": wood, "CopperSheet": copper,
          "Plaster": bt.plaster, "Concrete": bt.concrete, "Kawara": bt.kawara}


def write(folder, kinds):
    """kinds の絵を folder に書き、{名前: [色の絵, 凹凸の絵, 大きさ m]} を返す。"""
    out = {}
    for kind in sorted(kinds):
        rng = random.Random(f"surface-{kind}")
        col, h, strength = MAKERS[kind](rng)
        d, n = names(kind)
        g = np.clip(col / max(col.max(), 1e-6), 0, 1)
        Image.fromarray((g * 255).astype(np.uint8)).convert("RGB").save(f"{folder}/{d}")
        Image.fromarray(bt.normal_map(h, strength)).save(f"{folder}/{n}")
        out[kind] = [d, n, TEXTURES[kind]]
    return out


def materials_used(meshes, materials):
    """形に使われていて "surface" の書いてあるマテリアル {名前: dict(kind, color, roughness, metallic)}。"""
    used = {mat for m in meshes for mat, *_ in m.parts}
    out = {}
    for mat in sorted(used):
        spec = materials.get(mat, {})
        if spec.get("surface") in MAKERS:
            out[mat] = dict(kind=spec["surface"], color=list(spec["color"]), roughness=spec["roughness"],
                            metallic=spec.get("metallic", 0.0))
    return out


if __name__ == "__main__":
    import os
    import sys
    os.makedirs(sys.argv[1], exist_ok=True)
    print(write(sys.argv[1], MAKERS))
