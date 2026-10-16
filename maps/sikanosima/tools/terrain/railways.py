"""線路と駅 (道床・枕木・レール・踏切・架線・鉄橋と高架・トンネルの入口・ホーム・上屋・駅名標・駅舎)。

コースの設定の "features" の "railways" が true のときだけ作る。
- apply_roads.py: OSM の線路を取り (osm_railways.json)、なめらかな勾配の高さを決めて railways.json に書き、
  地形に道床 (平らな帯と、切土・盛土ののり面) を焼き込む。線路と交わる道路は、踏切の所でレールの高さに合わせる
- build_scenery.py: railways.json から線路の形 (タイルごとの形 world_meshes)、枕木・踏切・架線柱 (instances)、
  駅のホーム・上屋・駅名標 (world_meshes)、ホームの灯り (lights) を作る。駅舎は建物 (buildings.py) の見た目 "station" で建てる

線路の高さ
- つながった線路 (端の点を共有する way) をひと続きにして、5m おきの地面の高さを 160m の幅でならす (切土と盛土になる)
- 橋 (bridge) は両側の地面の高さを結び、下の地面や海から最低 1.8m (長い高架は 6.5m) 上げる。トンネルは両側を結ぶ
- 分かれ目や行き止まりの端は、まわり 60m の地面の平均に合わせる (同じ点に集まる線路の高さがそろう)
- タイルの外 400m まで作ってから切り取るので、隣のタイルとの境目で高さがそろう

駅
- OSM の railway=station / halt の点。ホームは OSM の railway=platform (面または線) があればその形、無ければ
  いちばん近い線路の外側に、線路に沿った 70m (halt は 45m) のホームを作る (複線なら両側)
- 駅舎は、OSM の building=train_station、または駅の点の近くの建物に駅の見た目を付ける。無ければ線路沿いに建てる

データ出典: © OpenStreetMap contributors (ODbL)
"""

import json
import math
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import scenery_meshes as sm
from buildings import OVERPASS_URL, clean_poly, min_rect, signed_area
from geo import http_post_form

