"""草地の草と、地面 (草地・土・道路) の細かい模様。

ランドスケープの草地は、遠くから見ると色のむらだけの平らな面で、近くでは「のっぺり」して見える。
そこで UE のランドスケープグラス (カメラの近くだけ、地面の草地の所に自動で草を生やす仕組み) に使う草の株と、
地面に細かい凹凸と色のむらを付けるタイルできる絵を作る。UE への取り込みと設定は tools/ue/setup_project.py が行う。

使い方:
    python build_grass.py areas/futamigaura.json

出力 (out/<エリア名>/grass/):
    SM_FD_GrassTuft.gltf  短い草の株 (芝や野草の短い所。草地一面に密に生やす)
    SM_FD_GrassTall.gltf  背の高い草の株 (ところどころ伸びた草。まばらに生やす)
    T_FD_Ground_D.png     地面の色のむら (リニア、0.5 で 1 倍。草地の色に掛ける)
    T_FD_Ground_N.png     地面の凹凸 (ノーマルマップ。草の根元の小さな盛り上がり)
    T_FD_Soil_D/N.png     急な斜面の土 (真砂土と小石、雨の筋) の色のむらと凹凸
    T_FD_Asphalt_D/N.png  道路のアスファルト (砕石の粒とひび割れ) の色のむらと凹凸
    grass.json            上のファイルの一覧

草の葉は板 (絵を貼って切り抜く) ではなく、細い三角形の帯そのもの (不透明) にする。
切り抜き (Masked) は数万株を描くと重いので、形だけで葉にした方が軽い。
葉は表と裏の 2 枚を重ねて同じ法線にし、法線はほぼ上向き (地面と同じ光り方) にして、草地全体がなじむようにする。
頂点の色: R = 根元からの高さ (0..1、根元の陰と風でゆれる量)、G = 葉ごとの乱数 (枯れた葉の色)、B = 葉ごとの乱数 (風のゆれの時間のずれ)。
"""

import json
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw

import scenery_meshes as sm
from bark import normal_map, value_noise
from geo import Area

MATERIAL = "FD_Grass"

# 草の株。blades = 葉の数、segments = 葉 1 枚の区切り (多いほどなめらかに曲がる)、
# height / width = 葉の高さと根元の幅 (m)、radius = 株の広がり (m)、tilt = 根元の傾き (度)、bend = 先へ向かって倒れる量 (度)
TUFTS = {
    "SM_FD_GrassTuft": dict(seed=1, blades=26, segments=2, height=(0.14, 0.36), width=(0.016, 0.028),
                            radius=0.22, tilt=(5, 30), bend=(10, 45)),
    "SM_FD_GrassTall": dict(seed=2, blades=14, segments=4, height=(0.40, 0.85), width=(0.012, 0.020),
                            radius=0.14, tilt=(3, 18), bend=(20, 70)),
}

GROUND_SIZE = 1024   # 地面の絵の大きさ (px)。UE では 1 枚を約 2.5m 四方に貼る


