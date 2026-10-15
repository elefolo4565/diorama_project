"""コースの道筋を決め、通るタイルを選ぶ。

使い方:
    python build_loop.py areas/itoshima_loop.json

道筋の決め方 (コースの設定 areas/<コース名>.json):
    "polygon" ([[緯度, 経度], ...]) があれば、その多角形にかかるタイルを全部作る (道筋は作らない。tools/kit/area_picker.py で地図に描ける)。
        ファストトラベルの行き先は "waypoints" (無ければ多角形の真ん中に近い主な道路の 1 か所)
    "route" があれば、その GPX / KML の線をそのまま使う (公式のコース図があればこちらが正確)
    無ければ OSM の主な道路を "waypoints" の順に最短経路で結ぶ ("loop" が true なら最後から最初へも戻る)
    "center_lat" / "center_lon" / "size_px" が無ければ、線の範囲から決めて設定ファイルに書き足す
    (原点は後から変えるとすべてのタイルがずれるので、一度決めたら固定)
    経由点に緯度経度が無ければ "q" (地名や施設名) を OSM の Nominatim で探して書き足す
    GPX の時に "waypoints" が無ければ、スタート・約 20km おき・ゴールをファストトラベルの行き先にする

出力 (out/<名前>/):
    osm_roads.json   Overpass API の生データ (主な道路だけ。設定が同じなら再実行時はこれを使う)
    loop_route.json  一周のポイント列 (緯度経度とローカル m)、距離、通る道路、必要なタイル
    preview.png      地形・道路・一周コース・タイルの確認用画像 (上が北)

タイル: futamigaura と同じ 4032m 四方の升目。中心 (原点) のタイルが (0, 0) で、i が東、j が北へ増える。
コースから corridor_m 以内にかかるタイルを「必要」とする。

データ出典: © OpenStreetMap contributors (ODbL)、国土地理院 標高タイル (DEM10B)
"""

import heapq
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from course import Course, read_track, track_extent
from geo import Area, http_get, http_post_form

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# 道を選ぶときの重み (距離に掛ける)。海沿いの県道を通したいので、細い道ほど避ける
ROUTE_COST = {
    "motorway": 50.0, "trunk": 1.2, "primary": 1.0, "secondary": 1.0, "tertiary": 1.3,
    "unclassified": 2.5, "residential": 4.0,
    "trunk_link": 2.0, "primary_link": 1.5, "secondary_link": 1.5, "tertiary_link": 1.8,
}
SNAP_CLASSES = ("trunk", "primary", "secondary", "tertiary")   # 経由点はこの道路の最寄りの点に寄せる
PREVIEW_PX = 2000


def overpass_query(area):
    s, w, n, e = area.bbox()
    b = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    hw = "|".join(ROUTE_COST)
    return f"""
[out:json][timeout:300];
way["highway"~"^({hw})$"]({b});
out body geom;
"""


def fetch(area):
    path = os.path.join(area.out_dir, "osm_roads.json")
    query = overpass_query(area)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("_query") == query:
            print(f"保存済みの OSM データを使用: {path}")
            return data
    print("Overpass API から主な道路を取得中 ...")
    data = json.loads(http_post_form(OVERPASS_URL, {"data": query}))
    data["_query"] = query
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


