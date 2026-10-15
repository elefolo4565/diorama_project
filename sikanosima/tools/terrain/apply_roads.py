"""道路を地形に焼き込み、バイクで走れる平らな路面を作る。

build_terrain.py と build_roads.py の後に実行する。
道路ごとに高さをならし、幅の内側を路面の高さに、外側の路肩を元の地形へなめらかにつなぐ。
橋とトンネルは地形を削らない。

使い方:
    python apply_roads.py areas/futamigaura.json

出力 (out/<エリア名>/):
    heightmap.png / heightmap.r16 / landscape_import.json  道路を焼き込んだ版で上書き
    height_road_m.npy  道路を焼き込んだ標高 (m)
    road_layer.png     ランドスケープの道路レイヤー用ウェイトマップ (8bit, 255 = 路面)。road_layer.r8 は同じ内容の RAW
    roads.json         ポイントの Z をならした路面の高さに更新
"""

import json
import os
import sys

import numpy as np
from PIL import Image

from build_roads import ROAD_Z_OFFSET_M
from build_terrain import write_outputs
from geo import Area

SHOULDER_M = 6.0        # 路肩から元の地形へつなぐ幅
SMOOTH_WINDOW_M = 50.0  # 路面の高さをならす区間長
MASK_FEATHER_M = 1.0    # 道路レイヤーの縁のぼかし幅
MIN_ROAD_Z_M = 0.5      # 路面の最低の高さ (海面 = 0)
SURFACE_SMOOTH_PX = 2   # 焼き込んだ路面の高さを、この半径 (画素) の箱型ぼかし 3 回でならす (交差点の段差や折れ目を消す)


def smooth_profile(z, spacing_m):
    n = max(1, int(round(SMOOTH_WINDOW_M / spacing_m)))
    if len(z) < 3 or n < 2:
        return z
    k = np.ones(2 * (n // 2) + 1) / (2 * (n // 2) + 1)
    pad = len(k) // 2
    zp = np.pad(z, pad, mode="edge")
    out = np.convolve(zp, k, mode="valid")
    # 端点は元の高さに固定し、他の道路との接続でずれないようにする
    out[0], out[-1] = z[0], z[-1]
    return out


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def box_blur(a, r):
    """端は端の値をのばして、半径 r の箱型の平均。"""
    k = 2 * r + 1
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r + 1, r)
        c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
        a = (np.take(c, range(k, c.shape[axis]), axis=axis) - np.take(c, range(0, c.shape[axis] - k), axis=axis)) / k
    return a


def burn(area, base, roads):
    """base (地形) に道路を焼き込む。重なりは道路の重み (中心ほど1) が大きい方、同じなら道路の中心線に近い方を採用。
    路面の内側は重みがどれも 1 なので、近い方を選ばないと、先に焼いた区間の端 (高さが一定) が次の区間の始まりに
    はみ出し、頂点ごとに平らな所と段差ができる (走るとガタガタする)。"""
    n = base.shape[0]
    mpp = area.meters_per_px
    weight = np.zeros_like(base, dtype=np.float32)
    road_z = np.zeros_like(base, dtype=np.float32)
    mask = np.zeros_like(base, dtype=np.float32)
    dist = np.full(base.shape, np.inf, dtype=np.float32)

    for r in roads:
        if r["bridge"] or r["tunnel"]:
            continue
        pts = np.array(r["points_cm"], dtype=np.float64) / 100.0  # UE m: X 東, Y 南, Z
        if len(pts) < 2:
            continue
        seg_len = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1)
        spacing = float(np.mean(seg_len)) if len(seg_len) else 10.0
        z = smooth_profile(pts[:, 2] - ROAD_Z_OFFSET_M, max(spacing, 1e-3))
        # 海岸沿いで海底の高さを拾っても、路面は海面より上に保つ
        z = np.maximum(z, MIN_ROAD_Z_M)
        pts[:, 2] = z
        r["points_cm"] = [[round(p[0] * 100, 1), round(p[1] * 100, 1),
                           round((p[2] + ROAD_Z_OFFSET_M) * 100, 1)] for p in pts]
        half = r["width_cm"] / 200.0
        reach = half + SHOULDER_M

        # 画素座標: col = (X + half_m)/mpp, row = (Y + half_m)/mpp  (UE の +Y は南 = 画素の下)
        cols = (pts[:, 0] + area.half_m) / mpp
        rows = (pts[:, 1] + area.half_m) / mpp
        for i in range(len(pts) - 1):
            c0, r0, c1, r1 = cols[i], rows[i], cols[i + 1], rows[i + 1]
            pad = reach / mpp + 1
            cmin, cmax = int(max(0, np.floor(min(c0, c1) - pad))), int(min(n - 1, np.ceil(max(c0, c1) + pad)))
            rmin, rmax = int(max(0, np.floor(min(r0, r1) - pad))), int(min(n - 1, np.ceil(max(r0, r1) + pad)))
            if cmin > cmax or rmin > rmax:
                continue
            cc, rr = np.meshgrid(np.arange(cmin, cmax + 1), np.arange(rmin, rmax + 1))
            dc, dr = c1 - c0, r1 - r0
            L2 = dc * dc + dr * dr
            t = np.clip(((cc - c0) * dc + (rr - r0) * dr) / L2, 0, 1) if L2 > 0 else np.zeros_like(cc, float)
            d = np.hypot(cc - (c0 + t * dc), rr - (r0 + t * dr)) * mpp
            w = 1.0 - smoothstep((d - half) / SHOULDER_M)
            zz = z[i] + (z[i + 1] - z[i]) * t
            win = (slice(rmin, rmax + 1), slice(cmin, cmax + 1))
            better = (w > weight[win] + 1e-6) | ((w >= weight[win] - 1e-6) & (d < dist[win]))
            weight[win] = np.where(better, w, weight[win])
            road_z[win] = np.where(better, zz, road_z[win])
            dist[win] = np.where(better, d, dist[win])
            m = 1.0 - smoothstep((d - half) / MASK_FEATHER_M)
            mask[win] = np.maximum(mask[win], m)

    # 路面の高さを道路のある所だけで (重み付きで) ぼかし、交差点の段差や頂点の折れ目をなめらかにする
    if SURFACE_SMOOTH_PX > 0:
        wz, ww = road_z * weight, weight.astype(np.float64)
        for _ in range(3):
            wz, ww = box_blur(wz, SURFACE_SMOOTH_PX), box_blur(ww, SURFACE_SMOOTH_PX)
        road_z = np.where(weight > 0, wz / np.maximum(ww, 1e-6), road_z).astype(np.float32)
    out = base * (1.0 - weight) + road_z * weight
    return out.astype(np.float32), mask