# ---------------------------------------------------------------- 草の株
def blade(rng, base, height, width, tilt_deg, bend_deg, segments):
    """根元 base から伸びる 1 枚の葉。(頂点, 帯の三角形, 法線, UV, 高さ 0..1) を返す。"""
    az = rng.uniform(0, 2 * math.pi)                      # 倒れる向き
    lean = np.array([math.cos(az), math.sin(az), 0.0])
    # 葉の幅の向き: 倒れる向きとおおよそ直角に、少しねじる
    twist = az + math.pi / 2 + rng.uniform(-0.5, 0.5)
    side = np.array([math.cos(twist), math.sin(twist), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    p = np.asarray(base, float)
    step = height / segments
    pts, ts = [p.copy()], [0.0]
    for i in range(segments):
        # 根元は tilt、先へ行くほど bend まで倒れる (2 乗で先の方ほど急に曲がる)
        a = math.radians(tilt_deg + bend_deg * ((i + 0.5) / segments) ** 2)
        d = up * math.cos(a) + lean * math.sin(a)
        p = p + d * step
        pts.append(p.copy())
        ts.append((i + 1) / segments)
    verts, normals, uvs, hs = [], [], [], []
    for i, (q, t) in enumerate(zip(pts, ts)):
        # 法線はほぼ上向き。先の方は倒れた向きへ少し傾ける (光の当たり方に柔らかい変化が出る)
        n = up * (0.85 - 0.25 * t) + lean * (0.15 + 0.35 * t)
        n /= np.linalg.norm(n)
        if i == len(pts) - 1:   # 先はとがらせて 1 点
            verts.append(q)
            normals.append(n)
            uvs.append((0.5, 0.0))
            hs.append(t)
            break
        w = width * 0.5 * (1 - t) ** 0.7
        for s, u in ((-1, 0.0), (1, 1.0)):
            verts.append(q + side * w * s)
            normals.append(n)
            uvs.append((u, 1 - t))
            hs.append(t)
    tris = []
    for i in range(segments - 1):
        a, b, c, d = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        tris += [(a, b, d), (a, d, c)]
    k = 2 * (segments - 1)
    tris.append((k, k + 1, k + 2))
    return np.array(verts), np.array(tris), np.array(normals), np.array(uvs), np.array(hs)


def tuft(name, seed, blades, segments, height, width, radius, tilt, bend):
    """草の株 1 つ (原点が地面)。葉ごとに表と裏の 2 枚を重ねる (同じ頂点・同じ法線)。"""
    rng = random.Random(f"{name}{seed}")
    mesh = sm.Mesh(name)
    V, F, N, UV, C = [], [], [], [], []
    base_index = 0
    for _ in range(blades):
        r = radius * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        base = (r * math.cos(a), r * math.sin(a), -0.02)   # 根元は少し地面に埋める (浮いて見えないように)
        # 株の外側の葉ほど低く、大きく倒れる
        k = r / radius
        h = rng.uniform(*height) * (1.0 - 0.35 * k)
        v, f, n, uv, t = blade(rng, base, h, rng.uniform(*width), rng.uniform(*tilt) + 20 * k,
                               rng.uniform(*bend), segments)
        dry, phase = rng.random(), rng.random()
        V.append(v)
        N.append(n)
        UV.append(uv)
        C.append(np.c_[t, np.full(len(t), dry), np.full(len(t), phase)])
        F.append(f + base_index)
        base_index += len(v)
    f = np.concatenate(F)
    mesh.add_cards(MATERIAL, np.concatenate(V), np.concatenate([f, f[:, ::-1]]), np.concatenate(N),
                   np.concatenate(UV), np.concatenate(C))
    return mesh


# ---------------------------------------------------------------- 地面の絵
GROUND_STROKES = 60000          # 上から見た草の葉の筆あと (短い線) の数
GROUND_STROKE_PX = (8, 30)      # 線の長さ (px。1px = 約 2.5mm)


def _strokes(rng, size, count, length, width):
    """上から見た草の葉: 向きのそろわない短い線をたくさん重ねる。(高さ 0..1, 葉ごとの乱数 0..1) の 2 枚を返す。
    端をまたぐ線は反対側にも描いて、上下左右がつながるようにする。"""
    hgt = Image.new("F", (size, size), 0.0)
    tone = Image.new("F", (size, size), 0.5)
    dh, dt = ImageDraw.Draw(hgt), ImageDraw.Draw(tone)
    # 葉の向きは場所ごとにゆるくそろう (踏まれたり風でなびいたりした向き)
    flow = value_noise(6, 6, rng, w=size, h=size)
    for i in range(count):
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        a = flow[int(y) % size, int(x) % size] * 2 * math.pi + rng.uniform(-1.0, 1.0)
        n = rng.uniform(*length)
        dx, dy = math.cos(a) * n, math.sin(a) * n
        h = (i + 1) / count * 0.6 + rng.uniform(0.0, 0.4)   # 後から描く線ほど上の葉 (高い)
        t = rng.random()
        w = rng.choice(width)
        for ox in (-size, 0, size):
            for oy in (-size, 0, size):
                if 0 <= x + ox + max(dx, 0) and x + ox + min(dx, 0) < size and 0 <= y + oy + max(dy, 0) and y + oy + min(dy, 0) < size:
                    seg = [(x + ox, y + oy), (x + ox + dx, y + oy + dy)]
                    dh.line(seg, fill=h, width=w)
                    dt.line(seg, fill=t, width=w)
    return np.asarray(hgt, np.float64), np.asarray(tone, np.float64)


def _blur(a, passes):
    """端が反対側につながったまま、3x3 の平均で passes 回ぼかす。"""
    for _ in range(passes):
        a = sum(np.roll(np.roll(a, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
    return a


def ground_textures(color_path, normal_path, size=GROUND_SIZE, seed=3):
    """草地の地面の色のむら (リニアの倍率、平均 0.5) と凹凸。上下左右がつながる。"""
    rng = random.Random(f"ground{seed}")
    height, tone = _strokes(rng, size, GROUND_STROKES, GROUND_STROKE_PX, (2, 2, 3, 4))
    soft = _blur(height, 2)
    Image.fromarray(normal_map(soft, 6.0)).save(normal_path)
    # 色: 上の葉ほど明るく、葉のすき間 (下の葉と根元) は暗い。葉ごとに明るさと色合いを少し変え、
    # ところどころ枯れた葉 (黄土色) が混じる。全体に大きめのむらを重ねる
    lum = 0.45 + 0.9 * soft + 0.3 * (tone - 0.5) + 0.2 * (value_noise(5, 5, rng, w=size, h=size) - 0.5)
    dead = np.clip((tone - 0.86) / 0.08, 0, 1) * np.clip(value_noise(8, 8, rng, w=size, h=size) * 1.6 - 0.3, 0, 1)
    r = lum * (1 + 0.30 * dead)
    g = lum * (1 + 0.06 * dead)
    b = lum * (1 - 0.30 * dead)
    rgb = np.stack([r, g, b], 2) * 0.5   # 0.5 で 1 倍 (UE で 2 倍して掛ける)
    Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).save(color_path)


def _fine(rng, size):
    """細かいざらつき (0..1)。"""
    out, amp, total = 0.0, 1.0, 0.0
    for cells in (64, 128, 256):
        out = out + value_noise(cells, cells, rng, w=size, h=size) * amp
        total += amp
        amp *= 0.6
    return out / total


def _wrapped(draw_fn, x, y, reach, size):
    """端をまたぐ形は反対側にも描く (上下左右がつながるように)。reach は形の大きさ (px)。"""
    for ox in (-size, 0, size):
        for oy in (-size, 0, size):
            if -reach <= x + ox < size + reach and -reach <= y + oy < size + reach:
                draw_fn(x + ox, y + oy)


def soil_textures(color_path, normal_path, size=GROUND_SIZE, seed=5):
    """切り土の斜面の土 (糸島の花こう岩が風化した真砂土)。色のむら (リニアの倍率、平均 0.5) と凹凸。
    絵の縦 (V) が斜面の上下になるように貼る (雨で削られた縦の筋)。1 枚を約 3m 四方に貼る。"""
    rng = random.Random(f"soil{seed}")
    noise = lambda cx, cy: value_noise(cx, cy, rng, w=size, h=size)
    # 縦の雨の筋 (横に細かく縦に長いむら)、土のでこぼこ、細かいざらつき
    rills = noise(40, 3) * 0.6 + noise(90, 6) * 0.4
    lumps = noise(6, 6) * 0.5 + noise(14, 14) * 0.3 + noise(32, 32) * 0.2
    grain = _fine(rng, size)
    height = 0.45 * lumps + 0.3 * rills + 0.25 * grain
    # 小石 (風化した花こう岩のかけら) と砂粒。石ごとに明るさを変え、上から光が当たったように陰を付ける
    stones = Image.new("F", (size, size), 0.0)
    tone = Image.new("F", (size, size), 0.5)
    ds, dt = ImageDraw.Draw(stones), ImageDraw.Draw(tone)
    for i in range(9000):
        big = i < 700
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        r = rng.uniform(2.0, 7.0) * (1 + 1.5 * rng.random() ** 4) if big else rng.uniform(0.6, 1.6)
        h, t = rng.uniform(0.6, 1.0), rng.uniform(0.0, 1.0)
        ry = r * rng.uniform(0.55, 1.0)

        def stone(cx, cy):
            box = (cx - r, cy - ry, cx + r, cy + ry)
            ds.ellipse(box, fill=h)
            dt.ellipse(box, fill=t)
        _wrapped(stone, x, y, r, size)
    mask = np.asarray(stones, np.float64)
    dome = _blur(mask, 2)
    tn = np.asarray(tone, np.float64)
    height = np.clip(height + 0.6 * dome, 0, 1.6)
    Image.fromarray(normal_map(_blur(height, 1), 9.0)).save(normal_path)
    # 色: 凹んだ所 (湿って暗い) と出っ張った所 (乾いて明るい)、黄土色のむら、黒っぽい腐植のしみ
    lum = 0.55 + 0.5 * (height - height.mean()) + 0.25 * (noise(5, 5) - 0.5)
    ochre = np.clip(noise(4, 4) * 1.5 - 0.4, 0, 1)
    humus = np.clip((noise(9, 9) * 0.6 + noise(23, 23) * 0.4 - 0.6) / 0.25, 0, 1) * 0.25
    r = lum * (1 + 0.18 * ochre - humus)
    g = lum * (1 + 0.02 * ochre - humus)
    b = lum * (1 - 0.15 * ochre - humus * 0.8)
    soil = np.stack([r, g, b], 2)
    # 石の色: 灰色から白っぽい灰色 (石ごと)。左上が明るく右下が暗い陰
    lit = np.clip(1 + 4.0 * (np.roll(np.roll(dome, 2, 0), 2, 1) - dome), 0.5, 1.5)
    gray = (0.45 + 0.5 * tn) * lit
    stone_rgb = np.stack([gray * 1.02, gray, gray * 0.97], 2)
    m = np.clip(mask * 1.4, 0, 1)[:, :, None]
    rgb = soil * (1 - m) + stone_rgb * m
    rgb = rgb / rgb.mean() * 0.5   # 平均を 0.5 (1 倍) にそろえる
    Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).save(color_path)


def asphalt_textures(color_path, normal_path, size=GROUND_SIZE, seed=7):
    """アスファルト。色のむら (リニアの倍率、平均 0.5。R は粗さにも使う) と凹凸。1 枚を約 1.5m 四方に貼る。
    黒い地 (アスファルト) に灰色の砕石の粒が詰まり、ところどころ細いひび割れがある。"""
    rng = random.Random(f"asphalt{seed}")
    noise = lambda cx, cy: value_noise(cx, cy, rng, w=size, h=size)
    stones = Image.new("F", (size, size), 0.0)
    tone = Image.new("F", (size, size), 0.0)
    ds, dt = ImageDraw.Draw(stones), ImageDraw.Draw(tone)
    for _ in range(26000):   # 砕石 (2〜10mm、1px = 約 1.5mm)
        x, y, r = rng.uniform(0, size), rng.uniform(0, size), rng.uniform(1.0, 3.5)
        h, t = rng.uniform(0.4, 1.0), rng.uniform(0.0, 1.0)

        def stone(cx, cy):
            box = (cx - r, cy - r * rng.uniform(0.6, 1.0), cx + r, cy + r)
            ds.ellipse(box, fill=h)
            dt.ellipse(box, fill=t)
        _wrapped(stone, x, y, r, size)
    st = np.asarray(stones, np.float64)
    tn = np.asarray(tone, np.float64)
    # ひび割れ: 曲がりながら伸びる細い線 (凹んで黒い)
    cracks = Image.new("F", (size, size), 0.0)
    dc = ImageDraw.Draw(cracks)
    for _ in range(7):
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        a = rng.uniform(0, 2 * math.pi)
        for _ in range(rng.randint(20, 60)):
            a += rng.uniform(-0.6, 0.6)
            n = rng.uniform(4, 12)
            x2, y2 = x + math.cos(a) * n, y + math.sin(a) * n
            _wrapped(lambda cx, cy: dc.line([(cx, cy), (cx + x2 - x, cy + y2 - y)], fill=1.0, width=2), x, y, n + 2, size)
            x, y = x2 % size, y2 % size
    ck = _blur(np.asarray(cracks, np.float64), 1)
    height = np.clip(0.35 * _fine(rng, size) + 0.6 * st - 0.6 * ck, 0, 1)
    Image.fromarray(normal_map(height, 7.0)).save(normal_path)
    # 色: 砕石は灰色 (明るさがばらつく)、地は黒。大きなむら (油じみ・補修のあと)、ひび割れはさらに黒い
    stone_lum = 0.6 + 0.5 * tn
    lum = 0.4 + (stone_lum - 0.4) * np.clip(st * 1.6, 0, 1)
    lum = lum * (1 + 0.35 * (noise(4, 4) - 0.5) + 0.15 * (noise(12, 12) - 0.5)) * (1 - 0.6 * ck)
    rgb = np.stack([lum, lum, lum * 1.03], 2)
    rgb = rgb / rgb.mean() * 0.5   # 平均を 0.5 (1 倍) にそろえる
    Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).save(color_path)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    out = os.path.join(area.out_dir, "grass")
    os.makedirs(out, exist_ok=True)
    meshes = {}
    for name, spec in TUFTS.items():
        mesh = tuft(name, **spec)
        fname = f"{name}.gltf"
        tris = sm.write_gltf(mesh, os.path.join(out, fname))
        lo, hi = mesh.bounds()
        print(f"  {fname}: 三角形 {tris} (表と裏)、大きさ {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f} x {hi[2] - lo[2]:.2f} m")
        meshes[name] = fname
    ground = {}
    for key, make in (("", ground_textures), ("soil_", soil_textures), ("asphalt_", asphalt_textures)):
        base = "T_FD_" + ({"": "Ground", "soil_": "Soil", "asphalt_": "Asphalt"}[key])
        color, normal = f"{base}_D.png", f"{base}_N.png"
        make(os.path.join(out, color), os.path.join(out, normal))
        ground[f"{key}color"], ground[f"{key}normal"] = color, normal
        print(f"  {color}, {normal}")
    with open(os.path.join(out, "grass.json"), "w", encoding="utf-8") as f:
        json.dump({"meshes": meshes, "ground": ground}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
