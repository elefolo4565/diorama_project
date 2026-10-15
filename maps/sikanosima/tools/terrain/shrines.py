"""神社 (鳥居・参道・灯籠・狛犬・手水舎・拝殿・本殿・玉垣・鎮守の森)。build_scenery.py から呼ぶ。

神社の場所
- OSM の amenity=place_of_worship (religion=shinto、または名前が神社・宮・稲荷・八幡・天満など) の点と、
  building=shrine の建物の輪郭 (拝殿・本殿)、境内の範囲 (landuse=religious) を osm_shrines.json に取る
  (取れないときは osm_pois.json と osm_buildings.json の中の神社を使う)
- 45m 以内の点はひとつの神社にまとめる (末社・遙拝所など)。寺・教会は除く

規模 (境内の広さ、無ければ建物の輪郭の広さと名前で決める)
- 祠: 名前の無い小さな神社。小さな社と小さな鳥居
- 村の神社: 鳥居 (石)・参道・灯籠・狛犬・手水舎・拝殿・本殿・本殿を囲む玉垣・鎮守の森
- 大きな神社 (境内 5000m2 以上、拝殿と本殿の輪郭が広い、名前が大社・神宮・八幡宮・天満宮): 朱の大鳥居と二の鳥居、
  灯籠の並ぶ長い参道、神門、社務所、拝殿と本殿を囲む玉垣、広い鎮守の森

並べ方
- 参道の向き: 本殿と拝殿の輪郭があれば本殿から拝殿の向きの反対、無ければいちばん近い道路から神社へ向かう向き
- 鳥居は道路の端から少し入った所 (参道が長すぎる・短すぎるときは規模の範囲に収める)
- 拝殿・本殿・門などは決まった大きさの部品を拡大して置く (scenery.json の instances)。基礎を深くしてあるので
  斜面でも浮かない。参道 (石段を含む) はタイルごとの形 (world_meshes) にする
- 参道と建物の周りの木・花・家は除き (keep_clear)、境内の周りに杉と楠の森を足す

データ出典: © OpenStreetMap contributors (ODbL)
"""

import json
import math
import os
import re

import numpy as np

import scenery_meshes as sm
from buildings import OVERPASS_URL, clean_poly, min_rect, point_in_poly, signed_area
from geo import http_post_form

SEED = 20261015
MERGE_M = 45.0                  # これより近い神社の点はひとつにまとめる
FOOTPRINT_M = 60.0              # 神社の点からこの距離までの building=shrine を拝殿・本殿とみなす
ROAD_SEARCH_M = 220.0           # 参道の向きを決めるのに使う道路の範囲
MIN_GROUND_M = 0.6              # これより低い所 (海・砂浜の際) には建てない
BIG_NAMES = ("大社", "神宮", "八幡宮", "天満宮", "宮崎宮", "大神宮")
SHRINE_NAME = re.compile(r"(神社|宮|稲荷|八幡|天満|権現|明神|大神|社|祠)$")
GENERIC_NAMES = {"", "神社", "shrine", "shinto shrine", "unknown shrine", "祠"}

# 規模ごとの寸法 (m)。sando: 参道の長さの範囲と幅、torii: 鳥居の拡大率、hall: 拝殿・本殿の拡大率、forest: 森の半径
TIERS = {
    "hokora": dict(sando=(2.5, 6.0), width=1.2, torii=0.45, hall=1.0, forest=9.0, lantern_pairs=0),
    "village": dict(sando=(10.0, 40.0), width=2.6, torii=0.85, hall=0.85, forest=28.0, lantern_pairs=2),
    "large": dict(sando=(30.0, 130.0), width=4.0, torii=1.3, hall=1.25, forest=55.0, lantern_pairs=6),
}
TIER_NAMES = {"hokora": "祠", "village": "村の神社", "large": "大きな神社"}
LARGE_PRECINCT_M2 = 5000.0
SMALL_PRECINCT_M2 = 400.0
LARGE_HALLS_M2 = 120.0          # 拝殿と本殿の輪郭の合計がこれ以上なら大きな神社
FOREST_SPACING_M = 6.5
FOREST_KINDS = (("SM_FD_Cedar_A", 0.28), ("SM_FD_Cedar_B", 0.24), ("SM_FD_Broadleaf_D", 0.33), ("SM_FD_Broadleaf_B", 0.15))

# 部品の基本の大きさ (拡大率 1 のとき、m)。原点は正面の地面、+X が奥 (参道を進む向き)
HAIDEN = dict(width=10.0, depth=7.0)   # 拝殿 (平入り: 正面が長い辺)
HONDEN = dict(width=4.4, depth=4.2)    # 本殿 (流造)
GAP_M = 3.0                     # 拝殿と本殿のあいだ

STEP_RISE_M = 0.17              # 参道が坂のときの石段の高さ
STEP_SLOPE = 0.10               # これより急な所は石段にする