class Graph:
    def __init__(self, area, data):
        self.pos = {}      # node id -> (x, y) ローカル m
        self.adj = {}      # node id -> [(to, cost, length, way index)]
        self.ways = []
        for el in data.get("elements", []):
            if el["type"] != "way" or "geometry" not in el:
                continue
            tags = el.get("tags", {})
            hw = tags.get("highway")
            if hw not in ROUTE_COST:
                continue
            nodes, geom = el["nodes"], el["geometry"]
            if len(nodes) != len(geom):
                continue
            wi = len(self.ways)
            self.ways.append({"id": el["id"], "highway": hw, "ref": tags.get("ref", ""),
                              "name": tags.get("name", ""), "nodes": nodes})
            oneway = tags.get("oneway") in ("yes", "1") or tags.get("junction") == "roundabout"
            for nid, g in zip(nodes, geom):
                self.pos[nid] = area.to_local(g["lat"], g["lon"])
            for a, b in zip(nodes, nodes[1:]):
                (xa, ya), (xb, yb) = self.pos[a], self.pos[b]
                length = math.hypot(xb - xa, yb - ya)
                cost = length * ROUTE_COST[hw]
                self.adj.setdefault(a, []).append((b, cost, length, wi))
                if not oneway:
                    self.adj.setdefault(b, []).append((a, cost, length, wi))
                else:
                    self.adj.setdefault(b, [])
        self.snap_nodes = {n for w in self.ways if w["highway"] in SNAP_CLASSES for n in w["nodes"]}

    def nearest(self, x, y):
        best, bd = None, float("inf")
        for n in self.snap_nodes:
            px, py = self.pos[n]
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                best, bd = n, d
        return best, math.sqrt(bd)

    def shortest(self, src, dst):
        dist, prev = {src: 0.0}, {}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == dst:
                break
            if d > dist.get(u, float("inf")):
                continue
            for v, c, _, wi in self.adj.get(u, ()):
                nd = d + c
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = (u, wi)
                    heapq.heappush(heap, (nd, v))
        if dst not in dist:
            return None
        path, n = [], dst
        while n != src:
            u, wi = prev[n]
            path.append((n, wi))
            n = u
        path.append((src, None))
        return path[::-1]


def route(area, graph, waypoints, loop=True):
    snapped = []
    for wp in waypoints:
        n, d = graph.nearest(*area.to_local(wp["lat"], wp["lon"]))
        print(f"  経由点 {wp['name']}: 最寄りの道路まで {d:.0f} m")
        snapped.append(n)
    legs = []
    for i, (a, b) in enumerate(zip(snapped, snapped[1:] + (snapped[:1] if loop else []))):
        p = graph.shortest(a, b)
        if p is None:
            sys.exit(f"{waypoints[i]['name']} から次の経由点へ道路がつながりません")
        legs.append((waypoints[i]["name"], p))
    return legs


def tiles_near(area, pts, corridor_m):
    half = (area.tile_size_px - 1) * area.meters_per_px / 2.0
    size = 2 * half
    need = set()
    for x, y in pts:
        for i in range(math.floor((x - corridor_m + half) / size), math.floor((x + corridor_m + half) / size) + 1):
            for j in range(math.floor((y - corridor_m + half) / size), math.floor((y + corridor_m + half) / size) + 1):
                cx, cy = i * size, j * size
                dx = max(abs(x - cx) - half, 0.0)
                dy = max(abs(y - cy) - half, 0.0)
                if math.hypot(dx, dy) <= corridor_m:
                    need.add((i, j))
    return sorted(need)


def inside(poly, x, y):
    """点 (x, y) が多角形 poly ([(x, y), ...]) の中か (偶奇規則)。"""
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def tiles_in_polygon(area, poly, step=250.0):
    """多角形に少しでもかかるタイル。タイルの中を step m おきに調べ、多角形の頂点がタイルの中にある場合も入れる。"""
    half = (area.tile_size_px - 1) * area.meters_per_px / 2.0
    size = 2 * half
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    need = set()
    for i in range(math.floor((min(xs) + half) / size), math.floor((max(xs) + half) / size) + 1):
        for j in range(math.floor((min(ys) + half) / size), math.floor((max(ys) + half) / size) + 1):
            cx, cy = i * size, j * size
            if any(abs(x - cx) <= half and abs(y - cy) <= half for x, y in poly):
                need.add((i, j))
                continue
            n = int(size // step) + 1
            if any(inside(poly, cx - half + a * size / (n - 1), cy - half + b * size / (n - 1))
                   for a in range(n) for b in range(n)):
                need.add((i, j))
    return sorted(need)


def polygon_stops(area, graph, poly, waypoints):
    """多角形モードのファストトラベルの行き先。経由点ごとに、多角形の中のいちばん近い主な道路の点から
    道沿いに数点たどった短い線を返す (setup_project.py は点の 3 つ先を向きに使う)。"""
    nodes = [n for n in graph.snap_nodes if inside(poly, *graph.pos[n])] or \
            [n for n in graph.pos if inside(poly, *graph.pos[n])]
    if not nodes:
        sys.exit("多角形の中に道路がありません。範囲を広げてください")
    if not waypoints:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        lat, lon = area.to_latlon(cx, cy)
        waypoints = [{"name": "スタート", "lat": round(lat, 6), "lon": round(lon, 6)}]
    chunks = []
    for wp in waypoints:
        x, y = area.to_local(wp["lat"], wp["lon"])
        n = min(nodes, key=lambda k: (graph.pos[k][0] - x) ** 2 + (graph.pos[k][1] - y) ** 2)
        print(f"  行き先 {wp['name']}: 道路まで {math.dist(graph.pos[n], (x, y)):.0f} m")
        path, seen = [n], {n}
        while len(path) < 6:
            nxt = [v for v, _, _, _ in graph.adj.get(path[-1], ()) if v not in seen]
            if not nxt:
                break
            path.append(nxt[0])
            seen.add(nxt[0])
        chunks.append((wp["name"], [(k, None) for k in path]))
    return waypoints, chunks


def densify(pts, step):
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / step)))
        out += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(1, n + 1)]
    return out