def surface_z(area, height, roads):
    """roads.json の点の Z を、焼き込んだ路面の高さにする。橋とトンネルは自分の点の高さをならす。"""
    n = height.shape[0]
    for r in roads:
        pts = np.array(r["points_cm"], dtype=np.float64) / 100.0
        if len(pts) < 2:
            continue
        if r["bridge"] or r["tunnel"]:
            seg = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1)
            z = np.maximum(smooth_profile(pts[:, 2] - ROAD_Z_OFFSET_M, max(float(np.mean(seg)), 1e-3)), MIN_ROAD_Z_M)
        else:
            col = np.clip((pts[:, 0] + area.half_m) / area.meters_per_px, 0, n - 1.001)
            row = np.clip((pts[:, 1] + area.half_m) / area.meters_per_px, 0, n - 1.001)
            c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
            tc, tr = col - c0, row - r0
            z = (height[r0, c0] * (1 - tc) * (1 - tr) + height[r0, c0 + 1] * tc * (1 - tr)
                 + height[r0 + 1, c0] * (1 - tc) * tr + height[r0 + 1, c0 + 1] * tc * tr)
        r["points_cm"] = [[p[0], p[1], round(float(zz + ROAD_Z_OFFSET_M) * 100, 1)]
                          for p, zz in zip(r["points_cm"], z)]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    out = area.out_dir
    for f in ("height_m.npy", "roads.json"):
        if not os.path.exists(os.path.join(out, f)):
            sys.exit(f"{f} がありません。先に build_terrain.py と build_roads.py を実行してください。")
    base = np.load(os.path.join(out, "height_m.npy"))
    sea = np.load(os.path.join(out, "sea_mask.npy"))
    with open(os.path.join(out, "roads.json"), encoding="utf-8") as f:
        doc = json.load(f)
    # タイルの外側まで続けた道路 (build_roads.py の roads_margin.json) を焼くと、隣のタイルと境目の路面がそろう
    wide_path = os.path.join(out, "roads_margin.json")
    if os.path.exists(wide_path):
        with open(wide_path, encoding="utf-8") as f:
            wide = json.load(f)["roads"]
    else:
        wide = json.loads(json.dumps(doc["roads"]))
    # 優先度の低い道路から焼き、主要道路の形を優先する (重なりは重みで決まる)
    height, mask = burn(area, base, sorted(wide, key=lambda r: -r["priority"]))
    roads = doc["roads"]
    surface_z(area, height, roads)
    write_outputs(area, height, sea, height_file="height_road_m.npy")
    layer = np.round(mask * 255).astype(np.uint8)
    Image.fromarray(layer).save(os.path.join(out, "road_layer.png"))
    layer.tofile(os.path.join(out, "road_layer.r8"))   # 同じ内容の RAW (C++ の UFDEditorTools::CreateLandscape が読む)
    doc["roads"] = sorted(roads, key=lambda r: (r["priority"], r["id"]))
    doc["z_note"] = "Z は apply_roads.py でならした路面の高さ"
    with open(os.path.join(out, "roads.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    changed = np.abs(height - base)
    print(f"道路を焼き込みました: 変更画素 {np.count_nonzero(changed > 0.01)}, 最大変化 {changed.max():.1f} m")
    print(f"出力先: {out}")


if __name__ == "__main__":
    main()
