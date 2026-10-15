"""国土地理院の標高タイルから UE5 ランドスケープ用の 16bit ハイトマップを作る。

使い方:
    python build_terrain.py areas/futamigaura.json

出力 (out/<エリア名>/):
    heightmap.png       16bit グレースケール。UE のランドスケープ「ファイルからインポート」に使う
    heightmap.r16       同じ内容の RAW (リトルエンディアン)
    height_m.npy        標高 (m, float32)。道路スクリプトとプレビューが使う
    height_margin_m.npy タイルの外側 TERRAIN_MARGIN_M まで含めた標高 (隣のタイルとの境目で道路をつなぐため)
    sea_mask.npy        海 (標高データなし) の画素
    landscape_import.json  UE で入力する位置・スケールなど

データ出典: 国土地理院 標高タイル (DEM5A / DEM10B)
https://maps.gsi.go.jp/development/ichiran.html#dem
"""

import copy
import io
import json
import math
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

from geo import Area, http_get, latlon_to_global_px

DEM_SOURCES = [
    # (名前, URL, ズーム) 先にあるものを優先し、欠けた画素を後のもので埋める
    ("dem5a", "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png", 15),
    ("dem10b", "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png", 14),
]

# 海底: 海岸線から沖へ 1:20 で下がり、最大 30m の深さ
SEA_SHORE_DEPTH_M = 1.0
SEA_SLOPE = 0.05
SEA_MAX_DEPTH_M = 30.0

# タイルの外側にこれだけ広く標高を読んでから切り取る。海の判定・海底の深さ・海岸のならしが
# 隣のタイルと同じ結果になり、境目の高さがそろう (海底の傾斜が届く 580m より広くする)
TERRAIN_MARGIN_M = 640.0

# 海岸線のならし: 境目から何 m の帯を、どのくらいの半径でぼかすか
COAST_BAND_M = 20.0
COAST_BLUR_M = 7.0


def decode_dem_png(data):
    """地理院の標高 PNG -> 標高 (m)。無効値は NaN。"""
    if data is None:
        return np.full((256, 256), np.nan, dtype=np.float64)
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(np.int64)
    x = rgb[..., 0] * 65536 + rgb[..., 1] * 256 + rgb[..., 2]
    h = np.where(x < 2 ** 23, x, x - 2 ** 24).astype(np.float64) * 0.01
    h[x == 2 ** 23] = np.nan
    return h