def load_relief(area):
    """プレビューの下絵: DEM10B z13 (遠景と同じタイル) を PREVIEW_PX 四方に並べ直す。"""
    from build_terrain import load_mosaic, sample_bilinear
    from geo import latlon_to_global_px
    mosaic, ox, oy = load_mosaic(area, "dem10b", "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png", 13)
    s = np.linspace(-area.half_m, area.half_m, PREVIEW_PX)
    xx, yy = np.meshgrid(s, -s)
    lat, lon = area.to_latlon(xx, yy)
    gx, gy = latlon_to_global_px(lat, lon, 13)
    return sample_bilinear(mosaic, gx - ox, gy - oy)


def to_px(area, x, y):
    k = PREVIEW_PX / (2 * area.half_m)
    return (x + area.half_m) * k, (area.half_m - y) * k


def write_preview(area, graph, legs, waypoints, tiles, path, polygon=None):
    h = load_relief(area)
    sea = ~np.isfinite(h) | (h < 0.5)
    t = np.clip(np.nan_to_num(h) / 400.0, 0, 1)
    img = np.zeros(h.shape + (3,), np.uint8)
    img[..., 0] = 90 + 140 * t
    img[..., 1] = 130 + 90 * t
    img[..., 2] = 80 + 90 * t
    img[sea] = (45, 75, 130)
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("msgothic.ttc", 22)
    except OSError:
        try:
            font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 22)
        except OSError:
            font = ImageFont.load_default()
    half = (area.tile_size_px - 1) * area.meters_per_px / 2.0
    for (i, j) in tiles:
        a = to_px(area, i * 2 * half - half, j * 2 * half + half)
        b = to_px(area, i * 2 * half + half, j * 2 * half - half)
        d.rectangle([a, b], outline=(255, 255, 255), width=2)
        d.text((a[0] + 6, a[1] + 4), f"{i},{j}", fill=(255, 255, 255), font=font)
    for w in (graph.ways if graph else []):
        pts = [to_px(area, *graph.pos[n]) for n in w["nodes"]]
        col = (230, 230, 230) if w["highway"] in SNAP_CLASSES else (170, 170, 170)
        d.line(pts, fill=col, width=2 if w["highway"] in SNAP_CLASSES else 1)
    if polygon:
        d.line([to_px(area, *q) for q in polygon + polygon[:1]], fill=(255, 140, 0), width=4)
    for _, p in legs:
        xy = [graph.pos[n] for n, _ in p] if graph else p
        d.line([to_px(area, *q) for q in xy], fill=(230, 30, 30), width=5)
    for wp in waypoints:
        x, y = to_px(area, *area.to_local(wp["lat"], wp["lon"]))
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(255, 220, 0), outline=(0, 0, 0))
        d.text((x + 10, y - 12), wp["name"], fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    im.save(path)


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
TRACK_STOP_KM = 20.0      # GPX に経由点が無い時、ファストトラベルの行き先をこの間隔で置く
AUTO_MARGIN_M = 3000.0    # 範囲を自動で決める時、コースのまわりに足す幅


def geocode_waypoints(path, cfg):
    """緯度経度の無い経由点を、"q" (地名や施設名) から OSM の Nominatim で探して設定ファイルに書き足す。
    書き足した後は緯度経度が使われるので、ずれていたら直接直せばよい。"""
    todo = [w for w in cfg.get("waypoints", []) if "lat" not in w]
    if not todo:
        return
    import hashlib
    import urllib.parse
    from geo import TOOLS_DIR
    for w in todo:
        q = w.get("q") or w["name"]
        url = NOMINATIM_URL + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "jp"})
        cache = os.path.join(TOOLS_DIR, "out", "_cache", "nominatim", hashlib.md5(q.encode("utf-8")).hexdigest() + ".json")
        res = json.loads(http_get(url, cache) or b"[]")
        if not res:
            sys.exit(f"経由点 {w['name']} ({q}) が見つかりません。\"q\" を直すか lat / lon を書いてください")
        w["lat"], w["lon"] = round(float(res[0]["lat"]), 6), round(float(res[0]["lon"]), 6)
        print(f"  経由点 {w['name']}: {res[0].get('display_name', '')} ({w['lat']}, {w['lon']})")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fill_extent(path, cfg, latlons):
    """center_lat / center_lon / size_px が無ければ、コースの範囲から決めて設定ファイルに書き足す。"""
    if all(k in cfg for k in ("center_lat", "center_lon", "size_px")):
        return
    (clat, clon), hx, hy = track_extent(latlons)
    rot = math.radians(float(cfg.get("rotation_deg", 0.0)))
    if rot:   # 升目を回すときは、回した向きでの広がり
        k = math.pi / 180.0 * 6378137.0
        en = [((lon - clon) * k * math.cos(math.radians(clat)), (lat - clat) * k) for lat, lon in latlons]
        hx = max(abs(e * math.cos(rot) + n * math.sin(rot)) for e, n in en)
        hy = max(abs(-e * math.sin(rot) + n * math.cos(rot)) for e, n in en)
    tile_m = (int(cfg["tile_size_px"]) - 1) * float(cfg["meters_per_px"])
    n = 2 * math.ceil((max(hx, hy) + AUTO_MARGIN_M + tile_m / 2) / tile_m) + 1   # 奇数枚 (中心のタイルが原点)
    cfg.setdefault("center_lat", round(clat, 4))
    cfg.setdefault("center_lon", round(clon, 4))
    cfg.setdefault("size_px", int(n * tile_m / float(cfg["meters_per_px"])) + 1)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"範囲を決めました: 中心 {cfg['center_lat']}, {cfg['center_lon']}、{n} x {n} タイル分 (設定ファイルに書き足しました)")


