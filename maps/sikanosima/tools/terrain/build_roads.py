"""OpenStreetMap から道路と目印を取り出し、UE 座標 (cm) のポイント列にする。

先に build_terrain.py を実行しておくこと (道路の高さを地形から拾うため)。

使い方:
    python build_roads.py areas/futamigaura.json

出力 (out/<エリア名>/):
    osm_raw.json   Overpass API の生データ (エリア設定が同じなら再実行時はこれを使う)
    roads.json     道路ごとのポイント列 (UE 座標 cm)。UE へのスプライン取り込みに使う
    roads_margin.json  タイルの外側 ROAD_MARGIN_M まで続けた道路 (apply_roads.py が境目の先まで焼くため)
    landmarks.json 目印 (夫婦岩など) の UE 座標

データ出典: © OpenStreetMap contributors (ODbL)
"""

import json
import os
import sys

import numpy as np

from geo import Area, http_post_form

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

ROAD_CLASSES = {
    # highway タグ: (既定の幅 m, 優先度)
    "motorway": (7.0, 0), "trunk": (7.0, 0), "primary": (7.0, 1), "secondary": (6.5, 1),
    "tertiary": (6.0, 2), "unclassified": (4.5, 3), "residential": (4.0, 3),
    "motorway_link": (5.0, 1), "trunk_link": (5.0, 1), "primary_link": (5.0, 1),
    "secondary_link": (5.0, 2), "tertiary_link": (5.0, 2), "service": (3.5, 4), "track": (3.0, 5),
}

LANE_WIDTH_M = 3.0
ROAD_Z_OFFSET_M = 0.05
POINT_SPACING_M = 10.0
ROAD_MARGIN_M = 150.0   # 隣のタイルとの境目で路面の高さがそろうよう、道路はこれだけ外まで焼く


def overpass_query(area):
    s, w, n, e = area.bbox()
    b = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    s, w, n, e = area.bbox(margin_m=ROAD_MARGIN_M)
    bm = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    hw = "|".join(ROAD_CLASSES)
    return f"""
[out:json][timeout:180];
(
  way["highway"~"^({hw})$"]({bm});
  nwr["name"]["natural"~"^(rock|stone|cape|beach|peak|bay)$"]({b});
  nwr["name"]["tourism"~"^(attraction|viewpoint)$"]({b});
  nwr["name"]["historic"]({b});
  nwr["name"]["amenity"="place_of_worship"]({b});
  way["natural"="coastline"]({b});
);
out tags geom;
"""


def fetch_osm(area):
    path = os.path.join(area.out_dir, "osm_raw.json")
    query = overpass_query(area)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("_query") == query:
            print(f"保存済みの OSM データを使用: {path}")
            return data
    print("Overpass API から OSM データを取得中 ...")
    raw = http_post_form(OVERPASS_URL, {"data": query})
    data = json.loads(raw)
    data["_query"] = query  # エリア設定を変えたら取り直すため
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


class HeightSampler:
    """標高を引く。タイルの外側の余白 (height_margin_m.npy) があればそこまで引ける。"""

    def __init__(self, area):
        path = os.path.join(area.out_dir, "height_m.npy")
        if not os.path.exists(path):
            sys.exit("height_m.npy がありません。先に build_terrain.py を実行してください。")
        self.h = np.load(path)
        self.margin = 0
        wide = os.path.join(area.out_dir, "height_margin_m.npy")
        if os.path.exists(wide):
            self.h = np.load(wide)
            self.margin = (self.h.shape[0] - area.size_px) // 2
        self.area = area

    def __call__(self, x, y):
        col, row = self.area.local_to_pixel(x, y)
        col, row = col + self.margin, row + self.margin
        n = self.h.shape[0]
        c0 = int(np.clip(np.floor(col), 0, n - 2))
        r0 = int(np.clip(np.floor(row), 0, n - 2))
        tc, tr = col - c0, row - r0
        tc, tr = float(np.clip(tc, 0, 1)), float(np.clip(tr, 0, 1))
        h = self.h
        return float(h[r0, c0] * (1 - tc) * (1 - tr) + h[r0, c0 + 1] * tc * (1 - tr)
                     + h[r0 + 1, c0] * (1 - tc) * tr + h[r0 + 1, c0 + 1] * tc * tr)


def inside(area, x, y, margin_m=0.0):
    return abs(x) <= area.half_m + margin_m and abs(y) <= area.half_m + margin_m


