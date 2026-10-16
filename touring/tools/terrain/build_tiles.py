"""コースのタイルをまとめて作る。build_loop.py の後に実行する。

使い方:
    python build_tiles.py areas/itoshima_loop.json            すべてのタイル
    python build_tiles.py areas/itoshima_loop.json -1,0 0,-1  指定したタイルだけ (境目のそろえ直しは全タイルで行う)
    python build_tiles.py areas/itoshima_loop.json --stitch   境目のそろえ直しだけ
    python build_tiles.py areas/itoshima_loop.json --scenery  景観物 (build_scenery.py) と海岸の絵だけ作り直す
    python build_tiles.py areas/itoshima_loop.json --coast    海岸の絵 (build_coast.py) だけ作り直す

手順:
    1. out/<コース名>/loop_route.json の tiles から、タイルごとのエリア設定 areas/<コース>/<名前>.json を作る
       (名前と置き場は course.py。糸島一周はタイル (0, 0) が最初の区間 areas/futamigaura.json そのもの)
    2. タイルごとに build_terrain.py → build_roads.py → apply_roads.py
    3. 隣り合うタイルの境目の高さを、境目を共有するタイルの平均にそろえ、内側へなめらかにつなぐ (stitch)
    4. タイルごとに build_scenery.py と build_coast.py (砂浜にしてよい所の絵)

一周の全タイルの一覧と UE での置き場所は out/<一周の名前>/tiles.json に書く (setup_project.py が読む)。
"""

import json
import os
import subprocess
import sys

import numpy as np

from build_terrain import write_outputs
from course import Course
from geo import TOOLS_DIR, Area

WATER_MARGIN_M = 2000.0    # WaterZone (海の範囲) はタイルを並べた範囲よりこれだけ広く取る
STITCH_FEATHER_PX = 64     # 境目の高さの差を、内側へこの画素数かけて 0 にする
PER_TILE = ("build_terrain.py", "build_roads.py", "apply_roads.py")
AFTER_STITCH = ("build_scenery.py", "build_coast.py")


def run(script, area_path):
    print(f"\n=== {script} {os.path.relpath(area_path, TOOLS_DIR)}", flush=True)
    subprocess.run([sys.executable, os.path.join(TOOLS_DIR, script), area_path], cwd=TOOLS_DIR, check=True)


def stitch(areas):
    """境目の画素の高さを、その画素を持つタイルすべての平均にする。差は内側へ STITCH_FEATHER_PX かけて薄める。"""
    heights, sum_, cnt = {}, {}, {}
    for (i, j), area in areas.items():
        path = os.path.join(area.out_dir, "height_road_m.npy")
        if not os.path.exists(path):
            print(f"  {area.name}: height_road_m.npy が無いので境目をそろえません")
            continue
        h = np.load(path).astype(np.float64)
        heights[(i, j)] = h
        n = h.shape[0] - 1
        for r, c in edge_pixels(n):
            key = (i * n + c, -j * n + r)   # 全体で共通の画素番号 (東 +、南 +)
            sum_[key] = sum_.get(key, 0.0) + h[r, c]
            cnt[key] = cnt.get(key, 0) + 1
    worst = 0.0
    for (i, j), h in heights.items():
        area = areas[(i, j)]
        n = h.shape[0] - 1
        target = lambda r, c: sum_[(i * n + c, -j * n + r)] / cnt[(i * n + c, -j * n + r)]
        before = h.copy()
        f = STITCH_FEATHER_PX
        ramp = 1.0 - np.arange(f) / f
        # 上下の辺 (行方向にぼかす) → 左右の辺 (列方向)。角は先に上下の辺で目標の値になる
        for row, step in ((0, 1), (n, -1)):
            delta = np.array([target(row, c) for c in range(n + 1)]) - h[row]
            for k in range(f):
                h[row + step * k] += delta * ramp[k]
        for col, step in ((0, 1), (n, -1)):
            delta = np.array([target(r, col) for r in range(n + 1)]) - h[:, col]
            for k in range(f):
                h[:, col + step * k] += delta * ramp[k]
        change = float(np.max(np.abs(h - before)))
        worst = max(worst, change)
        if change > 0.001:
            sea = np.load(os.path.join(area.out_dir, "sea_mask.npy"))
            write_outputs(area, h.astype(np.float32), sea, height_file="height_road_m.npy")
        print(f"  {area.name}: 境目の高さを最大 {change * 100:.1f} cm 直しました")
    print(f"境目のそろえ直し: 最大 {worst * 100:.1f} cm")