# ---------------------------------------------------------------- データ
def fetch(area):
    """神社の点・建物・境内の範囲 (osm_shrines.json)。取れなければ None。"""
    path = os.path.join(area.out_dir, "osm_shrines.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    s, w, n, e = area.bbox()
    b = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    query = (f'[out:json][timeout:180];(nwr["amenity"="place_of_worship"]({b});way["building"="shrine"]({b});'
             f'way["landuse"="religious"]({b});relation["landuse"="religious"]({b}););out tags geom;')
    print("Overpass API から OSM の神社を取得中 ...")
    try:
        data = json.loads(http_post_form(OVERPASS_URL, {"data": query}, retries=2))
    except Exception as ex:  # noqa: BLE001 Overpass の混雑は、建物と店のデータで代わりにする
        print(f"OSM の神社を取得できませんでした ({ex})。建物と店のデータの中の神社を使います")
        return None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def fallback(area):
    """osm_pois.json (点) と osm_buildings.json (輪郭) の中の神社。"""
    elements = []
    for fname in ("osm_pois.json", "osm_buildings.json"):
        path = os.path.join(area.out_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for el in json.load(f).get("elements", []):
                t = el.get("tags", {})
                if t.get("amenity") == "place_of_worship" or t.get("building") == "shrine":
                    elements.append(el)
    return {"elements": elements}


def is_shinto(tags):
    religion = tags.get("religion", "")
    if religion and religion != "shinto":
        return False
    name = tags.get("name", "")
    if name.endswith(("寺", "院", "庵", "教会", "堂")):
        return False
    return religion == "shinto" or tags.get("building") == "shrine" or bool(SHRINE_NAME.search(name))


def load(area, to_ue):
    """(神社の点 [(位置 m, タグ)], 建物の輪郭 [(輪郭, タグ)], 境内の範囲 [輪郭])。UE の座標 (m)。"""
    data = fetch(area) or fallback(area)
    points, halls, precincts = [], [], []
    seen = set()
    for el in data.get("elements", []):
        key = (el["type"], el["id"])
        if key in seen:
            continue
        seen.add(key)
        t = el.get("tags", {})
        rings = []
        if el["type"] == "way" and el.get("geometry"):
            rings = [el["geometry"]]
        elif el["type"] == "relation":
            rings = [m["geometry"] for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
        polys = []
        for g in rings:
            pts = [(p["lat"], p["lon"]) for p in g if p]
            if len(pts) >= 4:
                poly = clean_poly(to_ue(pts))
                if poly is not None:
                    polys.append(poly)
        if t.get("landuse") == "religious":
            if t.get("religion", "shinto") == "shinto":
                precincts += polys
            continue
        if not is_shinto(t):
            continue
        if t.get("building") and polys:
            halls += [(p, t) for p in polys]
            if t.get("amenity") == "place_of_worship":
                points.append((polys[0].mean(0), t))
            continue
        if polys:  # 建物でない place_of_worship の面は境内
            precincts += polys
            points.append((polys[0].mean(0), t))
        elif "lat" in el:
            points.append((to_ue([(el["lat"], el["lon"])])[0], t))
        elif el.get("center"):
            points.append((to_ue([(el["center"]["lat"], el["center"]["lon"])])[0], t))
    return points, halls, precincts


# ---------------------------------------------------------------- まとめ方と規模
def name_rank(tags):
    name = tags.get("name", "")
    return (bool(tags.get("wikidata")), name.endswith(BIG_NAMES), name.endswith(("神社", "宮")),
            name.lower() not in GENERIC_NAMES and "遙拝" not in name and "遥拝" not in name, len(name))


def cluster(points, halls, half_m):
    """近い点と建物をひとつの神社にまとめる。[{pos, tags, halls}]"""
    groups = []
    for pos, tags in points:
        for g in groups:
            if np.hypot(*(g["pos"] - pos)) < MERGE_M:
                g["members"].append((pos, tags))
                break
        else:
            groups.append({"pos": np.array(pos, float), "members": [(pos, tags)]})
    used = set()
    for g in groups:
        g["tags"] = max((t for _, t in g["members"]), key=name_rank)
        g["halls"] = []
        for i, (poly, t) in enumerate(halls):
            if i not in used and np.hypot(*(poly.mean(0) - g["pos"])) < FOOTPRINT_M:
                g["halls"].append((poly, t))
                used.add(i)
    for i, (poly, t) in enumerate(halls):  # 点の無い拝殿・本殿の輪郭も神社にする
        if i in used:
            continue
        g = next((g for g in groups if g.get("_from_halls") and np.hypot(*(g["pos"] - poly.mean(0))) < FOOTPRINT_M), None)
        if g is None:
            groups.append({"pos": poly.mean(0), "tags": t, "halls": [(poly, t)], "_from_halls": True})
        else:
            g["halls"].append((poly, t))
        used.add(i)
    return [g for g in groups if abs(g["pos"][0]) < half_m - 20 and abs(g["pos"][1]) < half_m - 20]


def tier_of(g, precinct):
    name = g["tags"].get("name", "")
    hall_m2 = sum(signed_area(p) for p, _ in g["halls"])
    if precinct is not None:
        a = signed_area(precinct)
        if a >= LARGE_PRECINCT_M2 or name.endswith(BIG_NAMES):
            return "large"
        return "hokora" if a < SMALL_PRECINCT_M2 and not g["halls"] else "village"
    if name.endswith(BIG_NAMES) or g["tags"].get("wikidata") or hall_m2 >= LARGE_HALLS_M2:
        return "large"
    if g["halls"] or (name.lower() not in GENERIC_NAMES and SHRINE_NAME.search(name)):
        return "village"
    return "hokora"


# ---------------------------------------------------------------- 並べ方
def nearest_road(roads, p, max_m=ROAD_SEARCH_M):
    """(道路の点 m, 道路の半分の幅 m)。無ければ None。"""
    best = None
    for r in roads:
        if r.get("tunnel") or r.get("bridge"):
            continue
        q = np.asarray(r["points_cm"], float)[:, :2] / 100
        if len(q) < 2:
            continue
        a, b = q[:-1], q[1:]
        ab = b - a
        t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
        c = a + ab * t[:, None]
        d = np.hypot(*(c - p).T)
        i = int(np.argmin(d))
        if d[i] < max_m and (best is None or d[i] < best[0]):
            best = (float(d[i]), c[i], r["width_cm"] / 200)
    return None if best is None else (best[1], best[2])


def hall_rect(poly):
    c, a, la, lb = min_rect(poly)
    return c, a, la, lb


def plan_one(g, roads, precincts, grid, road_mask, rng):
    """神社 1 つの並べ方。建てられなければ None。"""
    precinct = next((p for p in precincts if point_in_poly(g["pos"], p)), None)
    tier = tier_of(g, precinct)
    spec = TIERS[tier]
    halls = sorted(g["halls"], key=lambda h: -signed_area(h[0]))
    honden = next((h for h in halls if "本殿" in h[1].get("name", "")), None)
    haiden = next((h for h in halls if "拝殿" in h[1].get("name", "") or "拜殿" in h[1].get("name", "")), None)
    if haiden is None and halls:
        haiden = next((h for h in halls if h is not honden), None)
    hall_scale = spec["hall"]
    if haiden is not None:
        c, a, la, lb = hall_rect(haiden[0])
        p = c
        hall_scale = float(np.clip(math.sqrt(la * lb / (HAIDEN["width"] * HAIDEN["depth"])), 0.6, 1.9))
    else:
        p = g["pos"].copy()
        a = None
    ground = grid.height_m(np.array([p[0] * 100]), np.array([p[1] * 100]))[0]
    if np.isnan(ground) or ground < MIN_GROUND_M:
        return None
    # 参道の向き d (鳥居から拝殿へ)
    road = nearest_road(roads, p)
    if honden is not None and haiden is not None:
        d = p - hall_rect(honden[0])[0]
        d = -d / max(np.linalg.norm(d), 1e-6)
    elif road is not None and np.hypot(*(p - road[0])) > 1.0:
        d = (p - road[0]) / np.hypot(*(p - road[0]))
    else:
        ang = rng.uniform(0, 2 * math.pi)
        d = np.array([math.cos(ang), math.sin(ang)])
    if a is not None:  # 拝殿の輪郭の向きにそろえる (正面は長い辺)
        b = np.array([-a[1], a[0]])
        d = b * np.sign(b @ d or 1.0)
    depth = HAIDEN["depth"] * hall_scale if tier != "hokora" else 1.2
    front = p - d * depth / 2
    lo, hi = spec["sando"]
    if road is not None:
        length = float((front - road[0]) @ d) - road[1] - 2.5
    else:
        length = (lo + hi) / 3
    length = float(np.clip(length, lo, hi))
    # 鳥居が道路や海にかからないよう、拝殿の側へ寄せる
    n = road_mask.shape[0]
    while length > lo * 0.5:
        t = front - d * length
        ci, ri = int(t[0] + grid.half_cm / 100), int(t[1] + grid.half_cm / 100)   # road_mask は 1m の格子
        z = grid.height_m(np.array([t[0] * 100]), np.array([t[1] * 100]))[0]
        on_road = 0 <= ri < n and 0 <= ci < n and road_mask[ri, ci]
        if not on_road and not np.isnan(z) and z >= MIN_GROUND_M:
            break
        length -= 1.0
    length = max(length, 2.0)
    return {"name": g["tags"].get("name", "") or "(名前なし)", "tier": tier, "front": front, "d": d,
            "length": length, "hall_scale": hall_scale, "haiden_m": p,
            "honden_m": hall_rect(honden[0])[0] if honden is not None else None, "point_m": g["pos"].copy(),
            "precinct": precinct, "spec": spec}


def plan(area, grid, roads, stamp_roads):
    """タイルの神社の並べ方の一覧と、木・花・家をよける円 [(x cm, y cm, 半径 cm)]。"""
    def to_ue(latlon):
        pts = np.array([area.to_local(lat, lon) for lat, lon in latlon], float)
        pts[:, 1] *= -1
        return pts

    points, halls, precincts = load(area, to_ue)
    groups = cluster(points, halls, grid.half_cm / 100)
    road_mask = stamp_roads(grid, roads, 1.0, 0.5)
    rng = sm.Rng(SEED)
    plans = [pl for pl in (plan_one(g, roads, precincts, grid, road_mask, rng) for g in groups) if pl]
    # 大きな神社から順に置き、その境内に入る小さな神社 (末社・遙拝所の点) は置かない
    rank = {"large": 0, "village": 1, "hokora": 2}
    plans.sort(key=lambda pl: rank[pl["tier"]])
    kept, keep = [], []
    for pl in plans:
        c = clear_circles(pl)
        tips = [pl["haiden_m"] * 100, axis_point(pl, 0.0) * 100]
        if any(math.hypot(q[0] - x, q[1] - y) < r + 300 for x, y, r in keep for q in tips):
            print(f"  神社: {pl['name']} はほかの神社の境内にあるので置きません")
            continue
        kept.append(pl)
        keep += c
    return kept, keep


def axis_point(pl, s, y=0.0):
    """参道の軸の上の点 (鳥居が s=0、拝殿の正面が s=length)。y は右 (+) へのずれ。"""
    d = pl["d"]
    right = np.array([-d[1], d[0]])
    return pl["front"] - d * (pl["length"] - s) + right * y


def back_s(pl):
    """拝殿 (と本殿) のいちばん奥の s。"""
    if pl["tier"] == "hokora":
        return pl["length"] + 1.5
    k = pl["hall_scale"]
    return pl["length"] + HAIDEN["depth"] * k + GAP_M * k + HONDEN["depth"] * k + 2.0


def clear_circles(pl):
    w = pl["spec"]["width"]
    r = (w / 2 + (7.0 if pl["tier"] == "large" else 5.0 if pl["tier"] == "village" else 3.5))
    # OSM の点の所の建物 (地理院の輪郭に神社の見た目が付いたもの) は、こちらで建てるので除く
    out = [(float(pl["point_m"][0] * 100), float(pl["point_m"][1] * 100), 700.0)]
    s = -3.0
    end = back_s(pl) + 2.0
    while s <= end:
        rr = r
        if s > pl["length"]:  # 拝殿・本殿の幅
            rr = max(r, HAIDEN["width"] * pl["hall_scale"] / 2 + 3.0) if pl["tier"] != "hokora" else r
        p = axis_point(pl, s)
        out.append((float(p[0] * 100), float(p[1] * 100), float(rr * 100)))
        s += 3.0
    if pl["tier"] == "large":  # 社務所
        p = axis_point(pl, pl["length"] - 10.0, -(w / 2 + 11.0))
        out.append((float(p[0] * 100), float(p[1] * 100), 900.0))
    return out


# ---------------------------------------------------------------- 置き場所
def ground_cm(grid, p, fallback_m):
    z = grid.height_m(np.array([p[0] * 100]), np.array([p[1] * 100]))[0]
    return (fallback_m if np.isnan(z) else float(z)) * 100


def footprint_top_cm(grid, center, d, length, width, fallback_m):
    """長方形の範囲の地面のいちばん高い所 (建物の床の高さを決める)。"""
    right = np.array([-d[1], d[0]])
    pts = [center + d * sx * length / 2 + right * sy * width / 2 for sx in (-1, 0, 1) for sy in (-1, 0, 1)]
    z = grid.height_m(np.array([q[0] * 100 for q in pts]), np.array([q[1] * 100 for q in pts]))
    z = z[~np.isnan(z)]
    return (float(z.max()) if len(z) else fallback_m) * 100


def place(plans, grid, roads):
    """神社の部品の置き場所 {メッシュ名: [[x, y, z, yaw, 拡大率]]}、参道の形 (Mesh)、数の記録。"""
    inst = {}
    sando = sm.Mesh("SM_FD_ShrineSando", flat=True)
    stats = {}

    def put(name, p, z_cm, yaw, scale=1.0):
        inst.setdefault(name, []).append([round(float(p[0] * 100), 1), round(float(p[1] * 100), 1),
                                          round(float(z_cm), 1), round(float(yaw) % 360, 2), round(float(scale), 3)])

    for pl in plans:
        d, tier, spec, k = pl["d"], pl["tier"], pl["spec"], pl["hall_scale"]
        yaw = math.degrees(math.atan2(d[1], d[0]))
        z0 = ground_cm(grid, pl["front"], 1.0) / 100
        w, L = spec["width"], pl["length"]
        stats[TIER_NAMES[tier]] = stats.get(TIER_NAMES[tier], 0) + 1
        print(f"  神社: {pl['name']} ({TIER_NAMES[tier]}、参道 {L:.0f} m)")
        red = tier == "large" or "稲荷" in pl["name"]
        torii = "SM_FD_ShrineToriiRed" if red else "SM_FD_ShrineToriiStone"
        t0 = axis_point(pl, 0.0)
        put(torii, t0, ground_cm(grid, t0, z0) - 5, yaw, spec["torii"])
        add_sando(sando, grid, pl, z0)
        if tier == "hokora":
            p = axis_point(pl, L + 0.7)
            put("SM_FD_ShrineHokora", p, footprint_top_cm(grid, p, d, 1.4, 1.4, z0), yaw)
            continue
        # 灯籠 (参道の両側に対で)
        pairs = spec["lantern_pairs"]
        if pairs:
            ss = np.linspace(4.0, max(L - 6.0, 4.5), pairs) if L > 10 else [L * 0.5]
            for s in ss[:pairs]:
                for side in (-1, 1):
                    p = axis_point(pl, float(s), side * (w / 2 + 1.1))
                    put("SM_FD_ShrineLantern", p, ground_cm(grid, p, z0) - 5, yaw, 1.0 if tier == "large" else 0.85)
        if tier == "large" and L > 40:  # 二の鳥居
            p = axis_point(pl, L * 0.45)
            put("SM_FD_ShrineToriiRed", p, ground_cm(grid, p, z0) - 5, yaw, 1.0)
        if tier == "large":  # 神門
            p = axis_point(pl, L - 9.0)
            put("SM_FD_ShrineGate", p, footprint_top_cm(grid, p, d, 4.5, 7.0, z0) - 10, yaw, 1.0)
            p = axis_point(pl, L - 10.0, -(w / 2 + 11.0))
            put("SM_FD_ShrineOffice", p, footprint_top_cm(grid, p, d, 12.0, 7.0, z0), yaw + 90.0, 1.0)
        # 手水舎 (参道の右)
        p = axis_point(pl, L - (14.0 if tier == "large" else 6.0), w / 2 + (4.0 if tier == "large" else 3.0))
        put("SM_FD_ShrineTemizuya", p, footprint_top_cm(grid, p, d, 3.0, 3.0, z0), yaw + 90.0,
            1.0 if tier == "large" else 0.85)
        # 狛犬 (拝殿の前で向かい合い、参道の方を向く)
        for side in (-1, 1):
            p = axis_point(pl, L - 3.5, side * (w / 2 + 0.7))
            put("SM_FD_ShrineKomainu", p, ground_cm(grid, p, z0) - 5, yaw + 180.0 + side * 35.0,
                1.0 if tier == "large" else 0.85)
        # 拝殿と本殿
        hd = HAIDEN["depth"] * k
        p = axis_point(pl, L)
        put("SM_FD_ShrineHaiden", p, footprint_top_cm(grid, p + d * hd / 2, d, hd, HAIDEN["width"] * k, z0), yaw, k)
        sn = L + hd + GAP_M * k
        p = axis_point(pl, sn)
        hn = HONDEN["depth"] * k
        top = footprint_top_cm(grid, p + d * hn / 2, d, hn, HONDEN["width"] * k, z0)
        put("SM_FD_ShrineHonden", p, top, yaw, k)
        # 玉垣 (大きな神社は拝殿と本殿を、村の神社は本殿を囲む)
        s0 = (L + hd * 0.55) if tier == "large" else (sn - 1.2 * k)
        s1 = sn + hn + 1.5 * k
        half_w = (HAIDEN["width"] * k / 2 + 1.5) if tier == "large" else (HONDEN["width"] * k / 2 + 1.5)
        fence(put, grid, pl, s0, s1, half_w, z0)
    return inst, sando, stats


FENCE_SEG_M = 2.0


def fence(put, grid, pl, s0, s1, half_w, z0):
    """玉垣: 長方形の 4 辺に 2m の部品を並べる (正面の真ん中はあける)。"""
    d = pl["d"]
    right = np.array([-d[1], d[0]])
    yaw = math.degrees(math.atan2(d[1], d[0]))
    corners = [axis_point(pl, s0, -half_w), axis_point(pl, s1, -half_w), axis_point(pl, s1, half_w),
               axis_point(pl, s0, half_w)]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        e = b - a
        length = float(np.hypot(*e))
        n = max(1, int(round(length / FENCE_SEG_M)))
        ang = math.degrees(math.atan2(e[1], e[0]))
        for j in range(n):
            p = a + e * (j / n)
            mid = a + e * ((j + 0.5) / n)
            if i == 3 and abs(float((mid - axis_point(pl, s0)) @ right)) < 2.0:
                continue  # 正面の入口
            put("SM_FD_ShrineFence", p, ground_cm(grid, mid, z0) - 5, ang, length / n / FENCE_SEG_M)


def add_sando(mesh, grid, pl, z0):
    """参道 (鳥居から拝殿の前まで、拝殿の前は少し広く)。坂は石段にする。"""
    d = pl["d"]
    yaw = math.degrees(math.atan2(d[1], d[0]))
    w = pl["spec"]["width"]
    step = 0.5
    s_end = pl["length"] + (0.6 if pl["tier"] == "hokora" else 0.0)
    ss = np.arange(-1.0, s_end + 1e-6, step)
    pts = np.array([axis_point(pl, s) for s in ss])
    z = grid.height_m(pts[:, 0] * 100, pts[:, 1] * 100)
    z = np.where(np.isnan(z), z0, z)
    slope = np.abs(np.gradient(z, step))
    for i, (p, zz) in enumerate(zip(pts, z)):
        top = zz + 0.06
        if slope[i] > STEP_SLOPE:
            top = math.ceil(top / STEP_RISE_M) * STEP_RISE_M
        mesh.add("FD_ShrineStone", *sm.box((p[0], p[1], top - 0.45), (step + 0.02, w, 0.9), yaw))
    if pl["tier"] != "hokora":  # 拝殿の前の広場
        wide = w + 6.0 * pl["hall_scale"]
        for s in np.arange(pl["length"] - 6.0, pl["length"] + 0.01, 1.0):
            p = axis_point(pl, s)
            zz = ground_cm(grid, p, z0) / 100
            mesh.add("FD_ShrineGravel", *sm.box((p[0], p[1], zz + 0.03 - 0.45), (1.02, wide, 0.9), yaw))


def forest(grid, roads, plans, keep_clear_cm, stamp_roads):
    """鎮守の森 {木の種類: [[x, y, z, yaw, 拡大率]]}。境内 (無ければ神社の周りの円) に杉と楠を密に植える。"""
    rng = sm.Rng(SEED + 1)
    road_clear = stamp_roads(grid, roads, 1.0, 3.0)
    out = {}
    n = road_clear.shape[0]
    kinds = [k for k, _ in FOREST_KINDS]
    weights = np.cumsum([wt for _, wt in FOREST_KINDS])
    for pl in plans:
        radius = pl["spec"]["forest"]
        center = (axis_point(pl, pl["length"]) + axis_point(pl, back_s(pl))) / 2
        g = np.arange(-radius, radius + 1e-6, FOREST_SPACING_M)
        for gx in g:
            for gy in g:
                p = center + np.array([gx, gy]) + np.array(rng.uniform(-0.4, 0.4, 2)) * FOREST_SPACING_M
                if pl["precinct"] is not None:
                    if not point_in_poly(p, pl["precinct"]):
                        continue
                elif np.hypot(gx, gy) > radius or rng.random() < 0.15:
                    continue
                x, y = p * 100
                if any(math.hypot(x - cx, y - cy) < r for cx, cy, r in keep_clear_cm):
                    continue
                ci, ri = int(p[0] + grid.half_cm / 100), int(p[1] + grid.half_cm / 100)   # road_clear は 1m の格子
                if not (0 <= ri < n and 0 <= ci < n) or road_clear[ri, ci]:
                    continue
                z = grid.height_m(np.array([x]), np.array([y]))[0]
                if np.isnan(z) or z < 2.5:
                    continue
                kind = kinds[int(np.searchsorted(weights, rng.random() * weights[-1]))]
                out.setdefault(kind, []).append([round(float(x), 1), round(float(y), 1), round(float(z) * 100 - 10, 1),
                                                 round(float(rng.uniform(0, 360)), 1),
                                                 round(float(rng.uniform(1.0, 1.35)), 3)])
    return out


# ---------------------------------------------------------------- 形
def prism(section_xz, y0, y1):
    """XZ 面の凸多角形 section を Y の y0..y1 に押し出した形。"""
    sec = np.asarray(section_xz, float)
    ring_at = lambda y: np.stack([sec[:, 0], np.full(len(sec), y), sec[:, 1]], 1)
    return sm.sweep([ring_at(y0), ring_at(y1)])


def gable(m, material, x0, x1, ridge_x, z_eave, z_ridge, y0, y1, t=0.22, sori=0.25, segments=3):
    """切妻の屋根 (棟は Y 方向)。x0 と x1 が軒先、ridge_x が棟。軒先が少し反り上がる (sori)。"""
    for xe in (x0, x1):
        xs = np.linspace(xe, ridge_x, segments + 1)
        u = np.linspace(0, 1, segments + 1)
        zs = z_eave + (z_ridge - z_eave) * u - sori * u * (1 - u)   # 中ほどが少しくぼむ
        zs[0] += sori * 0.6                                          # 軒先が反り上がる
        for i in range(segments):
            a, b = (xs[i], zs[i]), (xs[i + 1], zs[i + 1])
            m.add(material, *prism([a, b, (b[0], b[1] - t), (a[0], a[1] - t)], y0, y1))


def raised_hall(m, width, depth, floor_z, wall_h, wall_mat, post_mat, base_depth=3.0):
    """高床の建物の胴 (石の基礎・床・柱・壁)。原点は正面の真ん中の地面、奥が +X。"""
    cx = depth / 2
    m.add("FD_ShrineStone", *sm.box((cx, 0, (floor_z - 0.35 - base_depth) / 2), (depth + 0.6, width + 0.6, floor_z - 0.35 + base_depth)))
    m.add(post_mat, *sm.box((cx, 0, floor_z - 0.15), (depth + 0.9, width + 0.9, 0.3)))  # 床と縁
    m.add(wall_mat, *sm.box((cx, 0, floor_z + wall_h / 2), (depth - 0.4, width - 0.4, wall_h)))
    for x in (0.0, depth):
        for y in np.linspace(-width / 2, width / 2, max(2, int(round(width / 2.5)) + 1)):
            m.add(post_mat, *sm.cylinder((x, y, floor_z - 0.3), (x, y, floor_z + wall_h + 0.1), 0.16, n=10))
    for y in (-width / 2, width / 2):
        m.add(post_mat, *sm.cylinder((depth / 2, y, floor_z - 0.3), (depth / 2, y, floor_z + wall_h + 0.1), 0.16, n=10))
    # 縁の欄干
    m.add(post_mat, *sm.box((cx, -width / 2 - 0.42, floor_z + 0.35), (depth + 0.9, 0.08, 0.08)))
    m.add(post_mat, *sm.box((cx, width / 2 + 0.42, floor_z + 0.35), (depth + 0.9, 0.08, 0.08)))


def front_steps(m, floor_z, width, x_front=0.0, material="FD_ShrineWood"):
    n = max(2, int(round(floor_z / 0.2)))
    run = 0.3
    for i in range(n):
        top = floor_z * (i + 1) / n
        x = x_front - 0.45 - run * (n - 1 - i) - run / 2
        m.add(material, *sm.box((x, 0, top / 2 - 0.2), (run + 0.02, width, top + 0.4)))


def haiden():
    """拝殿 (平入りの切妻、正面に向拝 (階段の上の庇))。原点は正面の真ん中の地面、奥が +X。"""
    m = sm.Mesh("SM_FD_ShrineHaiden")
    W, D = HAIDEN["width"], HAIDEN["depth"]
    fz, wh = 1.3, 3.1
    raised_hall(m, W, D, fz, wh, "FD_ShrineWood", "FD_ShrineWoodDark")
    # 正面の格子戸と白い壁の帯
    m.add("FD_ShrineWhite", *sm.box((-0.01, 0, fz + wh - 0.35), (0.42, W - 0.6, 0.5)))
    for y in np.linspace(-W / 2 + 1.0, W / 2 - 1.0, 7):
        m.add("FD_ShrineWoodDark", *sm.box((0.17, y, fz + 1.2), (0.06, 0.06, 2.3)))
    z_eave = fz + wh + 0.25
    gable(m, "FD_ShrineCopper", -1.9, D + 1.9, D / 2, z_eave, z_eave + 2.9, -W / 2 - 1.5, W / 2 + 1.5, t=0.25)
    m.add("FD_ShrineCopper", *sm.box((D / 2, 0, z_eave + 2.95), (0.5, W + 3.2, 0.35)))  # 棟
    # 向拝 (階段の上の庇と 2 本の柱)
    for y in (-1.6, 1.6):
        m.add("FD_ShrineWoodDark", *sm.cylinder((-2.6, y, -0.2), (-2.6, y, z_eave - 0.2), 0.14, n=10))
    m.add("FD_ShrineCopper", *prism([(-3.3, z_eave - 0.1), (-1.0, z_eave + 1.1), (-1.0, z_eave + 0.85), (-3.3, z_eave - 0.35)],
                                    -2.4, 2.4))
    front_steps(m, fz, 3.2)
    # 賽銭箱としめ縄
    m.add("FD_ShrineWoodDark", *sm.box((-0.5, 0, fz + 0.35), (0.6, 1.6, 0.7)))
    path = np.array([(-0.35, y, fz + wh - 0.75 - 0.25 * (1 - (y / 2.4) ** 2)) for y in np.linspace(-2.4, 2.4, 13)])
    m.add("FD_Shimenawa", *sm.tube(path, 0.12, n=8))
    m.add("FD_ShrineWoodDark", *sm.box((-0.34, 0, fz + wh - 1.15), (0.05, 0.08, 0.6)))  # 鈴の緒
    return m


def honden():
    """本殿 (流造: 正面の屋根が長く伸びる。棟に鰹木、妻に千木)。原点は正面の真ん中の地面、奥が +X。"""
    m = sm.Mesh("SM_FD_ShrineHonden")
    W, D = HONDEN["width"], HONDEN["depth"]
    fz, wh = 1.6, 2.5
    raised_hall(m, W, D, fz, wh, "FD_ShrineWhite", "FD_ShrineVermilion")
    z_eave = fz + wh + 0.2
    ridge_x = D * 0.55
    # 流造: 前の屋根は長く低く、後ろは短い
    gable(m, "FD_ShrineCopper", -2.4, D + 0.9, ridge_x, z_eave - 0.4, z_eave + 2.1, -W / 2 - 0.9, W / 2 + 0.9, t=0.2)
    zr = z_eave + 2.15
    m.add("FD_ShrineCopper", *sm.box((ridge_x, 0, zr), (0.4, W + 2.0, 0.3)))
    for y in np.linspace(-W / 2 + 0.4, W / 2 - 0.4, 4):  # 鰹木
        m.add("FD_ShrineGold", *sm.cylinder((ridge_x - 0.5, y, zr + 0.3), (ridge_x + 0.5, y, zr + 0.3), 0.13, n=10))
    for y in (-W / 2 - 0.9, W / 2 + 0.9):  # 千木 (妻の X 形の板)
        for sx in (-1, 1):
            p0 = np.array([ridge_x, y, zr - 0.2])
            p1 = p0 + np.array([sx * 0.9, 0, 1.1])
            m.add("FD_ShrineGold", *sm.swept_rect(np.array([p0, (p0 + p1) / 2, p1]), 0.12, 0.08))
    for y in (-1.2, 1.2):  # 向拝の柱
        m.add("FD_ShrineVermilion", *sm.cylinder((-1.9, y, -0.2), (-1.9, y, z_eave - 0.2), 0.12, n=10))
    front_steps(m, fz, 2.0)
    return m


def hokora():
    """祠 (石の台の上の小さな社)。原点は正面の真ん中の地面、奥が +X。"""
    m = sm.Mesh("SM_FD_ShrineHokora")
    m.add("FD_ShrineStone", *sm.box((0.55, 0, -0.5 + 0.35), (1.3, 1.3, 1.0 + 0.7)))
    m.add("FD_ShrineWood", *sm.box((0.55, 0, 0.6 + 0.4), (0.75, 0.7, 0.8)))
    gable(m, "FD_ShrineCopper", -0.05, 1.15, 0.55, 1.42, 1.85, -0.55, 0.55, t=0.06, sori=0.05)
    m.add("FD_Shimenawa", *sm.tube(np.array([(0.15, y, 1.25 - 0.05 * (1 - (y / 0.35) ** 2)) for y in np.linspace(-0.35, 0.35, 7)]),
                                   0.03, n=6))
    return m


def lantern():
    """石灯籠 (高さ約 2.3m)。原点は根元の地面。"""
    m = sm.Mesh("SM_FD_ShrineLantern")
    st = "FD_ShrineStone"
    m.add(st, *sm.box((0, 0, -0.2 + 0.2), (0.75, 0.75, 0.4 + 0.2)))
    m.add(st, *sm.cylinder((0, 0, 0.2), (0, 0, 1.15), 0.13, 0.11, n=12))
    m.add(st, *sm.box((0, 0, 1.22), (0.6, 0.6, 0.14)))
    m.add("FD_ShrineLight", *sm.box((0, 0, 1.52), (0.42, 0.42, 0.46)))  # 火袋
    m.add(st, *sm.cylinder((0, 0, 1.75), (0, 0, 2.1), 0.5, 0.06, n=6))  # 笠
    m.add(st, *sm.blob((0, 0, 2.17), (0.09, 0.09, 0.12), sm.Rng(3), subdiv=1, roughness=0.05))  # 宝珠
    return m


def komainu():
    """狛犬 (台座の上に座った形)。原点は台座の真ん中の地面、顔が +X を向く。"""
    m = sm.Mesh("SM_FD_ShrineKomainu")
    rng = sm.Rng(11)
    st = "FD_ShrineStone"
    m.add(st, *sm.box((0, 0, -0.2 + 0.5), (0.9, 0.7, 1.0 + 0.2)))
    m.add(st, *sm.box((0, 0, 1.07), (0.8, 0.6, 0.15)))
    m.add(st, *sm.blob((-0.08, 0, 1.45), (0.33, 0.26, 0.38), rng, roughness=0.12))   # 胴
    m.add(st, *sm.blob((0.16, 0, 1.92), (0.25, 0.24, 0.24), rng, roughness=0.15))    # 頭とたてがみ
    m.add(st, *sm.blob((0.35, 0, 1.86), (0.1, 0.11, 0.08), rng, subdiv=1, roughness=0.05))  # 鼻先
    for y in (-0.13, 0.13):  # 前足
        m.add(st, *sm.cylinder((0.22, y, 1.15), (0.17, y, 1.62), 0.07, n=8))
    return m


def temizuya():
    """手水舎 (4 本の柱と切妻屋根、石の水盤)。原点は真ん中の地面、棟は Y 方向。"""
    m = sm.Mesh("SM_FD_ShrineTemizuya")
    for x in (-1.0, 1.0):
        for y in (-1.3, 1.3):
            m.add("FD_ShrineWoodDark", *sm.cylinder((x, y, -0.3), (x, y, 2.6), 0.11, n=10))
    gable(m, "FD_ShrineCopper", -1.8, 1.8, 0.0, 2.55, 3.55, -2.0, 2.0, t=0.12, sori=0.12)
    m.add("FD_ShrineStone", *sm.box((0, 0, -0.3 + 0.5), (0.9, 1.7, 1.0 + 0.3)))
    m.add("FD_ShrineWater", *sm.box((0, 0, 0.86), (0.7, 1.5, 0.04)))
    return m


def gate():
    """神門 (四脚門: 朱の柱と切妻屋根)。原点は門の真ん中の地面、通り抜ける向きが +X。"""
    m = sm.Mesh("SM_FD_ShrineGate")
    for x in (-1.1, 1.1):
        for y in (-2.4, 2.4):
            m.add("FD_ShrineVermilion", *sm.cylinder((x, y, -0.6), (x, y, 4.2), 0.18, n=12))
    for y in (-1.5, 1.5):  # 本柱
        m.add("FD_ShrineVermilion", *sm.cylinder((0, y, -0.6), (0, y, 4.4), 0.24, n=12))
    m.add("FD_ShrineVermilion", *sm.box((0, 0, 4.3), (2.8, 5.4, 0.35)))
    m.add("FD_ShrineWhite", *sm.box((0, 0, 3.75), (0.2, 3.0, 0.7)))
    gable(m, "FD_ShrineCopper", -2.6, 2.6, 0.0, 4.55, 6.3, -3.6, 3.6, t=0.22, sori=0.3)
    m.add("FD_ShrineCopper", *sm.box((0, 0, 6.33), (0.45, 7.4, 0.32)))
    for y in (-2.4, 2.4):  # 両脇の玉垣へつなぐ板塀
        m.add("FD_ShrineVermilion", *sm.box((0, y * 1.25, 0.9), (0.15, 1.2, 1.8)))
    return m


def office():
    """社務所 (白壁と瓦の切妻の平屋)。原点は真ん中の地面、棟は Y 方向。"""
    m = sm.Mesh("SM_FD_ShrineOffice")
    W, D = 11.0, 6.0
    m.add("FD_ShrineStone", *sm.box((0, 0, -0.8 + 0.4), (D + 0.2, W + 0.2, 1.6)))
    m.add("FD_ShrineWhite", *sm.box((0, 0, 0.4 + 1.5), (D, W, 3.0)))
    for y in np.linspace(-W / 2 + 1.2, W / 2 - 1.2, 5):  # 窓
        m.add("FD_ShrineWoodDark", *sm.box((-D / 2 - 0.02, y, 1.9), (0.06, 1.3, 1.2)))
    gable(m, "FD_ShrineKawara", -D / 2 - 0.8, D / 2 + 0.8, 0.0, 3.4, 5.2, -W / 2 - 0.6, W / 2 + 0.6, t=0.2, sori=0.08)
    return m


def fence_part():
    """玉垣の 2m 分 (朱の柱と横木)。原点は始めの柱の根元、+X へ伸びる。X だけ拡大して長さを合わせる。"""
    m = sm.Mesh("SM_FD_ShrineFence")
    m.add("FD_ShrineVermilion", *sm.box((0, 0, 0.45), (0.14, 0.14, 1.5)))
    for z in (0.35, 1.05):
        m.add("FD_ShrineVermilion", *sm.box((FENCE_SEG_M / 2, 0, z), (FENCE_SEG_M, 0.08, 0.1)))
    for x in np.arange(0.25, FENCE_SEG_M, 0.25):  # 縦の格子
        m.add("FD_ShrineVermilion", *sm.box((x, 0, 0.7), (0.05, 0.05, 0.75)))
    return m


def meshes():
    m = {
        "SM_FD_ShrineToriiRed": sm.torii(name="SM_FD_ShrineToriiRed", material="FD_ShrineVermilion",
                                         top_material="FD_ShrineBlack"),
        "SM_FD_ShrineToriiStone": sm.torii(name="SM_FD_ShrineToriiStone", material="FD_ShrineStone"),
        "SM_FD_ShrineHaiden": haiden(),
        "SM_FD_ShrineHonden": honden(),
        "SM_FD_ShrineHokora": hokora(),
        "SM_FD_ShrineLantern": lantern(),
        "SM_FD_ShrineKomainu": komainu(),
        "SM_FD_ShrineTemizuya": temizuya(),
        "SM_FD_ShrineGate": gate(),
        "SM_FD_ShrineOffice": office(),
        "SM_FD_ShrineFence": fence_part(),
    }
    return m


STRETCH = ["SM_FD_ShrineFence"]
