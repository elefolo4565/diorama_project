"""ミニマップの地図の画像 (上から見た地図、北が上) を作る。

    python build_minimap.py areas/futamigaura.json
    python build_minimap.py areas/itoshima_loop.json   一周コース (build_tiles.py の後)。全タイルを 1 枚の地図にする

入力 (apply_roads.py までの出力)
    height_road_m.npy (なければ height_m.npy), sea_mask.npy, roads.json
出力
    minimap.png   2048 x 2048。範囲はランドスケープと同じ (UE の X, Y とも -201600 〜 +201600 cm)。
                  左が西、上が北 (UE の +X が右、+Y が下)。setup_project.py が /Game/FukuokaDrive/UI/T_FD_Minimap に取り込む

地図の描き方
- 海は青 (浅い所ほど明るい)、砂浜 (海面 +2.2m より低い陸) は砂色、陸は標高で緑から黄土色へ
- 北西から光を当てた陰影 (山の形がわかるように)
- 道路は roads.json の線を、地図で見えるよう実際より太く描く。県道などの主要道路は黄色、それ以外は白
- 線路 (railways.json があれば) は黒と白のしま、駅は赤い四角。トンネルの中は描かない
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from geo import TOOLS_DIR, Area

OUT_PX = 2048
LOOP_OUT_PX = 8192       # 一周コースの地図 (約 20km 四方、1px = 約 2.5m)
SUPERSAMPLE = 2          # 道路の線をなめらかにするため、倍の大きさで描いてから縮める

SEA_DEEP = np.array([38, 92, 140], np.float32)
SEA_SHALLOW = np.array([86, 168, 190], np.float32)
SHALLOW_DEPTH_M = 6.0
SAND = np.array([226, 211, 166], np.float32)
SAND_TOP_M = 2.2         # setup_project.py の SAND_DRY_TOP_CM と同じ
LAND_LOW = np.array([150, 190, 120], np.float32)
LAND_HIGH = np.array([118, 140, 86], np.float32)
LAND_TOP_M = 250.0
SUN_AZIMUTH_DEG = 315.0  # 北西から
SUN_ALTITUDE_DEG = 40.0
SHADE_STRENGTH = 0.55

# (幅 m, 縁の幅 m, 色, 縁の色)。主要道路 (優先度 0-1)、県道・市道 (2)、生活道路 (3)、私道・農道 (4-)
ROAD_STYLES = {
    1: (16.0, 3.0, (255, 206, 84), (120, 90, 30)),
    2: (11.0, 2.5, (255, 255, 255), (110, 110, 110)),
    3: (7.0, 2.0, (250, 250, 250), (130, 130, 130)),
    4: (4.5, 1.5, (235, 235, 225), (140, 140, 140)),
}


def hillshade(height, m_per_px):
    gy, gx = np.gradient(height.astype(np.float32), m_per_px)
    # 画素の row は南向きなので、北向きの勾配は -gy
    nx, ny, nz = -gx, gy, np.ones_like(gx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    az = np.radians(SUN_AZIMUTH_DEG)
    alt = np.radians(SUN_ALTITUDE_DEG)
    # 光の来る向き (東 = +x, 北 = +y)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    shade = (nx * lx + ny * ly + nz * lz) / norm
    flat = lz
    return np.clip(shade / flat, 0.0, 1.6)


def base_colors(height, sea, m_per_px):
    h = height.astype(np.float32)
    rgb = np.empty(h.shape + (3,), np.float32)

    t = np.clip(h / LAND_TOP_M, 0.0, 1.0)[..., None]
    land = LAND_LOW * (1 - t) + LAND_HIGH * t
    shade = hillshade(h, m_per_px)[..., None]
    land = land * (1.0 - SHADE_STRENGTH + SHADE_STRENGTH * shade)
    rgb[:] = land

    sand = (~sea) & (h < SAND_TOP_M)
    rgb[sand] = SAND

    water = sea | (h < 0.0)
    d = np.clip(-h / SHALLOW_DEPTH_M, 0.0, 1.0)[..., None]
    sea_rgb = SEA_SHALLOW * (1 - d) + SEA_DEEP * d
    rgb[water] = sea_rgb[water]
    return np.clip(rgb, 0, 255).astype(np.uint8)


def draw_roads(img, roads, area_half_cm, px):
    draw = ImageDraw.Draw(img)
    scale = px / (2.0 * area_half_cm)
    m_to_px = 100.0 * scale

    def style(r):
        return ROAD_STYLES[min(max(r["priority"], 1), 4)]

    def to_px(p):
        return ((p[0] + area_half_cm) * scale, (p[1] + area_half_cm) * scale)

    order = sorted(roads, key=lambda r: -r["priority"])   # 主要道路を最後 (上) に
    for outline in (True, False):
        for r in order:
            width, edge, fill, edge_color = style(r)
            pts = [to_px(p) for p in r["points_cm"]]
            if len(pts) < 2:
                continue
            w = width + 2 * edge if outline else width
            w_px = max(1, int(round(w * m_to_px)))
            draw.line(pts, fill=edge_color if outline else fill, width=w_px, joint="curve")
            # 線の端を丸める (PIL の線は端が四角いので、交差点にすき間ができる)
            for x, y in (pts[0], pts[-1]):
                rad = w_px / 2.0
                draw.ellipse((x - rad, y - rad, x + rad, y + rad), fill=edge_color if outline else fill)


RAIL_W_M, RAIL_EDGE_M, RAIL_DASH_M = 7.0, 2.0, 40.0
STATION_M = 26.0


def load_rails(out_dir, dx_cm=0.0, dy_cm=0.0):
    """(地上の線路の点列 [[x, y] cm], 駅の位置 [[x, y] cm])。railways.json が無ければ空。"""
    path = os.path.join(out_dir, "railways.json")
    if not os.path.exists(path):
        return [], []
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    runs = []
    for line in doc["lines"]:
        cur = []
        for p, k in zip(line["points_cm"], line["kind"]):
            if k == 2:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = []
            else:
                cur.append([p[0] + dx_cm, p[1] + dy_cm])
        if len(cur) >= 2:
            runs.append(cur)
    stations = [[s["pos_m"][0] * 100 + dx_cm, s["pos_m"][1] * 100 + dy_cm] for s in doc.get("stations", [])]
    return runs, stations


def draw_rails(img, runs, stations, area_half_cm, px):
    """線路 (黒い縁に白と黒のしま) と駅 (赤い四角)。"""
    if not runs and not stations:
        return
    draw = ImageDraw.Draw(img)
    scale = px / (2.0 * area_half_cm)
    m_to_px = 100.0 * scale

    def to_px(p):
        return ((p[0] + area_half_cm) * scale, (p[1] + area_half_cm) * scale)

    w = max(1, int(round(RAIL_W_M * m_to_px)))
    for run in runs:
        pts = [to_px(p) for p in run]
        draw.line(pts, fill=(60, 60, 60), width=w + max(1, int(round(2 * RAIL_EDGE_M * m_to_px))), joint="curve")
    for run in runs:
        pts = [to_px(p) for p in run]
        draw.line(pts, fill=(255, 255, 255), width=w, joint="curve")
        # 黒のしま: 道に沿って RAIL_DASH_M ごとに半分を塗る
        acc, on = 0.0, False
        for a, b in zip(run[:-1], run[1:]):
            seg = math.hypot(b[0] - a[0], b[1] - a[1]) / 100.0
            if on:
                draw.line([to_px(a), to_px(b)], fill=(60, 60, 60), width=w)
            acc += seg
            if acc >= RAIL_DASH_M:
                acc, on = 0.0, not on
    r = max(2, STATION_M * m_to_px / 2)
    for x, y in (to_px(p) for p in stations):
        draw.rectangle((x - r, y - r, x + r, y + r), fill=(220, 40, 40), outline=(255, 255, 255), width=max(1, int(r / 4)))


def loop_map(loop_path, area):
    """一周コース: タイルを並べた範囲を囲む正方形の地図。タイルの外は遠景の標高 (40m) で描く。"""
    from build_far_terrain import RASTER_M, far_area, load_raster
    with open(os.path.join(area.out_dir, "tiles.json"), encoding="utf-8") as f:
        doc = json.load(f)
    size, half = doc["tile_size_m"], doc["tile_size_m"] / 2
    xs = [t["offset_cm"][0] / 100 for t in doc["tiles"]]
    ys = [t["offset_cm"][1] / 100 for t in doc["tiles"]]
    side = max(max(xs) - min(xs), max(ys) - min(ys)) + size
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    x0, y0 = cx - side / 2, cy - side / 2           # 地図の北西の角 (UE の m)
    px_m = side / LOOP_OUT_PX

    # タイルの外: 遠景の標高を地図の画素へ並べ直す
    height, _ = load_raster(far_area(loop_path))
    n = height.shape[0]
    far_half = (n - 1) * RASTER_M / 2
    g = np.arange(LOOP_OUT_PX) * px_m + px_m / 2
    col = np.clip((x0 + g + far_half) / RASTER_M, 0, n - 1.001)
    row = np.clip((y0 + g + far_half) / RASTER_M, 0, n - 1.001)
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    tc, tr = (col - c0)[None, :], (row - r0)[:, None]
    hgt = (height[np.ix_(r0, c0)] * (1 - tc) * (1 - tr) + height[np.ix_(r0, c0 + 1)] * tc * (1 - tr)
           + height[np.ix_(r0 + 1, c0)] * (1 - tc) * tr + height[np.ix_(r0 + 1, c0 + 1)] * tc * tr)
    img = Image.fromarray(base_colors(hgt, hgt < 0, px_m))

    # タイル: ランドスケープと同じ高さで描いて貼る
    tile_px = int(round(size / px_m))
    roads, rails, stations = [], [], []
    for t, tx, ty in zip(doc["tiles"], xs, ys):
        out = os.path.join(TOOLS_DIR, "out", t["name"])
        hp = os.path.join(out, "height_road_m.npy")
        h = np.load(hp if os.path.exists(hp) else os.path.join(out, "height_m.npy"))
        sea = np.load(os.path.join(out, "sea_mask.npy"))
        tile = Image.fromarray(base_colors(h, sea, 1.0)).resize((tile_px, tile_px), Image.LANCZOS)
        img.paste(tile, (int(round((tx - half - x0) / px_m)), int(round((ty - half - y0) / px_m))))
        with open(os.path.join(out, "roads.json"), encoding="utf-8") as f:
            for r in json.load(f)["roads"]:
                r["points_cm"] = [[p[0] + tx * 100, p[1] + ty * 100] for p in r["points_cm"]]
                roads.append(r)
        ru, st = load_rails(out, tx * 100 - cx * 100, ty * 100 - cy * 100)
        rails += ru
        stations += st
    # draw_roads は中心が原点の正方形を描くので、地図の中心が原点になるようずらす
    for r in roads:
        r["points_cm"] = [[p[0] - cx * 100, p[1] - cy * 100] for p in r["points_cm"]]
    draw_roads(img, roads, side / 2 * 100.0, LOOP_OUT_PX)
    draw_rails(img, rails, stations, side / 2 * 100.0, LOOP_OUT_PX)
    path = os.path.join(area.out_dir, "minimap.png")
    img.save(path)
    bounds = {"world_min_cm": [x0 * 100, y0 * 100], "world_max_cm": [(x0 + side) * 100, (y0 + side) * 100],
              "pixels": LOOP_OUT_PX,
              "note": "C++ の AFDBikePawn::MinimapWorldMin / MinimapWorldMax と同じ値にする"}
    with open(os.path.join(area.out_dir, "minimap.json"), "w", encoding="utf-8") as f:
        json.dump(bounds, f, ensure_ascii=False, indent=1)
    print(f"ミニマップの地図: {path} ({LOOP_OUT_PX} x {LOOP_OUT_PX}, 1px = {px_m:.2f} m)、範囲 {bounds}")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    out = area.out_dir
    if os.path.exists(os.path.join(out, "tiles.json")):
        loop_map(sys.argv[1], area)
        return
    height_path = os.path.join(out, "height_road_m.npy")
    if not os.path.exists(height_path):
        height_path = os.path.join(out, "height_m.npy")
    height = np.load(height_path)
    sea = np.load(os.path.join(out, "sea_mask.npy"))
    with open(os.path.join(out, "roads.json"), encoding="utf-8") as f:
        roads = json.load(f)["roads"]

    big = OUT_PX * SUPERSAMPLE
    img = Image.fromarray(base_colors(height, sea, area.meters_per_px)).resize((big, big), Image.BILINEAR)
    draw_roads(img, roads, area.half_m * 100.0, big)
    draw_rails(img, *load_rails(out), area.half_m * 100.0, big)
    img = img.resize((OUT_PX, OUT_PX), Image.LANCZOS)
    path = os.path.join(out, "minimap.png")
    img.save(path)
    print(f"ミニマップの地図: {path} ({OUT_PX} x {OUT_PX}, 1px = {area.size_m / OUT_PX:.2f} m)")


if __name__ == "__main__":
    main()
