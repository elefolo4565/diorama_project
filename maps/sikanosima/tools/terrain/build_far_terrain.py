"""ランドスケープ (4km 四方) の外側に置く、遠景の地形メッシュを作る。

エリアの端が崖になって途切れないよう、まわり 110km 四方 (玄界灘の島々、可也山、背振の山並み、壱岐まで) を
粗い 1 枚のメッシュにする。ランドスケープではなくスタティックメッシュ (Nanite) なので、エディタの読み込みも軽い。

apply_roads.py の後に実行する (ランドスケープの端の高さに合わせてつなぐため)。

使い方:
    python build_far_terrain.py areas/futamigaura.json

出力 (out/<エリア名>/far/):
    SM_FD_FarTerrain.gltf / .bin  遠景の地形 (UE に取り込む。色は頂点カラー)
    far_terrain.json              頂点数・三角形数など
    preview.png                   上から見た色 (上が北)。黒は省いた沖の海、赤い枠がランドスケープ

メッシュの作り方
- エリア中心から放射状に N_RAYS 本の線を引き、ランドスケープの端 (正方形) から外へ、同じ比率で間隔を広げながら頂点を置く。
  遠いほど粗くなるが、見かけの細かさ (角度) はどこでも同じ (約 0.56°)
- いちばん内側の輪はランドスケープの端とぴったり同じ高さにし、外へ 300m かけて遠景の標高データへなじませる。
  さらに 1 つ内側に、ランドスケープの下へもぐり込む輪を置いて、すき間が空かないようにする
- WaterZone (8km 四方) より外で、全部の頂点が海面より下の四角は省く (遠景の海の板に隠れて見えないため)
- 色は頂点カラー (リニアの値。M_FarTerrain はそのまま使う):
  斜面と高い所は森、平地は田畑と町、近くの海辺の低い所は砂、海底は濡れた砂

データ出典: 国土地理院 標高タイル (DEM10B、ズーム13 = 約16m)
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image

from build_terrain import (SEA_MAX_DEPTH_M, SEA_SHORE_DEPTH_M, SEA_SLOPE, box_blur_where, distance_to_land,
                           fill_holes_coarse, flood_from_border, load_mosaic, resample_to_grid,
                           upsample_nearest)
from geo import TOOLS_DIR, Area

MESH_NAME = "SM_FD_FarTerrain"
FAR_HALF_M = 55000.0        # 中心からこの距離 (正方形の半分) まで。夏至の夕日の方角 (西北西 45〜50km) の壱岐が全部入る
RASTER_M = 40.0             # 標高を並べ直す格子の間隔
DEM = ("dem10b", "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png", 13)
N_RAYS = 640                # 放射状の線の数 (8 の倍数。角がちょうど頂点になる)。見かけの細かさは約 0.56°
SEAM_OVERLAP_M = 30.0       # ランドスケープの下へもぐり込む輪の幅
SEAM_SINK_M = 2.0           # もぐり込む輪をランドスケープよりどれだけ下げるか
SEAM_BLEND_M = 300.0        # 端の高さから遠景の標高へなじませる距離
WATER_HALF_M = 4000.0       # setup_project.py の WaterZone (SEA_ZONE_EXTENT_CM) の半分。この内側は海底も見える
WATER_RECT_M = (-WATER_HALF_M, -WATER_HALF_M, WATER_HALF_M, WATER_HALF_M)   # 一周コースでは tiles.json の water_zone_m
NEAR_CELL_M = 48.0          # 一周コース: タイルのまわり (WaterZone の内側) の格子の間隔。タイルの端 (2016 + 4032n m) に合う
SEA_CULL_Z_M = -0.6         # 遠景の海の板 (海面 -0.5m) より下の四角は省く

# 色 (リニア)。ランドスケープと木の色に合わせて、遠くでかすんでも緑が残る程度に濃くする
FOREST = (0.030, 0.058, 0.022)
FOREST_DARK = (0.020, 0.042, 0.017)   # スギの植林や松の多い所
PADDY = (0.045, 0.075, 0.026)          # 夏の田 (setup_project.py の GRASS_COLOR に合わせる)
TOWN = (0.090, 0.088, 0.080)            # 町 (屋根と道路が混じった灰色)
SAND = (0.62, 0.52, 0.36)
SEABED = (0.30, 0.25, 0.18)
SEABED_DEEP = (0.025, 0.035, 0.040)   # 深い海底。明るい砂のままだと沖の浅い水が白く光り、遠景の海の板 (紺) との境が目立つ
SEA_BLOCK_LAND_M = 2.0                # 海と判定したブロックの中では、これより低い画素も海にする
SEA_FLAT_M = 1.0                      # 標高データでこれより低い所 (干潟や湾の中。海面と同じ高さの値が入っている) は海の候補にする
BEACH_M = 120.0                       # 海からこの距離までの低い所を砂浜にする (内陸の低い田を砂にしないため)


# ---------------------------------------------------------------- 標高
def far_area(path):
    area = Area(path)
    area.size_px = int(round(2 * FAR_HALF_M / RASTER_M)) + 1
    area.meters_per_px = RASTER_M
    return area


def load_raster(area):
    """遠景の標高 (m) と砂浜の重み (0..1) を RASTER_M 間隔の格子で返す。row 0 が北端。
    海は build_terrain.py と同じ傾斜の海底にする。"""
    name, url, zoom = DEM
    mosaic, ox, oy = load_mosaic(area, name, url, zoom)
    h = resample_to_grid(area, mosaic, ox, oy, zoom).astype(np.float64)
    nan = np.isnan(h)
    if nan.all():
        sys.exit("標高データが1画素もありません。")
    print(f"[{name}] 有効画素 {1 - nan.mean():.1%}")

    # 海の判定。データなしの画素に加え、海面とほぼ同じ高さ (干潟や湾の中) の画素も海の候補にする。
    # 湾の中は 0.4m と 0.6m のような値がまだらに入っていることがあるので、粗いブロックの過半数で決める
    low = nan | (h < SEA_FLAT_M)
    k = 4
    hh, ww = low.shape[0] // k, low.shape[1] // k
    coarse_low = low[:hh * k, :ww * k].reshape(hh, k, ww, k).mean(axis=(1, 3)) >= 0.5
    coarse_sea = upsample_nearest(flood_from_border(coarse_low), k, low.shape)
    near_sea = box_blur_where(coarse_sea.astype(np.float64), np.ones(low.shape, dtype=bool), radius=k) > 0.0
    sea = (near_sea & low) | (coarse_sea & (nan | (h < SEA_BLOCK_LAND_M)))
    holes = nan & ~sea
    if holes.any():
        print(f"内陸の欠損 {np.count_nonzero(holes)} 画素を周囲の値で補間")
        h = fill_holes_coarse(h, holes, k)
    max_d = (SEA_MAX_DEPTH_M - SEA_SHORE_DEPTH_M) / SEA_SLOPE
    dist = distance_to_land(sea, RASTER_M, max_d)
    h[sea] = -np.minimum(SEA_SHORE_DEPTH_M + dist[sea] * SEA_SLOPE, SEA_MAX_DEPTH_M)
    h = box_blur_where(h, sea, radius=1)
    h[sea] = np.minimum(h[sea], -0.5 * SEA_SHORE_DEPTH_M)
    to_sea = distance_to_land(~sea, RASTER_M, BEACH_M)  # 陸の画素から海までの距離
    beach = np.where(sea, 1.0, np.clip(1.0 - to_sea / BEACH_M, 0.0, 1.0))
    return h.astype(np.float32), beach.astype(np.float32)


def bilinear(grid, col, row):
    hgt, wid = grid.shape
    col = np.clip(col, 0, wid - 1.001)
    row = np.clip(row, 0, hgt - 1.001)
    c0 = np.floor(col).astype(np.int64)
    r0 = np.floor(row).astype(np.int64)
    tc, tr = col - c0, row - r0
    return (grid[r0, c0] * (1 - tc) * (1 - tr) + grid[r0, c0 + 1] * tc * (1 - tr)
            + grid[r0 + 1, c0] * (1 - tc) * tr + grid[r0 + 1, c0 + 1] * tc * tr)


class Grid:
    """UE の座標 (m、X = 東, Y = 南) で引ける標高の格子。格子の中心が原点、row 0 が北端 (Y が最小)。"""

    def __init__(self, values, cell_m):
        self.values = values
        self.cell = cell_m
        self.half = (values.shape[0] - 1) * cell_m / 2.0

    def __call__(self, x, y):
        return bilinear(self.values, (x + self.half) / self.cell, (y + self.half) / self.cell)


def load_landscape(area):
    """取り込んだランドスケープと同じ高さ (heightmap.r16 と landscape_import.json の Z スケール)。"""
    out = area.out_dir
    with open(os.path.join(out, "landscape_import.json"), encoding="utf-8") as f:
        params = json.load(f)
    n = area.size_px
    raw = np.fromfile(os.path.join(out, "heightmap.r16"), dtype="<u2").reshape(n, n)
    z_scale = params["scale"][2]
    height_m = (raw.astype(np.float64) - 32768.0) * z_scale / 128.0 / 100.0
    return Grid(height_m, area.meters_per_px)


# ---------------------------------------------------------------- メッシュ
def value_noise(x, y, scale_m, seed):
    """なめらかな 0..1 のノイズ (numpy.random を使わない)。"""
    gx, gy = x / scale_m, y / scale_m
    ix, iy = np.floor(gx), np.floor(gy)
    fx, fy = gx - ix, gy - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def h(a, b):
        v = np.sin(a * 127.1 + b * 311.7 + seed * 74.7) * 43758.5453
        return v - np.floor(v)

    return (h(ix, iy) * (1 - fx) * (1 - fy) + h(ix + 1, iy) * fx * (1 - fy)
            + h(ix, iy + 1) * (1 - fx) * fy + h(ix + 1, iy + 1) * fx * fy)


def smoothstep(e0, e1, v):
    t = np.clip((v - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return np.asarray(a) * (1 - t[:, None]) + np.asarray(b) * t[:, None]


def in_water(x, y, margin=0.0):
    """WaterZone (setup_project.py が置く海の範囲。UE の m) の内側か。"""
    x0, y0, x1, y1 = WATER_RECT_M
    return (x >= x0 - margin) & (x <= x1 + margin) & (y >= y0 - margin) & (y <= y1 + margin)


def vertex_colors(x, y, z, slope_deg, beach):
    n1 = value_noise(x, y, 900.0, 1)
    n2 = value_noise(x, y, 3000.0, 2)
    low = mix(PADDY, TOWN, smoothstep(0.62, 0.8, n2) * (1 - smoothstep(20.0, 40.0, z)))
    forest = mix(FOREST, FOREST_DARK, smoothstep(0.45, 0.75, n1))
    forest_w = np.maximum(smoothstep(4.0, 10.0, slope_deg), smoothstep(60.0, 120.0, z))
    c = mix(low, forest, forest_w)
    c *= (0.85 + 0.3 * value_noise(x, y, 400.0, 3))[:, None]
    # 浜は近くだけ (遠くの粗い四角で砂色を引き伸ばすと、海岸が帯のように白くなる)
    near = in_water(x, y, 2000.0)
    c = mix(c, SAND, smoothstep(3.0, 1.8, z) * beach * near)
    seabed = mix(SEABED, SEABED_DEEP, smoothstep(-2.0, -12.0, z))
    c = mix(c, seabed, smoothstep(-0.2, -1.0, z))
    return c.astype(np.float32)


def square_seam(e, n_rays):
    """中心から正方形 (半分の幅 e) の端までの点 (N, 2)。"""
    theta = np.arange(n_rays) * (2 * math.pi / n_rays)
    cos, sin = np.cos(theta), np.sin(theta)
    reach = e / np.maximum(np.abs(cos), np.abs(sin))
    return np.stack([cos * reach, sin * reach], 1)


def build_mesh(raster, land, base, center=(0.0, 0.0)):
    """頂点 (UE の m)、三角形、頂点カラーを返す。raster と land は Grid (land は端の高さ)。
    base は center から見たランドスケープの端の点 (N, 2)。中心から外へ、端の形を拡大した輪を重ねる。"""
    cx, cy = center
    reach = np.linalg.norm(base, axis=1)                    # 中心から端まで
    e = float(reach.min())
    far = FAR_HALF_M + max(abs(cx), abs(cy))
    n_rings = int(math.ceil(math.log(far / e) / math.log(1 + 2 * math.pi / N_RAYS)))
    g = (far / e) ** (1.0 / n_rings)
    scales = np.concatenate([[1.0 - SEAM_OVERLAP_M / reach.max()], [1.0], g ** np.arange(1, n_rings + 1)])
    pts = base[None, :, :] * scales[:, None, None]          # (R, N, 2)
    pts[0] = base * ((reach - SEAM_OVERLAP_M) / reach)[:, None]   # 内側の輪はどの向きも端から SEAM_OVERLAP_M 内側
    x, y = pts[..., 0] + cx, pts[..., 1] + cy
    bx, by = base[:, 0] + cx, base[:, 1] + cy

    z = raster(x, y)
    edge_land = land(bx, by)
    offset = edge_land - raster(bx, by)
    beyond = (scales[:, None] - 1.0) * reach[None, :]       # 端から外への距離 (m)
    z = z + offset[None, :] * np.clip(1.0 - beyond / SEAM_BLEND_M, 0.0, 1.0)
    z[1] = edge_land                                         # 端の輪はランドスケープと同じ高さ
    z[0] = land(x[0], y[0]) - SEAM_SINK_M                    # 内側の輪はランドスケープの下
    keep = (np.abs(x) <= FAR_HALF_M) & (np.abs(y) <= FAR_HALF_M)
    x, y = np.clip(x, -FAR_HALF_M, FAR_HALF_M), np.clip(y, -FAR_HALF_M, FAR_HALF_M)
    N_RAYS_ = base.shape[0]

    rings = len(scales)
    idx = np.arange(rings * N_RAYS_).reshape(rings, N_RAYS_)
    a = idx[:-1, :]
    b = np.roll(idx, -1, axis=1)[:-1, :]
    c = np.roll(idx, -1, axis=1)[1:, :]
    d = idx[1:, :]
    quads = np.stack([a, b, c, d], -1).reshape(-1, 4)

    zf, xf, yf = z.ravel(), x.ravel(), y.ravel()
    # 遠景の範囲 (FAR_HALF_M 四方) の外へはみ出す四角と、WaterZone の外の海だけの四角は省く
    outside = ~keep.ravel()
    hidden = ((zf[quads] < SEA_CULL_Z_M).all(1) & (~in_water(xf, yf))[quads].all(1)) | outside[quads].all(1)
    quads = quads[~hidden]
    tris = np.concatenate([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]])

    used = np.unique(tris)
    remap = np.full(len(zf), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    tris = remap[tris]
    verts = np.stack([xf[used], yf[used], zf[used]], 1)
    return verts, tris, int(hidden.sum()), rings


def to_gltf(verts):
    return verts[:, [0, 2, 1]]


def finish(verts, tris):
    """glTF の座標で、面を上向きにそろえ、頂点法線と斜面の角度を求める。"""
    p = to_gltf(verts)
    fn = np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]])
    flip = fn[:, 1] < 0
    tris[flip] = tris[flip][:, ::-1]
    fn[flip] *= -1
    nrm = np.zeros_like(p)
    for k in range(3):
        np.add.at(nrm, tris[:, k], fn)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    slope = np.degrees(np.arccos(np.clip(nrm[:, 1], -1.0, 1.0)))
    return p.astype(np.float32), nrm.astype(np.float32), tris.astype(np.uint32), slope


def write_gltf(folder, pos, nrm, col, tris):
    bin_name = f"{MESH_NAME}.bin"
    blob = bytearray()
    views, accessors = [], []

    def add(arr, target, typ, comp):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": arr.nbytes, "target": target})
        blob.extend(arr.tobytes())
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr), "type": typ}
        accessors.append(acc)
        return len(accessors) - 1, acc

    i_pos, acc = add(pos, 34962, "VEC3", 5126)
    acc["min"], acc["max"] = pos.min(0).tolist(), pos.max(0).tolist()
    i_nrm, _ = add(nrm, 34962, "VEC3", 5126)
    i_col, _ = add(col, 34962, "VEC3", 5126)
    i_idx, _ = add(tris.ravel(), 34963, "SCALAR", 5125)
    doc = {
        "asset": {"version": "2.0", "generator": "fukuoka_drive tools/terrain/build_far_terrain.py"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": MESH_NAME, "mesh": 0}],
        "meshes": [{"name": MESH_NAME, "primitives": [{
            "attributes": {"POSITION": i_pos, "NORMAL": i_nrm, "COLOR_0": i_col},
            "indices": i_idx, "material": 0}]}],
        "materials": [{"name": "FD_FarTerrain",
                       "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0,
                                                "roughnessFactor": 0.9}}],
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(blob), "uri": bin_name}],
    }
    with open(os.path.join(folder, bin_name), "wb") as f:
        f.write(blob)
    with open(os.path.join(folder, f"{MESH_NAME}.gltf"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return len(blob)


def write_preview(folder, raster, verts, col, outline, size=900):
    """頂点カラーを上から見た画像 (省いた所は黒)。outline (UE の m の点の列) を赤で描く。"""
    img = np.zeros((size, size, 3), dtype=np.float64)
    cnt = np.zeros((size, size))
    to_px = lambda v: np.clip(((v + FAR_HALF_M) / (2 * FAR_HALF_M) * (size - 1)).astype(int), 0, size - 1)
    c, r = to_px(verts[:, 0]), to_px(verts[:, 1])
    np.add.at(img, (r, c), col)
    np.add.at(cnt, (r, c), 1)
    ok = cnt > 0
    img[ok] /= cnt[ok][:, None]
    # 頂点のない画素は、近くに頂点があればその色で埋める (遠くは頂点がまばらなため)
    for _ in range(12):
        if ok.all():
            break
        acc = np.zeros_like(img)
        n = np.zeros_like(cnt)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc += np.roll(np.roll(img * ok[..., None], dr, 0), dc, 1)
            n += np.roll(np.roll(ok, dr, 0), dc, 1)
        fill = ~ok & (n > 0)
        img[fill] = acc[fill] / n[fill][:, None]
        ok = ok | fill
    srgb = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(np.clip(img, 0, 1), 1 / 2.4) - 0.055)
    out = (np.clip(srgb, 0, 1) * 255).astype(np.uint8)
    out[to_px(outline[:, 1]), to_px(outline[:, 0])] = (220, 40, 40)
    Image.fromarray(out).save(os.path.join(folder, "preview.png"))


# ---------------------------------------------------------------- 一周コース (タイルを並べた形)
class Tiles:
    """一周コースのタイル (tiles.json)。UE の m で、どのタイルの中か・ランドスケープの高さを引ける。"""

    def __init__(self, loop_dir):
        with open(os.path.join(loop_dir, "tiles.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.size = float(doc["tile_size_m"])
        self.half = self.size / 2.0
        self.keys = [tuple(t["tile"]) for t in doc["tiles"]]
        self.water = doc["water_zone_m"]
        self.grids = {}
        for t in doc["tiles"]:
            area = Area(os.path.join(TOOLS_DIR, t["area"]))
            self.grids[tuple(t["tile"])] = load_landscape(area)

    def center(self, key):
        return key[0] * self.size, -key[1] * self.size     # UE の m (Y は南)

    def tile_at(self, x, y):
        i = np.floor((x + self.half) / self.size).astype(int)
        j = np.floor((-y + self.half) / self.size).astype(int)
        return i, j

    def inside(self, x, y):
        i, j = self.tile_at(np.asarray(x, float), np.asarray(y, float))
        out = np.zeros(i.shape, dtype=bool)
        for a, b in self.keys:
            out |= (i == a) & (j == b)
        return out

    def height(self, x, y):
        """ランドスケープの高さ。境目の点は、その点を含むタイルのどれか (境目の高さはそろえてある)。
        タイルの外の点は、いちばん近いタイルの端の高さ。"""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.full(x.shape, np.nan)
        best = np.full(x.shape, np.inf)
        for key, grid in self.grids.items():
            cx, cy = self.center(key)
            d = np.maximum(np.abs(x - cx), np.abs(y - cy)) - self.half
            take = d < best - 1e-6
            if take.any():
                out[take] = grid(x[take] - cx, y[take] - cy)
                best[take] = d[take]
        return out


def rect_seam(rect, n_rays):
    """長方形 rect (x0, y0, x1, y1) の中心から放射状に見た、長方形の端の点 (N, 2、中心からの向き) と中心。"""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    theta = np.arange(n_rays) * (2 * math.pi / n_rays)
    cos, sin = np.cos(theta), np.sin(theta)
    reach = 1.0 / np.maximum(np.abs(cos) / hx, np.abs(sin) / hy)
    return np.stack([cos * reach, sin * reach], 1), (cx, cy)


def near_grid(tiles, raster, rect):
    """タイルのまわり (rect の内側) を NEAR_CELL_M の格子にした頂点と三角形。タイルの内側は省き、
    タイルの端の頂点はランドスケープと同じ高さ、端から 1 マス内側の頂点はランドスケープの下に沈める。"""
    x0, y0, x1, y1 = rect
    xs = np.arange(x0, x1 + 0.5, NEAR_CELL_M)
    ys = np.arange(y0, y1 + 0.5, NEAR_CELL_M)
    X, Y = np.meshgrid(xs, ys)
    e = 1.0
    ins = lambda dx, dy: tiles.inside(X + dx, Y + dy)
    inside = ins(0, 0)
    corners = [ins(dx, dy) for dx in (-e, e) for dy in (-e, e)]
    interior = np.logical_and.reduce(corners)                  # まわりが全部タイル
    edge = np.logical_or.reduce(corners) & ~interior           # タイルを並べた形の端の上

    z = raster(X, Y)
    # 端から SEAM_BLEND_M かけて、端の高さとのずれを遠景の標高へなじませる
    dist = np.full(X.shape, np.inf)
    offset = np.zeros(X.shape)
    for key in tiles.keys:
        cx, cy = tiles.center(key)
        px = np.clip(X, cx - tiles.half, cx + tiles.half)
        py = np.clip(Y, cy - tiles.half, cy + tiles.half)
        d = np.hypot(X - px, Y - py)
        near = (d < dist) & (d < SEAM_BLEND_M)
        if near.any():
            offset[near] = tiles.height(px[near], py[near]) - raster(px[near], py[near])
        dist = np.minimum(dist, d)
    z = z + offset * np.clip(1.0 - dist / SEAM_BLEND_M, 0.0, 1.0)
    z[edge] = tiles.height(X[edge], Y[edge])
    z[interior] = tiles.height(X[interior], Y[interior]) - SEAM_SINK_M

    # マスは、頂点のどれかがタイルの外か端にあるものだけ残す (タイルの中の 1 マス幅の帯はランドスケープの下)
    keep_v = ~interior
    ny, nx = X.shape
    idx = np.arange(nx * ny).reshape(ny, nx)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    kv = keep_v.ravel()
    quads = np.stack([a, b, c, d], -1).reshape(-1, 4)
    quads = quads[kv[quads].any(1)]
    verts = np.stack([X.ravel(), Y.ravel(), z.ravel()], 1)
    return verts, quads


def tile_outline(tiles, key, step=20.0):
    cx, cy = tiles.center(key)
    h = tiles.half
    t = np.arange(-h, h, step)
    return np.concatenate([np.stack([cx + t, cy - h + 0 * t], 1), np.stack([cx + h + 0 * t, cy + t], 1),
                           np.stack([cx - t, cy + h + 0 * t], 1), np.stack([cx - h + 0 * t, cy - t], 1)])


def build_loop_mesh(tiles, raster):
    """タイルのまわりの格子 + その外の放射状の輪 (長方形の端から外へ)。"""
    c = NEAR_CELL_M
    x0, y0, x1, y1 = tiles.water
    rect = (math.floor(x0 / c) * c, math.floor(y0 / c) * c, math.ceil(x1 / c) * c, math.ceil(y1 / c) * c)
    gv, gq = near_grid(tiles, raster, rect)
    base, center = rect_seam(rect, N_RAYS)
    flat = lambda x, y: raster(x, y)
    rv, rt, culled, rings = build_mesh(raster, flat, base, center)
    # 放射状のメッシュは三角形で返るので、2 つで 1 つの四角に戻さずにそのまま足す
    verts = np.concatenate([gv, rv])
    tris = np.concatenate([np.concatenate([gq[:, [0, 1, 2]], gq[:, [0, 2, 3]]]), rt + len(gv)])
    used = np.unique(tris)
    remap = np.full(len(verts), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[tris], culled, rings, rect


# ---------------------------------------------------------------- まとめ
def build(out_dir, raster, land, beach, base, center, outline, tiles=None):
    folder = os.path.join(out_dir, "far")
    os.makedirs(folder, exist_ok=True)
    if tiles is not None:
        verts, tris, culled, rings, rect = build_loop_mesh(tiles, raster)
        x0, y0, x1, y1 = rect
        outline = np.array([(x, y) for k in tiles.keys for x, y in tile_outline(tiles, k)])
        center = ((x0 + x1) / 2, (y0 + y1) / 2)
        base = np.zeros((N_RAYS, 2))
    else:
        verts, tris, culled, rings = build_mesh(raster, land, base, center)
    pos, nrm, tris, slope = finish(verts, tris)
    col = vertex_colors(verts[:, 0], verts[:, 1], verts[:, 2], slope, beach(verts[:, 0], verts[:, 1]))
    nbytes = write_gltf(folder, pos, nrm, col, tris)
    write_preview(folder, raster, verts, col, outline)
    info = {
        "mesh": f"{MESH_NAME}.gltf", "half_m": FAR_HALF_M, "center_m": list(center), "rays": int(len(base)),
        "rings": rings, "vertices": int(len(pos)), "triangles": int(len(tris)), "culled_sea_quads": culled,
        "gltf_bytes": nbytes, "height_max_m": round(float(pos[:, 1].max()), 1),
    }
    with open(os.path.join(folder, "far_terrain.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"出力先: {folder}")
    return info


def main():
    global WATER_RECT_M
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    far = far_area(sys.argv[1])
    height, beach = load_raster(far)
    raster, beach = Grid(height, RASTER_M), Grid(beach, RASTER_M)
    if os.path.exists(os.path.join(area.out_dir, "tiles.json")):
        # 一周コース: タイルを並べた形の外側
        tiles = Tiles(area.out_dir)
        WATER_RECT_M = tuple(tiles.water)
        print(f"タイル {len(tiles.keys)} 枚の外側")
        build(area.out_dir, raster, None, beach, None, None, None, tiles=tiles)
    else:
        land = load_landscape(area)
        base = square_seam(area.half_m, N_RAYS)
        build(area.out_dir, raster, land, beach, base, (0.0, 0.0), base)


if __name__ == "__main__":
    main()