RAIL_KINDS = ("rail", "light_rail", "narrow_gauge", "subway", "preserved")
MARGIN_M = 400.0            # タイルの外のこの距離まで線路を作る (境目で高さをそろえるため)
SPACING_M = 5.0             # 線路の点の間隔
SMOOTH_M = 160.0            # 線路の高さをならす幅 (勾配をゆるくする)
PIN_RADIUS_M = 60.0         # 線路の端の高さは、この半径の地面の平均
PIN_RAMP_M = 150.0
SNAP_M = 12.0               # 先に作った線路からこの距離までの点は、その高さにそろえる (複線・側線)
SNAP_FULL_M = 6.0
MIN_Z_M = 1.0               # 道床の最低の高さ (海面 = 0)
BRIDGE_CLEAR_M = 1.8        # 橋の下の地面・水面からの高さ (道床の上面まで)
VIADUCT_CLEAR_M = 6.5       # 長い高架 (VIADUCT_LEN_M 以上で陸の上)
VIADUCT_LEN_M = 250.0
BED_HALF_M = 2.6            # 地形に焼く道床の平らな帯の半分の幅
BED_SHOULDER_M = 9.0        # のり面の幅
LAYER_HALF_M = 1.7          # 道路レイヤー (草が生えない) を塗る半分の幅 (バラストの下に隠れる)
BALLAST_TOP_M = 0.30        # 道床からのバラストの上面
SLEEPER_TOP_M = 0.36
RAIL_TOP_M = 0.52           # 道床からのレールの上面。踏切の道路はこの高さ
RAIL_H_M = 0.16
PLATFORM_ABOVE_RAIL_M = 0.92
PLATFORM_EDGE_M = 1.55      # 線路の中心からホームの縁まで
SLEEPER_SPACING_M = 0.62
CATENARY_SPACING_M = 50.0
CATENARY_OFFSET_M = 2.9     # 線路の中心から架線柱まで
CONTACT_WIRE_M = 5.0        # レールの上面からトロリ線まで
MESSENGER_M = 5.9
CROSSING_EXTRA_M = 0.8      # 道路の幅にこれを足した所までを踏切にする
STATION_TRACK_M = 120.0     # 駅の点からこの距離の中に線路が無ければ駅を作らない (地下駅など)
PLATFORM_LEN_M = {"station": 70.0, "halt": 45.0}
PLATFORM_W_M = 3.2
STATION_BUILDING_M = 45.0   # 駅の点からこの距離の建物を駅舎にする (OSM の building=train_station は 120m)
SEED = 20261016
# 駅名標の文字のフォント (見つかった最初のもの。無ければ駅名標は無地)
FONT_FILES = ("C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothB.ttc",
              "C:/Windows/Fonts/msgothic.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
SIGN_W_M, SIGN_H_M = 1.9, 0.9


# ---------------------------------------------------------------- データ
def query(area):
    s, w, n, e = area.bbox(margin_m=MARGIN_M)
    bm = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    kinds = "|".join(RAIL_KINDS)
    return (f'[out:json][timeout:180];(way["railway"~"^({kinds})$"]({bm});'
            f'nwr["railway"~"^(station|halt)$"]({bm});'
            f'way["railway"="platform"]({bm});way["public_transport"="platform"]["train"="yes"]({bm});'
            f'way["building"="train_station"]({bm}););out body geom;')


def fetch(area):
    """OSM の線路・駅・ホーム (osm_railways.json)。取れなければ None。"""
    path = os.path.join(area.out_dir, "osm_railways.json")
    q = query(area)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("_query") == q:
            return data
    print("Overpass API から OSM の線路と駅を取得中 ...")
    try:
        data = json.loads(http_post_form(OVERPASS_URL, {"data": q}, retries=3))
    except Exception as ex:  # noqa: BLE001 取れなければ線路を作らない (ほかは作る)
        print(f"OSM の線路を取得できませんでした ({ex})。線路と駅は作りません")
        return None
    data["_query"] = q
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def is_bridge(tags):
    return tags.get("bridge", "no") not in ("no", "") or tags.get("man_made") == "bridge"


def is_tunnel(tags):
    return tags.get("tunnel", "no") not in ("no", "", "building_passage") or tags.get("location") == "underground"


def gauge_m(tags):
    try:
        return float(str(tags.get("gauge", "1067")).split(";")[0]) / 1000.0
    except ValueError:
        return 1.067


def make_chains(ways):
    """端の点を 2 本だけが共有する way をつないだ列 [[(way の番号, 逆向きか)]]。"""
    ends = {}
    for i, w in enumerate(ways):
        for nd in (w["nodes"][0], w["nodes"][-1]):
            ends.setdefault(nd, []).append(i)
    used, out = set(), []

    def step(node):
        js = ends.get(node, [])
        if len(js) != 2:
            return None
        cand = [j for j in js if j not in used]
        return cand[0] if len(cand) == 1 else None

    for i in range(len(ways)):
        if i in used:
            continue
        used.add(i)
        seq = [(i, False)]
        node = ways[i]["nodes"][-1]
        while (j := step(node)) is not None:
            rev = ways[j]["nodes"][0] != node
            used.add(j)
            seq.append((j, rev))
            node = ways[j]["nodes"][0] if rev else ways[j]["nodes"][-1]
        node = ways[i]["nodes"][0]
        while (j := step(node)) is not None:
            rev = ways[j]["nodes"][-1] != node   # 前につなぐので、終わりが node なら同じ向き
            used.add(j)
            seq.insert(0, (j, rev))
            node = ways[j]["nodes"][-1] if rev else ways[j]["nodes"][0]
        out.append(seq)
    return out


def moving_average(z, n):
    if n < 2 or len(z) < 3:
        return z.copy()
    n = min(n, len(z) if len(z) % 2 else len(z) - 1)
    n = n if n % 2 else n - 1
    if n < 3:
        return z.copy()
    zp = np.pad(z, n // 2, mode="edge")
    return np.convolve(zp, np.ones(n) / n, mode="valid")


def profile(xy, kind, sample, pins):
    """道床の高さ (m)。xy: (N,2) UE の m、kind: 0 地面 / 1 橋 / 2 トンネル。pins: [(番号, 高さ)]。"""
    t = np.array([sample(x, -y) for x, y in xy])
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    ground = kind == 0
    z = t.copy()
    if ground.any():
        z[~ground] = np.interp(s[~ground], s[ground], t[ground])
    else:
        z = np.interp(s, [s[0], s[-1]], [t[0], t[-1]])
    # 橋の下の高さ
    need = np.full(len(z), -np.inf)
    i = 0
    while i < len(kind):
        if kind[i] != 1:
            i += 1
            continue
        j = i
        while j + 1 < len(kind) and kind[j + 1] == 1:
            j += 1
        a, b = max(i - 1, 0), min(j + 1, len(kind) - 1)
        length = s[b] - s[a]
        clear = VIADUCT_CLEAR_M if length >= VIADUCT_LEN_M and np.median(t[i:j + 1]) > 0.5 else BRIDGE_CLEAR_M
        d = np.minimum(s[i:j + 1] - s[a], s[b] - s[i:j + 1])
        need[i:j + 1] = np.maximum(t[i:j + 1], 0.0) + np.minimum(clear, 0.6 + 0.035 * d)
        i = j + 1
    z = np.maximum(z, need)
    n = int(round(SMOOTH_M / SPACING_M))
    z = moving_average(z, n)
    for _ in range(2):
        z = moving_average(np.maximum(z, need), int(round(40.0 / SPACING_M)))
    for k, pz in pins:
        ramp = np.clip(1.0 - np.abs(s - s[k]) / PIN_RAMP_M, 0, 1)
        z += (pz - z[k]) * ramp
    z = np.maximum(z, need)
    z = np.maximum(z, MIN_Z_M)
    return z


class Snap:
    """先に高さを決めた線路の点。並んだ線路 (複線・側線・駅の構内) を同じ高さにそろえる。"""
    CELL = 10.0

    def __init__(self):
        self.cells = {}

    def add(self, xy, z):
        for (x, y), zz in zip(xy, z):
            self.cells.setdefault((int(x // self.CELL), int(y // self.CELL)), []).append((x, y, zz))

    def near(self, x, y):
        """(距離, 高さ)。SNAP_M より遠ければ None。"""
        cx, cy = int(x // self.CELL), int(y // self.CELL)
        best = None
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for px, py, pz in self.cells.get((i, j), ()):
                    d = math.hypot(px - x, py - y)
                    if best is None or d < best[0]:
                        best = (d, pz)
        return best if best and best[0] < SNAP_M else None


def snap(xy, z, kind, done):
    """先の線路から SNAP_M 以内の点は、その高さにそろえる (近いほど強く)。"""
    out = z.copy()
    hit = False
    for i, (x, y) in enumerate(xy):
        if kind[i] == 2:
            continue
        nb = done.near(x, y)
        if nb is not None:
            w = float(np.clip((SNAP_M - nb[0]) / (SNAP_M - SNAP_FULL_M), 0, 1))
            out[i] = nb[1] * w + z[i] * (1 - w)
            hit = True
    if hit:
        out = moving_average(out, int(round(30.0 / SPACING_M)))
    return out


def disc_mean(sample, x, y):
    vals = [sample(x + r * math.cos(a), -(y + r * math.sin(a)))
            for r in (0.0, PIN_RADIUS_M / 2, PIN_RADIUS_M) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    return max(float(np.mean(vals)), MIN_Z_M)


def build(area, sample):
    """OSM の線路と駅を、道床の高さ付きで railways.json に書いて返す。取れない・無ければ None。"""
    data = fetch(area)
    if data is None:
        return None

    def to_ue(lat, lon):
        x, y = area.to_local(lat, lon)
        return x, -y

    lim = area.half_m + MARGIN_M
    ways, stations, platforms, station_buildings = [], [], [], []
    for el in data.get("elements", []):
        t = el.get("tags", {})
        geom = [p for p in el.get("geometry", []) if p]
        if el["type"] == "way" and t.get("railway") in RAIL_KINDS and len(geom) >= 2 and len(el.get("nodes", [])) == len(
                el.get("geometry", [])):
            if t.get("railway") == "subway" and not is_bridge(t):
                t = dict(t, tunnel=t.get("tunnel", "yes"))
            ways.append({"nodes": el["nodes"], "pts": [to_ue(p["lat"], p["lon"]) for p in geom], "tags": t})
        elif t.get("railway") in ("station", "halt") and t.get("station") != "subway":
            c = (el["lat"], el["lon"]) if "lat" in el else ((el["center"]["lat"], el["center"]["lon"]) if el.get("center") else None)
            if c is None and geom:
                c = (np.mean([p["lat"] for p in geom]), np.mean([p["lon"] for p in geom]))
            if c is None:
                continue
            x, y = to_ue(*c)
            if abs(x) <= area.half_m and abs(y) <= area.half_m:
                stations.append({"name": t.get("name", ""), "kind": t["railway"], "osm": f"{el['type']}/{el['id']}",
                                 "pos_m": [round(x, 2), round(y, 2)]})
        elif el["type"] == "way" and (t.get("railway") == "platform" or t.get("public_transport") == "platform") and geom:
            pts = [to_ue(p["lat"], p["lon"]) for p in geom]
            closed = len(pts) >= 4 and el["nodes"][0] == el["nodes"][-1]
            platforms.append({"pts_m": [[round(a, 2), round(b, 2)] for a, b in pts], "area": closed and t.get("area") != "no",
                              "width_m": t.get("width")})
        elif el["type"] == "way" and t.get("building") == "train_station" and geom:
            pts = np.array([to_ue(p["lat"], p["lon"]) for p in geom])
            station_buildings.append([round(float(pts[:, 0].mean()), 2), round(float(pts[:, 1].mean()), 2)])

    pieces = []
    for ci, seq in enumerate(make_chains(ways)):
        pts, seg_kind, seg_way = [], [], []
        for wi, rev in seq:
            p = ways[wi]["pts"][::-1] if rev else ways[wi]["pts"]
            k = 2 if is_tunnel(ways[wi]["tags"]) else 1 if is_bridge(ways[wi]["tags"]) else 0
            if not pts:
                pts.append(p[0])
            for q in p[1:]:
                a = np.array(pts[-1])
                b = np.array(q)
                m = max(1, int(math.ceil(np.hypot(*(b - a)) / SPACING_M)))
                for j in range(1, m + 1):
                    pts.append(tuple(a + (b - a) * j / m))
                    seg_kind.append(k)
                    seg_way.append(wi)
        xy = np.array(pts)
        if len(xy) < 2:
            continue
        seg_kind, seg_way = np.array(seg_kind), np.array(seg_way)
        inside = (np.abs(xy[:, 0]) <= lim) & (np.abs(xy[:, 1]) <= lim)
        # タイルの外 (MARGIN_M より遠く) で切る
        idx = np.flatnonzero(inside)
        if len(idx) < 2:
            continue
        for ri, run in enumerate(np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)):
            if len(run) >= 2:
                pieces.append((ci, ri, xy, seg_kind, seg_way, run[0], run[-1]))

    lines, done = [], Snap()
    # 長い線路 (本線) から高さを決め、並んだ側線や複線のもう片方をそれにそろえる
    for ci, ri, xy, seg_kind, seg_way, a, b in sorted(pieces, key=lambda pc: -(pc[6] - pc[5])):
        sub = xy[a:b + 1]
        sk = seg_kind[a:b]
        kind = np.empty(len(sub), int)
        kind[1:-1] = np.where(sk[:-1] == sk[1:], sk[1:], 0)
        kind[0], kind[-1] = sk[0], sk[-1]
        pins = []
        for end, k in ((0, a), (len(sub) - 1, b)):
            clipped = (k == a and a > 0) or (k == b and b < len(xy) - 1)
            if not clipped and kind[end] == 0:
                pins.append((end, disc_mean(sample, *sub[end])))
        z = snap(sub, profile(sub, kind, sample, pins), kind, done)
        done.add(sub[kind != 2], z[kind != 2])
        ways_here = seg_way[a:b]
        elec = np.array([ways[w]["tags"].get("electrified", "no") in ("contact_line", "yes") for w in ways_here])
        pe = np.r_[elec[0], elec]
        names = [ways[w]["tags"].get("name", "") for w in ways_here]
        first = ways[ways_here[0]]["tags"]
        lines.append({
            "id": f"{ci}_{ri}", "name": max(set(names), key=names.count) if names else "",
            "railway": first.get("railway", "rail"), "service": first.get("service", ""),
            "gauge_m": gauge_m(first),
            "points_cm": [[round(float(p[0] * 100), 1), round(float(p[1] * 100), 1), round(float(zz * 100), 1)]
                          for p, zz in zip(sub, z)],
            "kind": [int(k) for k in kind], "electrified": [int(e) for e in pe]})
    doc = {"note": "UE 座標 (cm、タイルの中心が原点)。Z は道床 (地形に焼いた平らな帯) の高さ。kind: 0 地面, 1 橋, 2 トンネル",
           "lines": lines, "stations": stations, "platforms": platforms, "station_buildings": station_buildings}
    with open(os.path.join(area.out_dir, "railways.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    km = sum(np.hypot(*np.diff(np.array(l["points_cm"])[:, :2], axis=0).T).sum() for l in lines) / 1e5
    print(f"線路: {len(lines)} 本 ({km:.1f} km、タイルの外 {MARGIN_M:.0f} m まで)、駅 {len(stations)}、OSM のホーム {len(platforms)}")
    return doc


def load(area):
    path = os.path.join(area.out_dir, "railways.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 地形に焼く (apply_roads.py)
def ground_runs(doc, kinds=(0,)):
    """kind が kinds の続いた部分 [(点 (N,3) cm, 線)]。境目の点は両側に入れる。"""
    out = []
    for line in doc["lines"]:
        p = np.array(line["points_cm"], float)
        k = np.array(line["kind"])
        ok = np.isin(k, kinds)
        i = 0
        while i < len(k):
            if not ok[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(k) and ok[j + 1]:
                j += 1
            if j > i:
                out.append((p[i:j + 1], line))
            i = j + 1
    return out


def bed_roads(doc):
    """地形に焼く道床を、道路と同じ形の辞書にする (apply_roads.burn に渡す)。"""
    return [{"points_cm": p.tolist(), "width_cm": BED_HALF_M * 200, "bridge": False, "tunnel": False}
            for p, _ in ground_runs(doc)]


def crossing_pins(roads, doc, z_offset_m):
    """線路 (地面の部分) と交わる道路に交点を足し、その点の高さをレールの上面に決める。
    roads の points_cm を書き換え、r["pins"] = [[点の番号, 路面の高さ m]] を付ける。足した数を返す。"""
    segs = []
    for p, _ in ground_runs(doc):
        segs.append(np.c_[p[:-1], p[1:]])
    if not segs:
        return 0
    S = np.concatenate(segs) / 100.0   # (M, 6) m: x0 y0 z0 x1 y1 z1
    lo = np.minimum(S[:, :2], S[:, 3:5]).min(0) - 10
    hi = np.maximum(S[:, :2], S[:, 3:5]).max(0) + 10
    a, b = S[:, :2], S[:, 3:5]
    count = 0
    for r in roads:
        if r.get("bridge") or r.get("tunnel"):
            continue
        P = np.array(r["points_cm"], float) / 100.0
        if len(P) < 2 or (P[:, :2].max(0) < lo).any() or (P[:, :2].min(0) > hi).any():
            continue
        new_pts, pins = [list(r["points_cm"][0])], []
        for i in range(len(P) - 1):
            c, d = P[i, :2], P[i + 1, :2]
            r_ = d - c
            s_ = b - a
            den = r_[0] * s_[:, 1] - r_[1] * s_[:, 0]
            ok = np.abs(den) > 1e-9
            qp = a - c
            with np.errstate(divide="ignore", invalid="ignore"):
                tt = (qp[:, 0] * s_[:, 1] - qp[:, 1] * s_[:, 0]) / den
                uu = (qp[:, 0] * r_[1] - qp[:, 1] * r_[0]) / den
            hit = ok & (tt >= 0) & (tt < 1) & (uu >= 0) & (uu <= 1)
            for k in np.flatnonzero(hit)[np.argsort(tt[hit])]:
                x, y = c + r_ * tt[k]
                bed = S[k, 2] + (S[k, 5] - S[k, 2]) * uu[k]
                zr = bed + RAIL_TOP_M
                if pins and np.hypot(x - new_pts[-1][0] / 100, y - new_pts[-1][1] / 100) < 1.0:
                    continue   # 複線の 2 本目はほぼ同じ所
                new_pts.append([round(x * 100, 1), round(y * 100, 1), round((zr + z_offset_m) * 100, 1)])
                pins.append([len(new_pts) - 1, zr])
                count += 1
            new_pts.append(list(r["points_cm"][i + 1]))
        if pins:
            r["points_cm"] = new_pts
            r["pins"] = pins
    return count


def apply_pins(z, pts_m, pins):
    """ならした路面の高さ z を、踏切の点 pins で決めた高さにする (前後をなだらかにつなぐ)。"""
    if not pins:
        return z
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(pts_m[:, :2], axis=0).T))]
    z = z.copy()
    for k, target in pins:
        delta = target - z[k]
        ramp_m = max(25.0, abs(delta) / 0.07)
        z += delta * np.clip(1.0 - np.abs(s - s[k]) / ramp_m, 0, 1)
    for k, target in pins:  # 近い踏切どうしの足し合わせで、ずれた分を直す
        z[k] = target
    return z


# ---------------------------------------------------------------- 並べ方 (build_scenery.py)
def clip_runs(p, kind, elec, half_cm):
    """タイルの中の部分。境目は補間して切る (隣のタイルと端がそろう)。[(点 (N,3) cm, kind, elec)]"""
    inside = (np.abs(p[:, 0]) <= half_cm) & (np.abs(p[:, 1]) <= half_cm)
    out, cur = [], None

    def cut(a, b):
        # a (中) と b (外) の間で、境目を越える所
        t = 1.0
        for ax in (0, 1):
            if abs(b[ax]) > half_cm:
                lim = math.copysign(half_cm, b[ax])
                tt = (lim - a[ax]) / (b[ax] - a[ax]) if b[ax] != a[ax] else 1.0
                t = min(t, tt)
        return a + (b - a) * t

    for i in range(len(p)):
        if inside[i]:
            if cur is None:
                cur = ([], [], [])
                if i > 0:
                    cur[0].append(cut(p[i], p[i - 1]))
                    cur[1].append(kind[i])
                    cur[2].append(elec[i])
            cur[0].append(p[i])
            cur[1].append(kind[i])
            cur[2].append(elec[i])
        elif cur is not None:
            cur[0].append(cut(p[i - 1], p[i]))
            cur[1].append(kind[i - 1])
            cur[2].append(elec[i - 1])
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return [(np.array(a), np.array(k), np.array(e)) for a, k, e in out if len(a) >= 2]


def frames(p):
    """点ごとの水平の進む向き t と左向き n (UE の m)。"""
    d = np.gradient(p[:, :2], axis=0)
    t = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    n = np.c_[-t[:, 1], t[:, 0]]
    return t, n


class Track:
    """タイルの中の線路 1 本 (UE の m)。"""

    def __init__(self, p_cm, kind, elec, line):
        self.p = p_cm / 100.0
        self.kind, self.elec, self.line = kind, elec.astype(bool), line
        self.t, self.n = frames(self.p)
        self.s = np.r_[0, np.cumsum(np.hypot(*np.diff(self.p[:, :2], axis=0).T))]
        self.gauge = float(line.get("gauge_m", 1.067))
        self.crossing = np.zeros(len(self.p), bool)

    def at(self, s):
        """道に沿った距離 s の点 (x, y, 道床 z) と t, n。"""
        s = float(np.clip(s, 0, self.s[-1]))
        i = int(np.clip(np.searchsorted(self.s, s) - 1, 0, len(self.s) - 2))
        f = (s - self.s[i]) / max(self.s[i + 1] - self.s[i], 1e-9)
        q = self.p[i] + (self.p[i + 1] - self.p[i]) * f
        t = self.p[i + 1, :2] - self.p[i, :2]
        t = t / max(np.linalg.norm(t), 1e-9)
        return q, t, np.array([-t[1], t[0]]), i

    def nearest(self, xy):
        a, b = self.p[:-1, :2], self.p[1:, :2]
        ab = b - a
        u = np.clip(((xy - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
        c = a + ab * u[:, None]
        d = np.hypot(*(c - xy).T)
        i = int(np.argmin(d))
        return float(d[i]), float(self.s[i] + u[i] * np.hypot(*ab[i])), i


def track_dist(xy, tracks, skip_tunnels=True):
    """点 xy (P,2) m から、いちばん近い線路の中心線までの距離 (P,)。"""
    xy = np.atleast_2d(np.asarray(xy, float))
    best = np.full(len(xy), 1e9)
    for tr in tracks:
        a, b = tr.p[:-1, :2], tr.p[1:, :2]
        if skip_tunnels:
            keep = (tr.kind[:-1] != 2) | (tr.kind[1:] != 2)
            a, b = a[keep], b[keep]
        if not len(a):
            continue
        ab = b - a
        for k in range(0, len(xy), 256):
            q = xy[k:k + 256, None, :]
            u = np.clip(((q - a) * ab).sum(2) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
            d = np.hypot(*(a + ab * u[..., None] - q).transpose(2, 0, 1)).min(1)
            best[k:k + 256] = np.minimum(best[k:k + 256], d)
    return best


def tracks_in_tile(doc, half_cm):
    out = []
    for line in doc["lines"]:
        p = np.array(line["points_cm"], float)
        for q, k, e in clip_runs(p, np.array(line["kind"]), np.array(line.get("electrified", [0] * len(p))), half_cm):
            out.append(Track(q, k, e, line))
    return out


def rail_roads(tracks, bridges=True):
    """木・花・建物をよける範囲 (道路と同じ形の辞書、stamp_roads と place_buildings に渡す)。"""
    out = []
    for tr in tracks:
        ok = tr.kind != 2 if bridges else tr.kind == 0
        i = 0
        while i < len(ok):
            if not ok[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(ok) and ok[j + 1]:
                j += 1
            if j > i:
                out.append({"points_cm": (tr.p[i:j + 1] * 100).tolist(), "width_cm": BED_HALF_M * 200 + 100,
                            "priority": 99, "bridge": False, "tunnel": False, "highway": "railway"})
            i = j + 1
    return out


def mark_crossings(tracks, grid, roads, stamp_roads):
    """道路 (橋・トンネルでない) の上にある線路の点を踏切にする。"""
    flat = [r for r in roads if not r.get("bridge") and not r.get("tunnel")]
    if not flat:
        return
    mask = stamp_roads(grid, flat, 0.5, CROSSING_EXTRA_M)
    n = mask.shape[0]
    for tr in tracks:
        ci = ((tr.p[:, 0] * 100 + grid.half_cm) / 50).astype(int)
        ri = ((tr.p[:, 1] * 100 + grid.half_cm) / 50).astype(int)
        ok = (ci >= 0) & (ri >= 0) & (ci < n) & (ri < n)
        hit = np.zeros(len(tr.p), bool)
        hit[ok] = mask[ri[ok], ci[ok]]
        tr.crossing = hit & (tr.kind == 0)


# ---------------------------------------------------------------- 駅
def plan_stations(doc, tracks, grid, roads, stamp_roads):
    """駅ごとのホーム [{name, kind, path (K,3) m (ホームの中心線、z は上面), width, track_side (+1/-1/0)}] と駅の点。"""
    if not tracks:
        return []
    road_mask = stamp_roads(grid, [r for r in roads if not r.get("bridge") and not r.get("tunnel")], 1.0, 0.5)
    n = road_mask.shape[0]

    def on_road(xy):
        c = (xy[:, 0] + grid.half_cm / 100).astype(int)
        r = (xy[:, 1] + grid.half_cm / 100).astype(int)
        ok = (c >= 0) & (r >= 0) & (c < n) & (r < n)
        out = np.ones(len(xy), bool)
        out[ok] = road_mask[r[ok], c[ok]]
        return out

    def rail_top_near(xy):
        best = None
        for tr in tracks:
            d, s, i = tr.nearest(xy[None, :])
            if tr.kind[i] != 2 and (best is None or d < best[0]):
                best = (d, tr.at(s)[0][2] + RAIL_TOP_M, tr)
        return best

    osm_pl = []
    for pl in doc.get("platforms", []):
        pts = np.array(pl["pts_m"], float)
        if len(pts) < 2:
            continue
        if pl["area"] and len(pts) >= 4:
            poly = clean_poly(pts)
            if poly is None:
                continue
            c, a, la, lb = min_rect(poly)
            if la < 8 or lb < 1.2:
                continue
            path = np.array([c - a * la / 2, c + a * la / 2])
            width = float(np.clip(lb, 2.0, 12.0))
        else:
            path = pts
            try:
                width = float(str(pl.get("width_m") or PLATFORM_W_M).replace("m", ""))
            except ValueError:
                width = PLATFORM_W_M
        osm_pl.append((path, width))

    plans, used_osm = [], set()
    for st in doc.get("stations", []):
        pos = np.array(st["pos_m"], float)
        near = rail_top_near(pos)
        if near is None or near[0] > STATION_TRACK_M:
            print(f"  駅: {st['name'] or '(名前なし)'} の近くに地上の線路が無いので作りません")
            continue
        mine = []
        for k, (path, width) in enumerate(osm_pl):
            if k in used_osm:
                continue
            c = path.mean(0)
            if np.hypot(*(c - pos)) < 250:
                mine.append(k)
        made = []
        for k in mine:
            path, width = osm_pl[k]
            path = densify2(path, 3.0)
            d = track_dist(path, tracks)
            if np.median(d) < width / 2 + 0.6:  # ホームの線が線路の上 (縁の線など) は使わない
                continue
            half = float(min(width / 2, np.median(d) - PLATFORM_EDGE_M))
            if half < 0.9:
                continue
            z = np.array([rail_top_near(q)[1] for q in path]) + PLATFORM_ABOVE_RAIL_M
            made.append({"path": np.c_[path, z], "width": 2 * half, "sides": None})
            used_osm.add(k)
        if not made:
            made = generated_platforms(st, pos, tracks, on_road)
        if not made:
            print(f"  駅: {st['name'] or '(名前なし)'} はホームを置く場所 (道路や踏切にかからない線路沿い) が無いので作りません")
        if made:
            plans.append({"name": st["name"], "kind": st["kind"], "pos": pos, "platforms": made,
                          "osm": st["osm"]})
    for pl in plans:
        for p in pl["platforms"]:
            p["sides"] = edge_sides(p, tracks) if p["sides"] is None else p["sides"]
    return plans


def densify2(path, step):
    out = [path[0]]
    for a, b in zip(path[:-1], path[1:]):
        m = max(1, int(math.ceil(np.hypot(*(b - a)) / step)))
        out += [a + (b - a) * j / m for j in range(1, m + 1)]
    return np.array(out)


def edge_sides(pl, tracks):
    """ホームの左右 (+1 = 進む向きの左) のどちらが線路に面しているか。点字ブロックをその縁に付ける。"""
    path = pl["path"]
    t, n = frames(path)
    out = []
    for side in (1, -1):
        q = path[:, :2] + n * side * (pl["width"] / 2 + PLATFORM_EDGE_M)
        if track_dist(q, tracks).min() < 1.2:
            out.append(side)
    return out or [1, -1]


def generated_platforms(st, pos, tracks, on_road):
    """OSM にホームが無い駅: いちばん近い線路の外側に、線路に沿ったホーム (複線なら両側)。"""
    best = None
    for tr in tracks:
        d, s, i = tr.nearest(pos[None, :])
        if tr.kind[i] != 2 and (best is None or d < best[0]):
            best = (d, s, tr)
    _, s0, tr = best
    q, t, nrm, _ = tr.at(s0)
    # 近くの平行な線路の、この線路からの横のずれ
    offs = [0.0]
    for other in tracks:
        if other is tr:
            continue
        d, so, i = other.nearest(q[None, :2])
        if d < 14.0 and other.kind[i] != 2:
            qo = other.at(so)[0]
            offs.append(float((qo[:2] - q[:2]) @ nrm))
    side_st = float((pos - q[:2]) @ nrm)
    sides = [1 if side_st >= 0 else -1]
    if len(set(round(o) for o in offs)) >= 2:
        sides.append(-sides[0])
    length = PLATFORM_LEN_M.get(st["kind"], 70.0)
    out = []
    for sd in sides:
        edge = max(offs) if sd > 0 else min(offs)
        off = edge + sd * (PLATFORM_EDGE_M + PLATFORM_W_M / 2)
        ss = np.arange(s0 - length / 2, s0 + length / 2 + 1e-6, 3.0)
        ss = ss[(ss >= 0) & (ss <= tr.s[-1])]
        if len(ss) < 4:
            continue
        pts = []
        for s in ss:
            qq, _, nn, i = tr.at(s)
            pts.append([qq[0] + nn[0] * off, qq[1] + nn[1] * off, qq[2] + RAIL_TOP_M + PLATFORM_ABOVE_RAIL_M, tr.kind[i]])
        pts = np.array(pts)
        # 踏切・道路・トンネルにかかる端は切る
        bad = on_road(pts[:, :2]) | (pts[:, 3] == 2)
        good = np.flatnonzero(~bad)
        if len(good) < 2:
            continue
        runs = np.split(good, np.flatnonzero(np.diff(good) > 1) + 1)
        run = max(runs, key=len)
        if len(run) * 3.0 < 24.0:
            continue
        out.append({"path": pts[run, :3], "width": PLATFORM_W_M, "sides": [-sd]})
    return out


def station_footprints(plans, footprints, doc, tracks):
    """駅舎: 駅の近くの建物に駅の見た目を付ける。無ければ線路沿いに建てる (footprints に足す)。
    ホームの上の建物 (上屋の輪郭) は除く。足した・付けた駅舎の数を返す。"""
    if not plans:
        return 0
    centers = np.array([p.mean(0) for p, _, _ in footprints]) if footprints else np.zeros((0, 2))
    drop = np.zeros(len(footprints), bool)
    for pl in plans:
        for p in pl["platforms"]:
            if len(centers):
                d = np.hypot(*(densify2(p["path"][:, :2], 1.0)[None] - centers[:, None]).transpose(2, 0, 1)).min(1)
                drop |= d < p["width"] / 2 + 1.0
    if len(centers):
        drop |= track_dist(centers, tracks) < BED_HALF_M + 0.5
    kept = [f for f, d in zip(footprints, drop) if not d]
    footprints[:] = kept
    centers = np.array([p.mean(0) for p, _, _ in footprints]) if footprints else np.zeros((0, 2))
    count = 0
    for pl in plans:
        pos = pl["pos"]
        hit = None
        if len(centers):
            d = np.hypot(*(centers - pos).T)
            for j in np.argsort(d)[:12]:
                tags = footprints[j][1]
                if tags.get("building") == "train_station" and d[j] < 120:
                    hit = j
                    break
            if hit is None:   # 駅の点にいちばん近い、駅舎らしい大きさの建物 (線路の上の建物は除いてある)
                for j in np.argsort(d)[:6]:
                    a = abs(signed_area(np.asarray(footprints[j][0], float))) if len(footprints[j][0]) >= 3 else 0
                    if d[j] < STATION_BUILDING_M and 30 <= a <= 2500:
                        hit = j
                        break
        if hit is not None:
            footprints[hit][1]["_look"] = "station"
            footprints[hit][1].setdefault("name", pl["name"])
            count += 1
            continue
        # 線路沿いに建てる: いちばん長いホームの外側
        p = max(pl["platforms"], key=lambda p: len(p["path"]))
        path = p["path"]
        mid = path[len(path) // 2, :2]
        t, nrm = frames(path)
        t, nrm = t[len(path) // 2], nrm[len(path) // 2]
        away = 1 if -1 in p["sides"] and 1 not in p["sides"] else -1 if 1 in p["sides"] and -1 not in p["sides"] else 1
        c = mid + nrm * away * (p["width"] / 2 + 5.0)
        w, d_ = 13.0, 7.0
        poly = np.array([c + t * sx * w / 2 + nrm * sy * d_ / 2 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        if signed_area(poly) < 0:
            poly = poly[::-1]
        footprints.append((poly, {"building": "train_station", "_look": "station", "building:levels": "1",
                                  "name": pl["name"]}, "railway"))
        count += 1
    return count


# ---------------------------------------------------------------- 形をつくる
def ribbon(path, profile_pts, n=None):
    """path (K,3) に沿って、断面 profile_pts [(横 (+左), 上)] を流した閉じた形。n は左向き (K,2)。"""
    if n is None:
        _, n = frames(path)
    rings = []
    for p, nn in zip(path, n):
        rings.append([[p[0] + nn[0] * a, p[1] + nn[1] * a, p[2] + b] for a, b in profile_pts])
    return sm.sweep(rings)


def offset_path(path, n, off, dz=0.0):
    return np.c_[path[:, 0] + n[:, 0] * off, path[:, 1] + n[:, 1] * off, path[:, 2] + dz]


def runs_of(mask):
    i = 0
    out = []
    while i < len(mask):
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(mask) and mask[j + 1]:
            j += 1
        out.append((i, j))
        i = j + 1
    return out


def font():
    for f in FONT_FILES:
        if os.path.exists(f):
            return f
    return None


def sign_texture(name, line_name, path):
    """駅名標の絵 (白地に駅名、下に青い帯と路線名)。フォントが無ければ False。"""
    f = font()
    if f is None or not name:
        return False
    w, h = 1024, int(1024 * SIGN_H_M / SIGN_W_M)
    img = Image.new("RGB", (w, h), (238, 238, 232))
    d = ImageDraw.Draw(img)
    size = 190
    while size > 40:
        big = ImageFont.truetype(f, size)
        box = d.textbbox((0, 0), name, font=big)
        if box[2] - box[0] <= w * 0.86:
            break
        size -= 10
    box = d.textbbox((0, 0), name, font=big)
    d.text(((w - (box[2] - box[0])) / 2 - box[0], h * 0.36 - (box[3] - box[1]) / 2 - box[1]), name, fill=(20, 20, 20), font=big)
    d.rectangle((0, int(h * 0.72), w, int(h * 0.9)), fill=(10, 60, 150))
    if line_name:
        small = ImageFont.truetype(f, int(h * 0.11))
        box = d.textbbox((0, 0), line_name, font=small)
        d.text(((w - (box[2] - box[0])) / 2 - box[0], h * 0.81 - (box[3] - box[1]) / 2 - box[1]), line_name,
               fill=(245, 245, 245), font=small)
    img.save(path)
    return True


def place(tracks, plans, grid, roads, out_dir=None):
    """線路と駅の形と置き場所。(instances, world meshes {名前: Mesh}, lights, 数の記録)
    out_dir があれば、駅名標の絵 (T_FD_StationSign_*.png) をそこに書き、マテリアルを scenery_meshes.MATERIALS に足す。"""
    track = sm.Mesh("SM_FD_Railway", flat=True)
    wires = sm.Mesh("SM_FD_RailWires", flat=True)
    station = sm.Mesh("SM_FD_RailStations", flat=True)
    inst, lights = {}, {}
    stats = {"線路 km": 0.0, "踏切": 0, "鉄橋・高架 m": 0.0, "トンネルの入口": 0, "架線柱": 0, "駅": len(plans)}

    def put(name, p, yaw, scale=1.0, pitch=0.0):
        it = [round(float(p[0] * 100), 1), round(float(p[1] * 100), 1), round(float(p[2] * 100), 1),
              round(float(yaw) % 360, 2), round(float(scale), 3)]
        if pitch:
            it.append(round(float(pitch), 2))
        inst.setdefault(name, []).append(it)

    def ground_z(x, y, fallback):
        z = grid.height_m(np.array([x * 100]), np.array([y * 100]))[0]
        return fallback if np.isnan(z) else float(z)

    for tr in tracks:
        p, n = tr.p, tr.n
        vis = tr.kind != 2
        stats["線路 km"] += float(np.hypot(*np.diff(p[vis][:, :2], axis=0).T).sum()) / 1000 if vis.sum() > 1 else 0
        half_g = tr.gauge / 2 + 0.035
        sleeper = "SM_FD_RailSleeperWide" if tr.gauge > 1.3 else "SM_FD_RailSleeper"
        for i, j in runs_of(vis):
            seg = slice(max(i - (1 if i > 0 and tr.kind[i - 1] == 2 else 0), 0), j + 1)
            q, nn = p[seg], n[seg]
            if len(q) < 2:
                continue
            for side in (-1, 1):  # レール
                track.add("FD_Rail", *sm.swept_rect(offset_path(q, nn, side * half_g, RAIL_TOP_M - RAIL_H_M / 2), 0.075, RAIL_H_M))
            kind, cross = tr.kind[seg], tr.crossing[seg]
            # バラスト (踏切の所は除く)
            for a, b in runs_of(~cross):
                if b > a:
                    track.add("FD_Ballast", *ribbon(q[a:b + 1], [(-2.0, -0.45), (2.0, -0.45), (1.45, BALLAST_TOP_M),
                                                                 (-1.45, BALLAST_TOP_M)], nn[a:b + 1]))
            # 踏切の板と警報機
            for a, b in runs_of(cross):
                a0, b1 = max(a - 1, 0), min(b + 1, len(q) - 1)
                track.add("FD_CrossingPanel", *ribbon(q[a0:b1 + 1], [(-1.6, 0.0), (1.6, 0.0), (1.6, RAIL_TOP_M - 0.012),
                                                                    (-1.6, RAIL_TOP_M - 0.012)], nn[a0:b1 + 1]))
                c = q[(a + b) // 2]
                t = q[min(b1, len(q) - 1), :2] - q[a0, :2]
                t = t / max(np.linalg.norm(t), 1e-9)
                nrm = np.array([-t[1], t[0]])
                span = max(np.hypot(*(q[b1, :2] - q[a0, :2])) / 2 + 1.0, 3.0)
                for sd in (1, -1):
                    pos = c[:2] + nrm * sd * 3.4 + t * sd * span
                    zg = ground_z(*pos, c[2])
                    # 警報機は道路 (線路と直角) を走ってくる車の方を向く
                    yaw = math.degrees(math.atan2(nrm[1] * sd, nrm[0] * sd))
                    put("SM_FD_RailCrossingSignal", (pos[0], pos[1], zg - 0.05), yaw)
                stats["踏切"] += 1
            # 枕木
            ss = np.arange(SLEEPER_SPACING_M / 2, tr.s[seg][-1] - tr.s[seg][0], SLEEPER_SPACING_M)
            s_base = tr.s[seg][0]
            for s in ss:
                qq, t, _, k = tr.at(s_base + s)
                if tr.crossing[k] or tr.kind[k] == 2:
                    continue
                dz = (tr.p[k + 1, 2] - tr.p[k, 2]) / max(tr.s[k + 1] - tr.s[k], 1e-6)
                put(sleeper, (qq[0], qq[1], qq[2] + SLEEPER_TOP_M - 0.16), math.degrees(math.atan2(t[1], t[0])),
                    1.0, math.degrees(math.atan(dz)))
            # 鉄橋・高架: 桁、側壁、橋脚
            for a, b in runs_of(kind == 1):
                a0, b1 = max(a - 1, 0), min(b + 1, len(q) - 1)
                qq, nb = q[a0:b1 + 1], nn[a0:b1 + 1]
                track.add("FD_BridgeConcrete", *ribbon(qq, [(-2.5, -1.3), (2.5, -1.3), (2.5, -0.05), (-2.5, -0.05)], nb))
                for sd in (-1, 1):
                    track.add("FD_BridgeConcrete", *ribbon(qq, [(sd * 2.35, -0.1), (sd * 2.55, -0.1), (sd * 2.55, 1.15),
                                                                (sd * 2.35, 1.15)], nb))
                length = float(tr.s[seg][b1] - tr.s[seg][a0])
                stats["鉄橋・高架 m"] += length
                for s in np.arange(10.0, length - 5.0, 22.0):
                    qp, t, _, _ = tr.at(tr.s[seg][a0] + s)
                    zg = ground_z(qp[0], qp[1], qp[2] - 8)
                    top = qp[2] - 1.3
                    if top - max(zg, -6.0) < 1.0:
                        continue
                    yaw = math.degrees(math.atan2(t[1], t[0]))
                    bottom = min(zg, 0.0) - 1.5 if zg < 0.3 else zg - 1.0
                    track.add("FD_BridgeConcrete", *sm.box((qp[0], qp[1], (top + bottom) / 2), (1.6, 3.6, top - bottom), yaw))
                    track.add("FD_BridgeConcrete", *sm.box((qp[0], qp[1], top - 0.4), (2.2, 5.2, 0.8), yaw))
            # 架線 (電化された所)
            el = tr.elec[seg] & vis[seg]
            for a, b in runs_of(el):
                if b - a < 2:
                    continue
                qq, nb = q[a:b + 1], nn[a:b + 1]
                wires.add("FD_Wire", *sm.swept_rect(offset_path(qq, nb, 0.0, RAIL_TOP_M + CONTACT_WIRE_M), 0.025, 0.025))
                wires.add("FD_Wire", *sm.swept_rect(offset_path(qq, nb, 0.0, RAIL_TOP_M + MESSENGER_M), 0.03, 0.03))
                length = float(tr.s[seg][b] - tr.s[seg][a])
                for s in np.arange(CATENARY_SPACING_M / 2, length, CATENARY_SPACING_M):
                    qp, t, nrm, k = tr.at(tr.s[seg][a] + s)
                    if tr.crossing[k]:
                        continue
                    pos = qp[:2] + nrm * (2.45 if tr.kind[k] == 1 else CATENARY_OFFSET_M)   # 橋は桁の端に立てる
                    v = -nrm   # 腕は線路の方 (柱から見て -n) へ伸びる。形の腕は -Y 向き
                    yaw = math.degrees(math.atan2(v[0], -v[1]))
                    put("SM_FD_RailCatenaryPole", (pos[0], pos[1], qp[2] - 0.3), yaw)
                    stats["架線柱"] += 1
        # トンネルの入口
        for i in range(1, len(tr.kind)):
            if (tr.kind[i] == 2) != (tr.kind[i - 1] == 2):
                k = i - 1 if tr.kind[i] == 2 else i   # 地上の側の点
                inward = (tr.p[i, :2] - tr.p[i - 1, :2]) * (1 if tr.kind[i] == 2 else -1)
                inward = inward / max(np.linalg.norm(inward), 1e-9)
                q = tr.p[k]
                yaw = math.degrees(math.atan2(inward[1], inward[0]))
                put("SM_FD_RailTunnelPortal", (q[0], q[1], q[2] - 0.5), yaw)
                stats["トンネルの入口"] += 1

    for pl in plans:
        sign = None
        if out_dir:
            key = re.sub(r"[^0-9A-Za-z]", "_", pl["osm"])
            tex = f"T_FD_StationSign_{key}.png"
            line_name = next((tr.line.get("name", "") for tr in tracks if tr.nearest(pl["pos"][None])[0] < STATION_TRACK_M), "")
            if sign_texture(pl["name"], line_name, os.path.join(out_dir, tex)):
                sign = f"FD_StationSign_{key}"
                sm.MATERIALS[sign] = dict(color=(1, 1, 1), roughness=0.5, texture=tex)
        for p in pl["platforms"]:
            platform(station, p, grid, lights, put, sign)
        print(f"  駅: {pl['name'] or '(名前なし)'} (ホーム {len(pl['platforms'])})")
    stats["線路 km"] = round(stats["線路 km"], 2)
    stats["鉄橋・高架 m"] = round(stats["鉄橋・高架 m"])
    world = {m.name: m for m in (track, wires, station) if m.parts}
    return inst, world, lights, stats


def platform(mesh, p, grid, lights, put, sign=None):
    """ホーム 1 本: 側壁と上面、点字ブロック、上屋、ベンチ、駅名標、灯り、端のスロープ。"""
    path = p["path"]
    w = p["width"]
    t, n = frames(path)
    top = path[:, 2]
    zg = grid.height_m(path[:, 0] * 100, path[:, 1] * 100)
    zg = np.where(np.isnan(zg), top - 1.5, zg)
    rel = min(float((zg - top).min()) - 0.6, -1.5)
    mesh.add("FD_PlatformWall", *ribbon(np.c_[path[:, :2], top], [(-w / 2, rel), (w / 2, rel), (w / 2, -0.06), (-w / 2, -0.06)], n))
    mesh.add("FD_PlatformTop", *ribbon(np.c_[path[:, :2], top], [(-w / 2 + 0.05, -0.1), (w / 2 - 0.05, -0.1),
                                                                (w / 2 - 0.05, 0.0), (-w / 2 + 0.05, 0.0)], n))
    for sd in p["sides"]:
        e = sd * (w / 2)
        mesh.add("FD_PlatformEdge", *ribbon(np.c_[path[:, :2], top], [(e - 0.25 * sd, -0.05), (e, -0.05), (e, 0.012),
                                                                     (e - 0.25 * sd, 0.012)], n))
        y0 = e - sd * 0.85
        mesh.add("FD_TactileYellow", *ribbon(np.c_[path[:, :2], top], [(y0 - 0.15, -0.05), (y0 + 0.15, -0.05),
                                                                      (y0 + 0.15, 0.015), (y0 - 0.15, 0.015)], n))
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(path[:, :2], axis=0).T))]
    L = s[-1]
    at = lambda u: (np.array([np.interp(u, s, path[:, 0]), np.interp(u, s, path[:, 1]), np.interp(u, s, top)]),
                    math.degrees(math.atan2(np.interp(u, s, t[:, 1]), np.interp(u, s, t[:, 0]))))
    # 上屋 (真ん中の 4 割、1 本柱の屋根)
    r0, r1 = L * 0.3, L * 0.7
    if r1 - r0 >= 10:
        k = (s >= r0) & (s <= r1)
        roof = np.c_[path[k, :2], top[k] + 3.3]
        if len(roof) >= 2:
            mesh.add("FD_StationRoof", *ribbon(roof, [(-w / 2 + 0.15, 0.0), (w / 2 - 0.15, 0.0), (w / 2 - 0.15, 0.14),
                                                     (-w / 2 + 0.15, 0.14)], n[k]))
        for u in np.arange(r0 + 2.0, r1 - 1.0, 6.0):
            q, yaw = at(u)
            mesh.add("FD_StationPost", *sm.cylinder((q[0], q[1], q[2] - 0.05), (q[0], q[1], q[2] + 3.3), 0.11, n=8))
            mesh.add("FD_StationPost", *sm.box((q[0], q[1], q[2] + 3.22), (0.3, w - 0.6, 0.16), yaw))
            lights.setdefault("station", []).append([round(float(q[0] * 100), 1), round(float(q[1] * 100), 1),
                                                     round(float((q[2] + 3.05) * 100), 1), round(yaw, 1), -90.0])
            mesh.add("FD_LampGlow", *sm.box((q[0], q[1], q[2] + 3.08), (1.2, 0.18, 0.06), yaw))
        for u in (r0 + 5.0, r1 - 5.0):   # ベンチ
            q, yaw = at(u)
            mesh.add("FD_StationBench", *sm.box((q[0], q[1], q[2] + 0.42), (1.8, 0.42, 0.06), yaw))
            mesh.add("FD_StationBench", *sm.box((q[0], q[1], q[2] + 0.2), (1.6, 0.3, 0.4), yaw))
    # 上屋の外の灯り
    for u in np.r_[np.arange(4.0, r0 - 2.0, 14.0), np.arange(r1 + 4.0, L - 2.0, 14.0)]:
        q, yaw = at(u)
        mesh.add("FD_StationPost", *sm.cylinder((q[0], q[1], q[2] - 0.05), (q[0], q[1], q[2] + 3.6), 0.06, n=8))
        mesh.add("FD_LampGlow", *sm.box((q[0], q[1], q[2] + 3.6), (0.9, 0.16, 0.08), yaw))
        lights.setdefault("station", []).append([round(float(q[0] * 100), 1), round(float(q[1] * 100), 1),
                                                 round(float((q[2] + 3.5) * 100), 1), round(yaw, 1), -90.0])
    # 駅名標 (線路の方を向いた板)
    for u in (L * 0.2, L * 0.82):
        q, yaw = at(u)
        for dy in (-0.75, 0.75):
            pp = q[:2] + np.array([math.cos(math.radians(yaw)), math.sin(math.radians(yaw))]) * dy
            mesh.add("FD_StationPost", *sm.cylinder((pp[0], pp[1], q[2] - 0.05), (pp[0], pp[1], q[2] + 2.5), 0.04, n=6))
        mesh.add("FD_SignWhite", *sm.box((q[0], q[1], q[2] + 2.05), (SIGN_W_M, 0.06, SIGN_H_M), yaw))
        if sign:
            sign_faces(mesh, sign, np.array([q[0], q[1], q[2] + 2.05]), math.radians(yaw))
        else:
            mesh.add("FD_SignBlue", *sm.box((q[0], q[1], q[2] + 1.72), (1.92, 0.08, 0.16), yaw))
    # 端のスロープ (線路と同じ向きに地面へ下りる)
    for end, sgn in ((0, -1), (len(path) - 1, 1)):
        q = np.array([path[end, 0], path[end, 1], top[end]])
        tt = t[end] * sgn
        g = grid.height_m(np.array([(q[0] + tt[0] * 8) * 100]), np.array([(q[1] + tt[1] * 8) * 100]))[0]
        if np.isnan(g) or q[2] - g > 2.5 or q[2] - g < 0.2:
            continue
        run = max((q[2] - g) / 0.12, 1.0)
        if run > 14.0:
            continue
        ramp = np.array([q, q + np.r_[tt * run, g - q[2]]])
        ramp[:, 2] = [q[2], g + 0.02]
        mesh.add("FD_PlatformTop", *ribbon(ramp, [(-0.9, -0.6), (0.9, -0.6), (0.9, 0.0), (-0.9, 0.0)],
                                           np.repeat(n[end][None], 2, 0)))


def sign_faces(mesh, material, c, yaw):
    """駅名標の表と裏の面 (絵を貼る)。板は yaw の向きに長く、面は横 (線路の方) を向く。"""
    t = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    for nrm in (np.array([-t[1], t[0], 0.0]), np.array([t[1], -t[0], 0.0])):
        # 見る人の右 (UE は左手系: 右 = 上 x 前、前 = -nrm)
        right = np.cross(up, -nrm)
        o = c + nrm * 0.032
        v = np.array([o - right * SIGN_W_M / 2 + up * SIGN_H_M / 2, o + right * SIGN_W_M / 2 + up * SIGN_H_M / 2,
                      o + right * SIGN_W_M / 2 - up * SIGN_H_M / 2, o - right * SIGN_W_M / 2 - up * SIGN_H_M / 2])
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        mesh.add_cards(material, v, np.array([[0, 1, 2], [0, 2, 3]]), np.repeat(nrm[None], 4, 0), uv, np.ones(4),
                       orient=True)


# ---------------------------------------------------------------- 部品の形 (原点は地面)
def sleeper(width):
    """枕木 (コンクリート)。+X が線路の向き。原点は下の真ん中。"""
    m = sm.Mesh("SM_FD_RailSleeperWide" if width > 2.2 else "SM_FD_RailSleeper")
    m.add("FD_Sleeper", *sm.box((0, 0, 0.08), (0.22, width, 0.16)))
    return m


def crossing_signal():
    """踏切警報機と遮断機 (上げた所)。+X が道路の車の方。原点は根元。"""
    m = sm.Mesh("SM_FD_RailCrossingSignal")
    for k in range(8):  # 黄と黒のしま模様の柱
        m.add("FD_SignYellow" if k % 2 == 0 else "FD_SignBlack",
              *sm.cylinder((0, 0, -0.2 + k * 0.32), (0, 0, -0.2 + (k + 1) * 0.32), 0.075, n=10))
    m.add("FD_SignBlack", *sm.cylinder((0, 0, 2.36), (0, 0, 3.6), 0.06, n=8))
    for sgn in (-1, 1):  # ×の踏切の標識
        a = math.radians(30 * sgn)
        p0 = np.array([0.06, -0.7 * math.cos(a), 3.25 - 0.7 * math.sin(a)])
        p1 = np.array([0.06, 0.7 * math.cos(a), 3.25 + 0.7 * math.sin(a)])
        m.add("FD_SignYellow", *sm.swept_rect(np.array([p0, (p0 + p1) / 2, p1]), 0.03, 0.2))
    m.add("FD_SignBlack", *sm.box((0.1, 0, 2.55), (0.08, 0.95, 0.12)))
    for y in (-0.38, 0.38):  # 赤い灯
        m.add("FD_SignBlack", *sm.cylinder((0.02, y, 2.55), (0.08, y, 2.55), 0.2, n=12))
        m.add("FD_SignRed", *sm.cylinder((0.1, y, 2.55), (0.22, y, 2.55), 0.13, n=12))
    m.add("FD_SignBlack", *sm.box((-0.05, 0.35, 1.1), (0.35, 0.3, 0.45)))   # 遮断機の箱
    for k in range(6):  # 上げた遮断かん (黄と黒)
        m.add("FD_SignYellow" if k % 2 == 0 else "FD_SignBlack",
              *sm.cylinder((-0.05, 0.55, 1.2 + k * 0.6), (-0.05, 0.55, 1.2 + (k + 1) * 0.6), 0.04, n=6))
    return m


def catenary_pole():
    """架線柱 (コンクリートの柱と、線路の上へ伸びる鉄の腕)。腕は -Y の向き。原点は根元 (道床の少し下)。"""
    m = sm.Mesh("SM_FD_RailCatenaryPole")
    m.add("FD_PoleConcrete", *sm.cylinder((0, 0, -6.0), (0, 0, 7.4), 0.17, 0.12, n=10))   # 盛土でも地面に届く
    top = 0.3 + RAIL_TOP_M
    m.add("FD_Steel", *sm.box((0, -1.7, top + MESSENGER_M + 0.15), (0.1, 3.6, 0.1)))   # ちょう架線の腕
    m.add("FD_Steel", *sm.cylinder((0, -0.1, top + CONTACT_WIRE_M + 0.25), (0, -CATENARY_OFFSET_M, top + CONTACT_WIRE_M + 0.05),
                                   0.03, n=6))
    m.add("FD_Steel", *sm.cylinder((0, -0.1, top + MESSENGER_M - 0.4), (0, -2.0, top + MESSENGER_M + 0.1), 0.025, n=6))
    m.add("FD_Insulator", *sm.cylinder((0, -CATENARY_OFFSET_M, top + MESSENGER_M + 0.1), (0, -CATENARY_OFFSET_M, top + MESSENGER_M - 0.05),
                                       0.06, n=8))
    m.add("FD_Wire", *sm.cylinder((0, -CATENARY_OFFSET_M, top + MESSENGER_M), (0, -CATENARY_OFFSET_M, top + CONTACT_WIRE_M),
                                  0.012, n=4))
    return m


def tunnel_portal():
    """トンネルの入口 (コンクリートの坑門と暗い坑口)。+X がトンネルの奥。原点は道床。"""
    m = sm.Mesh("SM_FD_RailTunnelPortal")
    c = "FD_BridgeConcrete"
    for sd in (-1, 1):
        m.add(c, *sm.box((0.6, sd * 3.6, 3.0), (1.6, 2.6, 8.0)))
    m.add(c, *sm.box((0.6, 0, 6.8), (1.6, 4.8, 2.4)))
    m.add(c, *sm.box((0.4, 0, 8.25), (2.0, 10.4, 0.5)))
    # 坑口のアーチ (上の角を埋める)
    for sd in (-1, 1):
        m.add(c, *sm.box((0.6, sd * 2.05, 5.35), (1.6, 0.6, 0.7)))
    m.add("FD_TunnelDark", *sm.box((2.2, 0, 2.4), (1.6, 4.8, 6.6)))
    return m


def meshes(names):
    make = {"SM_FD_RailSleeper": lambda: sleeper(2.0), "SM_FD_RailSleeperWide": lambda: sleeper(2.4),
            "SM_FD_RailCrossingSignal": crossing_signal, "SM_FD_RailCatenaryPole": catenary_pole,
            "SM_FD_RailTunnelPortal": tunnel_portal}
    return {k: make[k]() for k in names if k in make}


CULL_CM = {"SM_FD_RailSleeper": 35000, "SM_FD_RailSleeperWide": 35000}
