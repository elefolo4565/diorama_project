"""meisho/ の名所を、置く所の地形と道路の上に作って調べ、確認用の画像を描く (UE は使わない)。

使い方 (地域のフォルダの tools/terrain で。タイルの地形 (build_tiles.py) を作った後):
    python meisho/check.py areas/<コース名>.json              そのコースのタイルにあるすべての名所
    python meisho/check.py areas/<コース名>.json kininkouen   meisho/kininkouen.py だけ

出力 (out/meisho/): <名前>_preview.png (真上・道路から見た所・横から見た断面。地形は緑、道路は灰色) と .gltf
調べること: 三角形の数、マテリアルの名前と定義、名所の点からの広がり、同じ形になるか、地面から浮いている部品・埋まりすぎの部品。
"""

import glob
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import scenery_meshes as sm  # noqa: E402
from build_scenery import Grid  # noqa: E402
from geo import Area  # noqa: E402

import meisho  # noqa: E402
from plants.check import render  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "out", "meisho")
MAX_TRIS = 60000
MAX_SPREAD_M = 150.0
PATCH_M = 26.0          # 確認用の地形を描く範囲 (名所の点から)
sm.MATERIALS.setdefault("FD_MeishoCheckGround", dict(color=(0.10, 0.20, 0.06), roughness=1.0))
sm.MATERIALS.setdefault("FD_MeishoCheckRoad", dict(color=(0.12, 0.12, 0.12), roughness=1.0))


def tiles_of(course_path):
    base = os.path.splitext(course_path)[0]
    return sorted(glob.glob(os.path.join(base, "*.json")))


def mesh_hash(mesh):
    h = hashlib.sha1()
    for mat, v, f in mesh.parts:
        h.update(mat.encode())
        h.update(np.round(v, 4).tobytes())
        h.update(np.asarray(f).tobytes())
    return h.hexdigest()


def terrain_patch(ctx, roads):
    """名所のまわりの地形 (緑) と道路 (灰色) の形。確認の絵にだけ使う。"""
    m = sm.Mesh("check_ground", flat=True)
    step = 1.5
    xs = np.arange(ctx.x - PATCH_M, ctx.x + PATCH_M + 0.01, step)
    ys = np.arange(ctx.y - PATCH_M, ctx.y + PATCH_M + 0.01, step)
    gx, gy = np.meshgrid(xs, ys)
    gz = ctx.ground(gx, gy)
    v = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], 1)
    nx = len(xs)
    tris = []
    for j in range(len(ys) - 1):
        for i in range(nx - 1):
            a, b, c, d = j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i
            tris += [(a, b, c), (a, c, d)]
    m.add("FD_MeishoCheckGround", v, np.array(tris))
    for r in roads:
        p = np.asarray(r["points_cm"], float) / 100
        near = np.hypot(p[:, 0] - ctx.x, p[:, 1] - ctx.y) < PATCH_M * 1.4
        if near.sum() >= 2:
            q = p[near].copy()
            q[:, 2] += 0.08
            m.add("FD_MeishoCheckRoad", *sm.swept_rect(q, r["width_cm"] / 100, 0.1))
    return m


def rotated(meshes, ctx):
    """道路の座標の s (奥行き) が +Y、u が +X になるように回し、名所の点を原点にした 1 つの形。"""
    t = math.radians(ctx.yaw_deg - 90.0)
    rot = np.array([[math.cos(-t), -math.sin(-t)], [math.sin(-t), math.cos(-t)]])
    out = sm.Mesh("view", flat=True)
    for mesh in meshes:
        for mat, v, f in mesh.parts:
            v = v.copy()
            v[:, :2] = (v[:, :2] - (ctx.x, ctx.y)) @ rot.T
            out.add(mat, v, f)
    return out