def track_route(area, course, cfg):
    """GPX / KML の線をコースにする。経由点が無ければ、スタート・約 20km おき・ゴールを作る。"""
    track = read_track(os.path.join(os.path.dirname(course.path), course.route_file))
    xy = [area.to_local(lat, lon) for lat, lon in track]
    if course.loop and xy[0] != xy[-1]:
        xy.append(xy[0])
        track.append(track[0])
    waypoints = cfg.get("waypoints")
    if not waypoints:
        waypoints, run, next_km = [{"name": "スタート", "lat": track[0][0], "lon": track[0][1]}], 0.0, TRACK_STOP_KM
        total_km = sum_len(xy) / 1000
        for k in range(1, len(xy)):
            run += math.hypot(xy[k][0] - xy[k - 1][0], xy[k][1] - xy[k - 1][1]) / 1000
            if run >= next_km and run < total_km - TRACK_STOP_KM / 2:
                waypoints.append({"name": f"{next_km:.0f}km", "lat": track[k][0], "lon": track[k][1]})
                next_km += TRACK_STOP_KM
        if not course.loop:
            waypoints.append({"name": "ゴール", "lat": track[-1][0], "lon": track[-1][1]})
    return track, xy, waypoints


def sum_len(xy):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(xy, xy[1:]))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    course = Course(path)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    geocode_waypoints(path, cfg)
    if cfg.get("polygon"):
        fill_extent(path, cfg, [tuple(p) for p in cfg["polygon"]])
    elif course.route_file:
        fill_extent(path, cfg, read_track(os.path.join(os.path.dirname(path), course.route_file)))
    else:
        fill_extent(path, cfg, [(w["lat"], w["lon"]) for w in cfg["waypoints"]])
    area = Area(path)
    area.tile_size_px = int(cfg["tile_size_px"])

    points, summary, total = [], [], 0.0
    polygon = [area.to_local(lat, lon) for lat, lon in cfg.get("polygon", [])]
    if polygon:
        graph = Graph(area, fetch(area))
        print(f"道路 {len(graph.ways)} 本, 点 {len(graph.pos)} 個")
        waypoints, stops = polygon_stops(area, graph, polygon, cfg.get("waypoints"))
        if not cfg.get("waypoints"):
            cfg["waypoints"] = waypoints
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.write("\n")
        for name, p in stops:
            for n, _ in p:
                x, y = graph.pos[n]
                lat, lon = area.to_latlon(x, y)
                points.append({"lat": round(lat, 7), "lon": round(lon, 7), "x_m": round(x, 1), "y_m": round(y, 1),
                               "osm_node": n})
        legs = []
    elif course.route_file:
        track, xy, waypoints = track_route(area, course, cfg)
        graph, legs = None, [("スタート", xy)]
        total = sum_len(xy)
        points = [{"lat": round(lat, 7), "lon": round(lon, 7), "x_m": round(x, 1), "y_m": round(y, 1)}
                  for (lat, lon), (x, y) in zip(track, xy)]
        summary.append({"from": "スタート", "km": round(total / 1000, 2), "roads": {course.route_file: round(total / 1000, 2)}})
        if not cfg.get("waypoints"):
            cfg["waypoints"] = waypoints
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"ファストトラベルの行き先を {len(waypoints)} か所作りました (設定ファイルの waypoints で直せます)")
    else:
        waypoints = cfg["waypoints"]
        graph = Graph(area, fetch(area))
        print(f"道路 {len(graph.ways)} 本, 点 {len(graph.pos)} 個")
        legs = route(area, graph, waypoints, course.loop)
    for name, p in (legs if graph else []):   # 多角形モードでは legs は空
        leg_len, refs = 0.0, {}
        for (a, _), (b, wi) in zip(p, p[1:]):
            (xa, ya), (xb, yb) = graph.pos[a], graph.pos[b]
            seg = math.hypot(xb - xa, yb - ya)
            leg_len += seg
            w = graph.ways[wi]
            if w["ref"]:
                key = f"{'国道' if w['highway'].startswith('trunk') else '県道'}{w['ref']}号"
            else:
                key = w["name"] or w["highway"]
            refs[key] = refs.get(key, 0.0) + seg
        for n, _ in p[(1 if points else 0):]:
            x, y = graph.pos[n]
            lat, lon = area.to_latlon(x, y)
            points.append({"lat": round(lat, 7), "lon": round(lon, 7), "x_m": round(x, 1), "y_m": round(y, 1),
                           "osm_node": n})
        total += leg_len
        summary.append({"from": name, "km": round(leg_len / 1000, 2),
                        "roads": {k: round(v / 1000, 2) for k, v in sorted(refs.items(), key=lambda kv: -kv[1])}})

    if polygon:
        tiles = tiles_in_polygon(area, polygon)
    else:
        pts = densify([(p["x_m"], p["y_m"]) for p in points], 50.0)
        tiles = tiles_near(area, pts, float(cfg.get("corridor_m", 300)))
    out = {"name": area.name, "origin_lat": area.center_lat, "origin_lon": area.center_lon,
           "tile_size_m": (area.tile_size_px - 1) * area.meters_per_px,
           "axes": "x_m 東, y_m 北 (原点からの m)。タイル (i, j) の中心は (i, j) x tile_size_m",
           "source": "© OpenStreetMap contributors (ODbL)",
           "mode": "polygon" if polygon else "route",
           "loop": course.loop and not polygon, "length_km": round(total / 1000, 2), "legs": summary,
           "tiles": [list(t) for t in tiles], "points": points}
    with open(os.path.join(area.out_dir, "loop_route.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    if polygon:
        print(f"多角形の範囲: 必要なタイル {len(tiles)} 枚: {tiles}")
    else:
        print(f"{'一周' if course.loop else '全長'} {total / 1000:.1f} km, 必要なタイル {len(tiles)} 枚: {tiles}")
    for s in summary:
        print(f"  {s['from']} から {s['km']} km: {s['roads']}")
    write_preview(area, graph, legs, waypoints, tiles, os.path.join(area.out_dir, "preview.png"), polygon)
    print(f"出力先: {area.out_dir}")


if __name__ == "__main__":
    main()