def edge_pixels(n):
    for c in range(n + 1):
        yield 0, c
        yield n, c
    for r in range(1, n):
        yield r, 0
        yield r, n


def has_sea(course, areas):
    """海を置くか。コースの設定の "sea" が "none" なら置かない。"auto" (既定) ならどれかのタイルに海があれば置く
    (地形をまだ作っていないタイルは海があるものとみなす)。"""
    if course.cfg.get("sea", "auto") == "none":
        return False
    for area in areas.values():
        path = os.path.join(area.out_dir, "sea_mask.npy")
        if not os.path.exists(path) or np.load(path).any():
            return True
    return False


def write_tiles_json(course, loop, areas, base_tile):
    cfg = course.cfg
    tiles = []
    for (i, j), area in sorted(areas.items()):
        tiles.append({"tile": [i, j], "name": area.name,
                      "area": os.path.relpath(course.tile_area_path(i, j), TOOLS_DIR).replace(os.sep, "/"),
                      "center_lat": round(area.center_lat, 7), "center_lon": round(area.center_lon, 7),
                      "offset_cm": area.ue_offset_cm})
    size = (cfg["tile_size_px"] - 1) * cfg["meters_per_px"]
    xs = [t["offset_cm"][0] / 100 for t in tiles]
    ys = [t["offset_cm"][1] / 100 for t in tiles]
    m = size / 2 + WATER_MARGIN_M
    out = {"name": loop.name, "map": course.map, "base_tile": base_tile, "loop": course.loop,
           "sea": has_sea(course, areas),
           "tile_size_m": size,
           "axes": "UE: +X 東, +Y 南。タイルのデータはタイルの中心が原点なので、offset_cm だけずらして置く",
           # 海 (WaterZone) の範囲 [x0, y0, x1, y1] (UE の m)。setup_project.py と build_far_terrain.py が使う
           "water_zone_m": [min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m],
           "tiles": tiles}
    path = os.path.join(loop.out_dir, "tiles.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"タイルの一覧: {path}")


def start_tile(route, tiles):
    """コースの最初の点があるタイル (共通のアセットはこのタイルのデータで作る)。原点のタイルがあればそれ。"""
    if (0, 0) in tiles:
        return (0, 0)
    size = route["tile_size_m"]
    p = route["points"][0]
    t = (round(p["x_m"] / size), round(p["y_m"] / size))
    return t if t in tiles else tiles[0]


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    loop_path = args[0]
    loop = Area(loop_path)
    course = Course(loop_path)
    route_path = os.path.join(loop.out_dir, "loop_route.json")
    if not os.path.exists(route_path):
        sys.exit("loop_route.json がありません。先に build_loop.py を実行してください。")
    with open(route_path, encoding="utf-8") as f:
        route = json.load(f)
    all_tiles = [tuple(t) for t in route["tiles"]]
    areas = {t: Area(course.tile_area_path(*t)) for t in all_tiles}
    write_tiles_json(course, loop, areas, areas[start_tile(route, all_tiles)].name)

    stitch_only = "--stitch" in args
    scenery_only = "--scenery" in args
    coast_only = "--coast" in args
    picked = [tuple(int(v) for v in a.split(",")) for a in args[1:] if not a.startswith("--")]
    todo = picked or all_tiles
    for t in todo:
        if t not in areas:
            sys.exit(f"タイル {t} は一周コースにかかっていません ({all_tiles})")
    if not stitch_only and not scenery_only and not coast_only:
        for t in todo:
            for script in PER_TILE:
                run(script, course.tile_area_path(*t))
    if not scenery_only and not coast_only:
        print("\n=== 境目のそろえ直し")
        stitch(areas)
    if not stitch_only:
        for t in todo:
            for script in (("build_coast.py",) if coast_only else AFTER_STITCH):
                run(script, course.tile_area_path(*t))
    write_tiles_json(course, loop, areas, areas[start_tile(route, all_tiles)].name)   # 海があるかは地形を作った後に決まる
    print("\nタイルの作成が終わりました")


if __name__ == "__main__":
    main()