def check_one(name, mod, ctx, roads):
    errs, notes = [], []
    mesh = mod.build(ctx)
    mesh.name = meisho.mesh_name(name)
    if not mesh.parts:
        return [f"{name}: 形が空です"], notes, None
    tris = sum(len(f) for _, _, f in mesh.parts)
    lo, hi = mesh.bounds()
    spread = max(np.hypot(lo[0] - ctx.x, lo[1] - ctx.y), np.hypot(hi[0] - ctx.x, hi[1] - ctx.y))
    notes.append(f"三角形 {tris}、点からの広がり {spread:.0f} m、高さ {lo[2]:.1f}〜{hi[2]:.1f} m"
                 + (f"、いちばん近い道路 {ctx.road['name'] or '(名前なし)'} {ctx.road['dist']:.1f} m" if ctx.road else ""))
    if tris > MAX_TRIS:
        errs.append(f"{name}: 三角形が多すぎます ({tris} > {MAX_TRIS})")
    if spread > MAX_SPREAD_M:
        errs.append(f"{name}: 名所の点から {spread:.0f} m まで広がっています (>{MAX_SPREAD_M:.0f} m)")
    for mat, _, _ in mesh.parts:
        if mat not in sm.MATERIALS:
            errs.append(f"{name}: マテリアル {mat} が MATERIALS にありません")
        elif mat not in getattr(mod, "MATERIALS", {}) and not mat.startswith("FD_"):
            errs.append(f"{name}: マテリアル {mat} の名前は FD_ で始めてください")
    again = mod.build(ctx)
    if mesh_hash(again) != mesh_hash(mesh):
        errs.append(f"{name}: 2 回作ると形が変わります (乱数は scenery_meshes.Rng(seed) を使う)")
    # 浮いている部品: 部品の底が地面より 0.5m 以上上で、真下に地面がある
    floating = 0
    for mat, v, f in mesh.parts:
        c = v.mean(0)
        if v[:, 2].min() - ctx.ground(c[0], c[1]) > 0.5 and "Rail" not in mat:
            floating += 1
    if floating:
        notes.append(f"地面から 0.5m 以上浮いている部品 {floating} 個 (手すり以外。橋や台の上なら問題なし)")
    return errs, notes, mesh


def preview(name, mesh, ctx, roads, path):
    scene = rotated([terrain_patch(ctx, roads), mesh], ctx)
    only = rotated([mesh], ctx)
    views = [render(scene, {}, "top"), render(scene, {}, "front"), render(only, {}, "side")]
    names = ["真上 (下が道路の側)", "道路から見た所", "横から見た断面 (左が道路)"]
    W = views[0].width
    im = Image.new("RGB", (W * 3, W + 22), (255, 255, 255))
    d = ImageDraw.Draw(im)
    font = None
    for fp in ("C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, 13)
            break
    for i, (v, label) in enumerate(zip(views, names)):
        im.paste(v, (i * W, 22))
        d.text((i * W + 6, 3), label, fill=(30, 30, 30), font=font)
    im.save(path)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    course, names = sys.argv[1], sys.argv[2:] or None
    os.makedirs(OUT, exist_ok=True)
    found, all_errs = 0, []
    for tile_path in tiles_of(course):
        area = Area(tile_path)
        hp = os.path.join(area.out_dir, "height_road_m.npy")
        rp = os.path.join(area.out_dir, "roads.json")
        if not (os.path.exists(hp) and os.path.exists(rp)):
            continue
        with open(rp, encoding="utf-8") as f:
            roads = json.load(f)["roads"]
        # apply_roads.py と同じく名所の地面を平らにした地形で調べる (タイルの地形を作り直す前でも確かめられる)
        height = np.load(hp)
        ref = os.path.join(area.out_dir, "height_m.npy")
        height, _ = meisho.flatten(area, height, roads, ref=np.load(ref) if os.path.exists(ref) else None, names=names)
        grid = Grid(area, height)
        for name, mod, ctx in meisho.find(area, grid, roads, names):
            found += 1
            print(f"{name} ({mod.NAME_JA}) タイル {area.name}")
            errs, notes, mesh = check_one(name, mod, ctx, roads)
            for n in notes:
                print("  " + n)
            all_errs += errs
            if mesh is not None:
                sm.write_gltf(mesh, os.path.join(OUT, f"{mesh.name}.gltf"))
                p = os.path.join(OUT, f"{name}_preview.png")
                preview(name, mesh, ctx, roads, p)
                print(f"  確認用の画像: {p}")
    if not found:
        all_errs.append("このコースのタイルに名所がありません (タイルの地形を作ったか、LATLON が範囲の中か確かめてください)")
    for e in all_errs:
        print("NG: " + e)
    print("OK" if not all_errs else "NG")
    sys.exit(1 if all_errs else 0)


if __name__ == "__main__":
    main()