def densify(pts, spacing_m):
    """地形に沿わせるため、点の間隔を spacing_m 以下に補う。"""
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(np.ceil(np.hypot(x1 - x0, y1 - y0) / spacing_m)))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def split_inside(area, pts, margin_m=0.0):
    """範囲外の点で道路を分割し、範囲内の連続部分だけ返す。"""
    runs, cur = [], []
    for x, y in densify(pts, POINT_SPACING_M):
        if inside(area, x, y, margin_m):
            cur.append((x, y))
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def road_width(tags):
    hw = tags.get("highway")
    width = ROAD_CLASSES.get(hw, (4.0, 9))[0]
    try:
        if "width" in tags:
            return float(tags["width"].replace("m", "").strip())
        if "lanes" in tags:
            return max(width, int(tags["lanes"]) * LANE_WIDTH_M)
    except ValueError:
        pass
    return width


def element_center(el):
    if el["type"] == "node":
        return el["lat"], el["lon"]
    if "geometry" in el and el["geometry"]:
        g = el["geometry"]
        return sum(p["lat"] for p in g) / len(g), sum(p["lon"] for p in g) / len(g)
    if "bounds" in el:
        b = el["bounds"]
        return (b["minlat"] + b["maxlat"]) / 2, (b["minlon"] + b["maxlon"]) / 2
    return None


def build(area, data, margin_m=0.0):
    sample = HeightSampler(area)
    roads, landmarks, coast = [], [], []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "way" and tags.get("highway") in ROAD_CLASSES and "geometry" in el:
            pts = [area.to_local(p["lat"], p["lon"]) for p in el["geometry"] if p]
            for i, run in enumerate(split_inside(area, pts, margin_m)):
                ue_pts = []
                for x, y in run:
                    ux, uy, uz = Area.local_to_ue(x, y, sample(x, y) + ROAD_Z_OFFSET_M)
                    ue_pts.append([round(ux, 1), round(uy, 1), round(uz, 1)])
                roads.append({
                    "id": f"{el['id']}_{i}",
                    "osm_way": el["id"],
                    "name": tags.get("name", ""),
                    "ref": tags.get("ref", ""),
                    "highway": tags["highway"],
                    "priority": ROAD_CLASSES[tags["highway"]][1],
                    "width_cm": round(road_width(tags) * 100.0),
                    "oneway": tags.get("oneway") == "yes",
                    "bridge": tags.get("bridge") == "yes",
                    "tunnel": tags.get("tunnel") == "yes",
                    "points_cm": ue_pts,
                })
        elif el["type"] == "way" and tags.get("natural") == "coastline" and "geometry" in el:
            coast.append([area.to_local(p["lat"], p["lon"]) for p in el["geometry"] if p])
        elif tags.get("name"):
            c = element_center(el)
            if c is None:
                continue
            x, y = area.to_local(*c)
            if not inside(area, x, y):
                continue
            ux, uy, uz = Area.local_to_ue(x, y, sample(x, y))
            landmarks.append({
                "name": tags["name"],
                "kind": next((f"{k}={tags[k]}" for k in ("natural", "tourism", "historic", "amenity")
                              if k in tags), ""),
                "osm": f"{el['type']}/{el['id']}",
                "lat": round(c[0], 7), "lon": round(c[1], 7),
                "location_cm": [round(ux, 1), round(uy, 1), round(uz, 1)],
            })
    roads.sort(key=lambda r: (r["priority"], r["id"]))
    return roads, landmarks, coast


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    data = fetch_osm(area)
    roads, landmarks, coast = build(area, data)
    out = area.out_dir
    meta = {"area": area.name, "units": "cm", "axes": "UE: +X 東, +Y 南, +Z 上",
            "source": "© OpenStreetMap contributors (ODbL)"}
    with open(os.path.join(out, "roads.json"), "w", encoding="utf-8") as f:
        json.dump({**meta, "roads": roads}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "landmarks.json"), "w", encoding="utf-8") as f:
        json.dump({**meta, "landmarks": landmarks}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "coastline_local_m.json"), "w", encoding="utf-8") as f:
        json.dump(coast, f)
    wide, _, _ = build(area, data, ROAD_MARGIN_M)
    with open(os.path.join(out, "roads_margin.json"), "w", encoding="utf-8") as f:
        json.dump({**meta, "margin_m": ROAD_MARGIN_M, "roads": wide}, f, ensure_ascii=False)
    total_km = sum(
        np.sum(np.linalg.norm(np.diff(np.array(r["points_cm"])[:, :2], axis=0), axis=1))
        for r in roads) / 100000.0
    print(f"道路 {len(roads)} 本 (計 {total_km:.1f} km), 目印 {len(landmarks)} 件")
    for lm in landmarks[:30]:
        print(f"  {lm['name']} ({lm['kind']})")
    print(f"出力先: {out}")


if __name__ == "__main__":
    main()