def load_mosaic(area, name, url, zoom):
    s, w, n, e = area.bbox(margin_m=200.0)
    px0, py0 = latlon_to_global_px(n, w, zoom)
    px1, py1 = latlon_to_global_px(s, e, zoom)
    tx0, ty0 = int(px0 // 256), int(py0 // 256)
    tx1, ty1 = int(px1 // 256), int(py1 // 256)
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    print(f"[{name}] z{zoom} タイル {nx}x{ny} 枚を取得")
    mosaic = np.full((ny * 256, nx * 256), np.nan, dtype=np.float64)
    for j in range(ny):
        for i in range(nx):
            tx, ty = tx0 + i, ty0 + j
            cache = os.path.join(area.cache_dir, name, str(zoom), str(tx), f"{ty}.png")
            data = http_get(url.format(z=zoom, x=tx, y=ty), cache)
            mosaic[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = decode_dem_png(data)
        print(f"  {j + 1}/{ny} 行", end="\r")
    print()
    return mosaic, tx0 * 256, ty0 * 256


def sample_bilinear(mosaic, gx, gy):
    """全球ピクセル座標 (タイル原点で引いたもの) で双線形補間。近傍に NaN があれば NaN。"""
    # 画素中心は +0.5 の位置
    fx = gx - 0.5
    fy = gy - 0.5
    x0 = np.floor(fx).astype(np.int64)
    y0 = np.floor(fy).astype(np.int64)
    tx = fx - x0
    ty = fy - y0
    hgt, wid = mosaic.shape
    x0 = np.clip(x0, 0, wid - 2)
    y0 = np.clip(y0, 0, hgt - 2)
    v00 = mosaic[y0, x0]
    v10 = mosaic[y0, x0 + 1]
    v01 = mosaic[y0 + 1, x0]
    v11 = mosaic[y0 + 1, x0 + 1]
    return (v00 * (1 - tx) * (1 - ty) + v10 * tx * (1 - ty) + v01 * (1 - tx) * ty + v11 * tx * ty)


def resample_to_grid(area, mosaic, ox, oy, zoom):
    size = area.size_px
    out = np.empty((size, size), dtype=np.float32)
    cols = np.arange(size, dtype=np.float64)
    chunk = 256
    for r0 in range(0, size, chunk):
        rows = np.arange(r0, min(r0 + chunk, size), dtype=np.float64)
        cc, rr = np.meshgrid(cols, rows)
        x, y = area.pixel_to_local(cc, rr)
        lat, lon = area.to_latlon(x, y)
        gx, gy = latlon_to_global_px(lat, lon, zoom)
        out[r0:r0 + len(rows)] = sample_bilinear(mosaic, gx - ox, gy - oy)
    return out


def flood_from_border(nan_mask):
    """外周に接している NaN 領域 (= 海) を返す。それ以外の NaN は内陸のデータ欠損。"""
    hgt, wid = nan_mask.shape
    sea = np.zeros_like(nan_mask)
    q = deque()
    for c in range(wid):
        for r in (0, hgt - 1):
            if nan_mask[r, c] and not sea[r, c]:
                sea[r, c] = True
                q.append((r, c))
    for r in range(hgt):
        for c in (0, wid - 1):
            if nan_mask[r, c] and not sea[r, c]:
                sea[r, c] = True
                q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < hgt and 0 <= nc < wid and nan_mask[nr, nc] and not sea[nr, nc]:
                sea[nr, nc] = True
                q.append((nr, nc))
    return sea


def shift(a, dr, dc, fill):
    out = np.full_like(a, fill)
    hgt, wid = a.shape
    out[max(dr, 0):hgt + min(dr, 0), max(dc, 0):wid + min(dc, 0)] = \
        a[max(-dr, 0):hgt + min(-dr, 0), max(-dc, 0):wid + min(-dc, 0)]
    return out


def distance_to_land(sea, cell_m, max_m):
    """8近傍の反復でおおよその距離 (m) を求める。max_m を超えた分は max_m。"""
    dist = np.where(sea, np.inf, 0.0).astype(np.float32)
    steps = int(math.ceil(max_m / cell_m)) + 1
    diag = cell_m * math.sqrt(2)
    for _ in range(steps):
        best = dist
        for dr, dc, d in ((1, 0, cell_m), (-1, 0, cell_m), (0, 1, cell_m), (0, -1, cell_m),
                          (1, 1, diag), (1, -1, diag), (-1, 1, diag), (-1, -1, diag)):
            best = np.minimum(best, shift(dist, dr, dc, np.inf) + d)
        if np.array_equal(best, dist):
            break
        dist = best
    return np.minimum(dist, max_m)


def fill_holes(height, holes):
    """内陸の欠損を周囲の値で少しずつ埋める。"""
    h = height.copy()
    todo = holes.copy()
    while todo.any():
        acc = np.zeros_like(h)
        cnt = np.zeros_like(h)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v = shift(h, dr, dc, np.nan)
            ok = ~np.isnan(v)
            acc[ok] += v[ok]
            cnt[ok] += 1
        newly = todo & (cnt > 0)
        if not newly.any():
            break
        h[newly] = acc[newly] / cnt[newly]
        todo &= ~newly
    return h


def fill_holes_coarse(height, holes, k):
    """粗いグリッドで穴を埋めてから戻し、境目をならす (広い欠損でも速い)。"""
    hgt, wid = height.shape
    hh, ww = -(-hgt // k), -(-wid // k)
    pad = np.full((hh * k, ww * k), np.nan, dtype=np.float64)
    pad[:hgt, :wid] = height
    blocks = pad.reshape(hh, k, ww, k)
    cnt = np.count_nonzero(~np.isnan(blocks), axis=(1, 3))
    total = np.nansum(blocks, axis=(1, 3))
    coarse = np.where(cnt > 0, total / np.maximum(cnt, 1), np.nan)
    coarse = fill_holes(coarse, np.isnan(coarse))
    up = np.repeat(np.repeat(coarse, k, axis=0), k, axis=1)[:hgt, :wid]
    # 海 (NaN のまま) を仮の値で埋めてからならし、結果は穴の画素にだけ使う
    tmp = np.where(np.isnan(height), up, height)
    blurred = box_blur_where(box_blur_where(tmp, holes, radius=2 * k), holes, radius=k)
    out = height.copy()
    out[holes] = blurred[holes]
    return out


def downsample_bool(mask, k):
    hgt, wid = mask.shape
    hh, ww = hgt // k, wid // k
    return mask[:hh * k, :ww * k].reshape(hh, k, ww, k).all(axis=(1, 3))


def upsample_nearest(a, k, shape):
    up = np.repeat(np.repeat(a, k, axis=0), k, axis=1)
    out = np.empty(shape, dtype=a.dtype)
    hh, ww = min(shape[0], up.shape[0]), min(shape[1], up.shape[1])
    out[:hh, :ww] = up[:hh, :ww]
    if hh < shape[0]:
        out[hh:, :ww] = up[hh - 1:hh, :ww]
    if ww < shape[1]:
        out[:, ww:] = out[:, ww - 1:ww]
    return out


def build(area):
    """タイルの外側に TERRAIN_MARGIN_M 広げて作り、タイルの範囲を切り取って返す。"""
    k = max(1, int(round(8.0 / area.meters_per_px)))
    margin = int(round(TERRAIN_MARGIN_M / area.meters_per_px / k)) * k
    big = copy.copy(area)
    big.size_px = area.size_px + 2 * margin
    height, sea = build_raster(big)
    # 外側も含めた標高は、タイルの外へ少しはみ出して道路を焼く apply_roads.py が使う
    np.save(os.path.join(area.out_dir, "height_margin_m.npy"), height)
    crop = (slice(margin, margin + area.size_px), slice(margin, margin + area.size_px))
    return np.ascontiguousarray(height[crop]), np.ascontiguousarray(sea[crop])


def build_raster(area):
    height = None
    for name, url, zoom in DEM_SOURCES:
        mosaic, ox, oy = load_mosaic(area, name, url, zoom)
        h = resample_to_grid(area, mosaic, ox, oy, zoom)
        valid = np.count_nonzero(~np.isnan(h)) / h.size
        print(f"[{name}] 有効画素 {valid:.1%}")
        if height is None:
            height = h
        else:
            gap = np.isnan(height)
            height[gap] = h[gap]

    nan_mask = np.isnan(height)
    if nan_mask.all():
        sys.exit("標高データが1画素もありません。エリア設定 (中心座標) を確認してください。")

    # 海の判定と距離計算は粗いグリッドで行う (速度のため)
    k = max(1, int(round(8.0 / area.meters_per_px)))
    coarse_nan = downsample_bool(nan_mask, k)
    coarse_sea = flood_from_border(coarse_nan)
    # 粗いブロックの境目で海が欠けないよう、海ブロックに隣接する欠損画素も海に含める
    sea_up = upsample_nearest(coarse_sea, k, nan_mask.shape).astype(np.float64)
    near_sea = box_blur_where(sea_up, np.ones(nan_mask.shape, dtype=bool), radius=k) > 0.0
    sea = near_sea & nan_mask
    holes = nan_mask & ~sea
    if holes.any():
        print(f"内陸の欠損 {np.count_nonzero(holes)} 画素を周囲の値で補間")
        height = fill_holes_coarse(height, holes, k)

    max_d = (SEA_MAX_DEPTH_M - SEA_SHORE_DEPTH_M) / SEA_SLOPE
    coarse_dist = distance_to_land(coarse_sea, k * area.meters_per_px, max_d)
    dist = upsample_nearest(coarse_dist, k, nan_mask.shape)
    depth = np.minimum(SEA_SHORE_DEPTH_M + dist * SEA_SLOPE, SEA_MAX_DEPTH_M)
    height[sea] = -depth[sea]
    # 粗いグリッド由来の段差をならす (海の部分だけ)
    if sea.any():
        height = box_blur_where(height, sea, radius=k)
        # 崖の近くでならした結果、海が陸になってしまわないようにする
        height[sea] = np.minimum(height[sea], -0.5 * SEA_SHORE_DEPTH_M)
        height = smooth_coastline(height, sea, area.meters_per_px)

    return height.astype(np.float32), sea


def smooth_coastline(height, sea, meters_per_px):
    """標高データの格子 (約4〜8m) がそのまま出た階段状の海岸線をならす。

    陸と海の境目から COAST_BAND_M 以内だけをぼかす。海面 (Z=0) との交線が
    なめらかな等高線になるので、水を置いたときの汀線もなめらかになる。
    """
    band_r = max(1, int(round(COAST_BAND_M / meters_per_px)))
    frac = box_blur_where(sea.astype(np.float64), np.ones_like(sea), radius=band_r)
    band = (frac > 0.0) & (frac < 1.0)
    if not band.any():
        return height
    r = max(1, int(round(COAST_BLUR_M / meters_per_px)))
    h = height.astype(np.float64)
    for _ in range(2):
        h = box_blur_where(h, band, radius=r)
    # 帯の外側へなめらかにつなぐ
    w = np.clip(1.0 - np.abs(frac - 0.5) * 2.0, 0.0, 1.0)
    w = box_blur_where(w, np.ones_like(sea), radius=r)
    return height * (1.0 - w) + h * w


def box_blur_where(a, mask, radius):
    """mask の画素だけ (2r+1)^2 の平均で置き換える。積分画像で計算。"""
    pad = np.pad(a.astype(np.float64), radius + 1, mode="edge")
    ii = pad.cumsum(0).cumsum(1)
    r = radius
    hgt, wid = a.shape
    s = (ii[2 * r + 1:2 * r + 1 + hgt, 2 * r + 1:2 * r + 1 + wid]
         - ii[0:hgt, 2 * r + 1:2 * r + 1 + wid]
         - ii[2 * r + 1:2 * r + 1 + hgt, 0:wid]
         + ii[0:hgt, 0:wid])
    mean = s / (2 * r + 1) ** 2
    out = a.copy()
    out[mask] = mean[mask]
    return out


def choose_z_scale(height):
    """UE: 高さ(cm) = (値 - 32768) * ZScale / 128。海面 (0m) を 32768 に固定する。"""
    peak_cm = float(np.max(np.abs(height))) * 100.0
    needed = peak_cm * 128.0 / 32000.0
    return float(max(10, int(math.ceil(needed / 10.0)) * 10))


def write_outputs(area, height, sea, height_file="height_m.npy"):
    z_scale = choose_z_scale(height)
    values = np.round(32768.0 + height.astype(np.float64) * 100.0 * 128.0 / z_scale)
    values = np.clip(values, 0, 65535).astype(np.uint16)

    out = area.out_dir
    Image.fromarray(values).save(os.path.join(out, "heightmap.png"))
    values.astype("<u2").tofile(os.path.join(out, "heightmap.r16"))
    np.save(os.path.join(out, height_file), height)
    np.save(os.path.join(out, "sea_mask.npy"), sea)

    size_cm = area.size_m * 100.0
    params = {
        "area": area.name,
        "center_lat": area.center_lat,
        "center_lon": area.center_lon,
        "resolution": f"{area.size_px} x {area.size_px}",
        "size_m": area.size_m,
        # UE5.8 の取り込み画面の「場所」はランドスケープの中心。中心をエリア中心 (原点) に置く
        "location_cm": [0.0, 0.0, 0.0],
        "corner_location_cm": [-size_cm / 2.0, -size_cm / 2.0, 0.0],
        "scale": [area.meters_per_px * 100.0, area.meters_per_px * 100.0, z_scale],
        "sea_level_z_cm": 0.0,
        "height_min_m": round(float(height.min()), 2),
        "height_max_m": round(float(height.max()), 2),
        "precision_cm": round(z_scale / 128.0, 3),
        "note": "UE の +X が東、+Y が南。Water の海面は Z=0 に置く。",
    }
    with open(os.path.join(out, "landscape_import.json"), "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)
    print(json.dumps(params, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    height, sea = build(area)
    write_outputs(area, height, sea)
    print(f"出力先: {area.out_dir}")


if __name__ == "__main__":
    main()
