"""沿道の建物 (家・納屋・倉庫・店) の形。夜は窓が灯る。build_scenery.py から呼ぶ。

建物の輪郭
- 国土地理院のベクトルタイル (最適化ベクトルタイル、ズーム 16) の建築物。基盤地図情報なので、ほぼすべての建物がある
  (OSM の建物はこのあたりでは 2 割ほどしか描かれていない)
- OSM の建物 (osm_buildings.json) は、輪郭が重なる地理院の建物に階数と種類 (building=apartments など) を付けるのに使う
- どちらも PC で取得する (python buildings.py fetch areas/futamigaura.json、build_scenery.py も無ければ取得する)

形の決め方
- 長方形に近い家 (輪郭の面積が最小の外接長方形の 7 割以上) は、その長方形の壁に瓦の切妻屋根か寄棟屋根をのせる
- 大きな建物・3 階以上・店や学校・長方形でない建物は、輪郭どおりの壁に平らな屋根
- 階数は OSM の building:levels、無ければ種類と広さから決める (家は 2 階が多い。小屋・車庫は 1 階)
- 道路にかかる建物 (地図のずれ) と海の上の建物は置かない。建物の上と周り 2m の木や花は除く
- 地理院の「無壁舎」(vt_code 3111/3112、車庫や農作業の屋根だけの小屋) は、柱と金属の屋根だけにする
- OSM の店や施設の点 (osm_pois.json) がある建物は、その種類らしい見た目にする (店の名前は出さない)。
  コンビニ (1 階が全面ガラスで、色の帯が光る)・カフェや食堂 (大きな窓)・店 (1 階が店先)・神社 (板壁と銅板の屋根)・
  寺 (白壁と大きな瓦の寄棟)・学校や役場 (横長の窓が並ぶ)。OSM に店の点が少ないので、海辺の家の 4 分の 1 ほどをカフェに、幹線道路沿いの建物の 2 割ほどをコンビニ・カフェ・店にする

窓 (UE のマテリアル M_FD_BuildingWall が描く。窓の板は作らない)
- 壁の UV: U = 窓の列 (約 3m ごとに 1、壁の長さで割り切れるように伸ばす)、V = 階 (1 階の床が 0、基礎は負)
- 2 つ目の UV: X = 建物ごとの乱数 (どの窓が灯るか)、Y = 窓の描き方 (STYLE_*。基礎・妻壁・小さな小屋は 0 で窓なし)
- 頂点の色 = 壁の色 (屋根は屋根の色)。屋根の 2 つ目の UV: X = 建物ごとの乱数、Y = 屋根の種類 (ROOF_KAWARA など)
- 壁と屋根の模様と凹凸の絵は building_textures.py (マテリアルがワールド座標で貼る)
- 夜は MPC_FD_Night の HouseLights (灯っている窓の割合、FDTimeOfDay が時刻で変える) より乱数の小さい窓が灯る

メッシュは 500m 四方ごとに 1 つ (原点に置く、scenery.json の world_meshes)。

データ出典: 国土地理院ベクトルタイル (地理院タイル)、© OpenStreetMap contributors (ODbL)
"""

import gzip
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

import scenery_meshes as sm
from geo import Area, http_get, http_post_form

SEED = 20261014

GSI_TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/optimal_bvmap-v1/{z}/{x}/{y}.pbf"
GSI_ZOOM = 16
GSI_LAYERS = ("BldA",)          # 建築物 (面)。見つからないときは名前に Bld / building を含む層を使う
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CHUNK_M = 500.0                 # メッシュを分ける大きさ
MIN_AREA_M2 = 12.0              # これより小さいもの (物置) は置かない
MAX_AREA_M2 = 20000.0
NO_WINDOW_AREA_M2 = 25.0        # これより小さい小屋には窓を描かない
RECT_FILL = 0.7                 # 外接長方形に対する面積の割合がこれ以上なら長方形の家とみなす
PITCHED_MAX_AREA_M2 = 400.0
ROAD_OVERLAP = 0.25             # 輪郭の中の点のうち、これより多くが道路の上なら置かない
CLEAR_M = 2.0                   # 建物の周りで木や花を除く幅

FLOOR_M = 2.9                   # 1 階分の高さ
FLOOR_TALL_M = 4.2              # 倉庫・工場・納屋
FOUNDATION_M = 0.45             # 地面 (輪郭の中のいちばん高い所) から 1 階の床まで
BAY_M = 3.0                     # 窓の列の間隔
EAVE_M = 0.55                   # 軒の出
VERGE_M = 0.35                  # けらばの出 (切妻の妻側)
ROOF_T_M = 0.15                 # 屋根の厚さ
PITCH_DEG = {"house": 24.0, "shed": 14.0}

# 種類 (OSM の building) -> 区分
SKIP_KINDS = {"greenhouse", "roof", "carport", "ruins", "construction", "no", "bridge", "canopy", "tent", "collapsed"}
BIG_KINDS = {"apartments", "commercial", "retail", "office", "school", "hotel", "hospital", "public", "civic",
             "university", "kindergarten", "supermarket", "dormitory", "government", "train_station"}
SHED_KINDS = {"shed", "garage", "garages", "barn", "farm_auxiliary", "hut", "cowshed", "stable", "storage_tank", "service"}
TALL_KINDS = {"industrial", "warehouse", "barn", "manufacture", "factory"}
TEMPLE_KINDS = {"temple", "shrine", "church", "religious"}

# 壁の色 (リニア)。(色, 重み)
HOUSE_WALLS = (((0.60, 0.59, 0.56), 5), ((0.56, 0.50, 0.39), 4), ((0.44, 0.37, 0.28), 3), ((0.40, 0.40, 0.39), 3),
               ((0.28, 0.26, 0.23), 2), ((0.13, 0.085, 0.055), 2), ((0.09, 0.09, 0.09), 1))
SHED_WALLS = (((0.24, 0.27, 0.29), 3), ((0.33, 0.33, 0.32), 3), ((0.12, 0.09, 0.07), 2), ((0.18, 0.08, 0.05), 1))
BIG_WALLS = (((0.55, 0.54, 0.51), 4), ((0.45, 0.44, 0.42), 3), ((0.50, 0.45, 0.37), 2))
# 屋根の色 (リニア)。いぶし瓦 (銀灰)・黒瓦・青い釉薬瓦・茶色の金属・赤茶
HOUSE_ROOFS = (((0.050, 0.054, 0.060), 5), ((0.024, 0.026, 0.030), 3), ((0.022, 0.036, 0.070), 2),
               ((0.055, 0.032, 0.020), 2), ((0.10, 0.040, 0.020), 1))
SHED_ROOFS = (((0.13, 0.13, 0.13), 3), ((0.030, 0.050, 0.075), 2), ((0.09, 0.035, 0.020), 2), ((0.035, 0.055, 0.035), 1))
FLAT_ROOF = (0.20, 0.20, 0.19)
ROOF_KAWARA, ROOF_METAL, ROOF_FLAT = 0.0, 1.0, 2.0   # 屋根の種類 (2 つ目の UV の Y)
METAL_HOUSE_ROOF = 0.2          # 家の屋根のうち金属 (トタン・ガルバリウム) の割合

# 壁の窓の描き方 (2 つ目の UV の Y。マテリアル M_FD_BuildingWall と同じ番号)
STYLE_NONE, STYLE_HOUSE, STYLE_STORE, STYLE_KONBINI, STYLE_CAFE, STYLE_WOOD, STYLE_OFFICE = range(7)
OPEN_CODES = ("3111", "3112")   # 地理院の無壁舎
OPEN_HEIGHT_M = (2.6, 3.4)      # 無壁舎の軒の高さ
POST_SPACING_M = 3.6            # 無壁舎の柱の間隔
POST_M = 0.15                   # 柱の太さ
POI_SEARCH_M = 20.0             # 点が輪郭の外にあるとき、この距離までの建物に付ける
# OSM に店の点が少ないので、場所から店を推し量る。海辺の家の一部をカフェに、幹線道路沿いの建物の一部を店にする
BEACH_CAFE = 0.25               # 海辺の家のうち、海辺のカフェにする割合
BEACH_SEA_M = 120.0             # 海からこの距離までが海辺
BEACH_MAX_Z_M = 25.0            # 海辺のカフェにする建物の地面の高さの上限
MAIN_ROADS = ("primary", "secondary", "tertiary")
ROADSIDE_M = 12.0               # 幹線道路の端からこの距離までが道路沿い
ROADSIDE_LOOKS = (("konbini", 0.04, (100, 450)), ("cafe", 0.08, (50, 300)), ("shop", 0.10, (60, 600)))  # (見た目, 割合, 面積 m2)
# 店や施設の見た目。levels = 階数 (範囲)、floor = 1 階分の高さ、roof = 屋根の形、walls / roofs = 色、
# pitch / eave = 屋根の勾配と軒の出、foundation = 床の高さ
POI_LOOKS = {
    "konbini": dict(style=STYLE_KONBINI, levels=(1, 1), floor=4.0, roof="flat", walls=(((0.62, 0.62, 0.60), 1),)),
    "cafe": dict(style=STYLE_CAFE, levels=(1, 2), floor=3.2, roof="gabled_metal",
                 walls=(((0.62, 0.60, 0.56), 3), ((0.16, 0.10, 0.06), 2), ((0.20, 0.30, 0.38), 1), ((0.50, 0.42, 0.30), 1))),
    "shop": dict(style=STYLE_STORE, levels=(2, 2), floor=3.0, roof="flat", walls=BIG_WALLS),
    "shrine": dict(style=STYLE_WOOD, levels=(1, 1), floor=3.6, roof="gabled", pitch=32.0, eave=1.1, foundation=0.9,
                   walls=(((0.13, 0.07, 0.04), 1),), roofs=(((0.04, 0.11, 0.08), 2), ((0.024, 0.026, 0.030), 1))),
    "temple": dict(style=STYLE_WOOD, levels=(1, 1), floor=4.0, roof="hipped", pitch=30.0, eave=1.3, foundation=0.9,
                   walls=(((0.60, 0.60, 0.58), 1),), roofs=(((0.024, 0.026, 0.030), 2), ((0.050, 0.054, 0.060), 1))),
    "public": dict(style=STYLE_OFFICE, levels=(2, 3), floor=3.5, roof="flat", walls=BIG_WALLS),
    "inn": dict(style=STYLE_HOUSE, levels=(2, 3), floor=3.0, roof="hipped", walls=BIG_WALLS),
    # 駅舎 (railways.py が駅の近くの建物に付ける、または線路沿いに建てる)
    "station": dict(style=STYLE_STORE, levels=(1, 1), floor=4.2, roof="hipped", pitch=24.0, eave=1.2,
                    walls=(((0.66, 0.64, 0.60), 3), ((0.55, 0.42, 0.30), 1)),
                    roofs=(((0.05, 0.06, 0.08), 2), ((0.20, 0.06, 0.04), 1))),
}


# ---------------------------------------------------------------- 取得
def mvt_varint(buf, i):
    v, shift = 0, 0
    while True:
        b = buf[i]
        i += 1
        v |= (b & 0x7F) << shift
        if b < 0x80:
            return v, i
        shift += 7


def mvt_fields(buf):
    """protobuf のメッセージを (番号, 値) に分ける。長さ付きの値は bytes、それ以外は int。"""
    i, out = 0, []
    while i < len(buf):
        key, i = mvt_varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = mvt_varint(buf, i)
        elif wt == 2:
            n, i = mvt_varint(buf, i)
            v, i = bytes(buf[i:i + n]), i + n
        elif wt == 1:
            v, i = buf[i:i + 8], i + 8
        elif wt == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"protobuf の型 {wt} は読めません")
        out.append((num, v))
    return out


def mvt_packed(b):
    i, out = 0, []
    while i < len(b):
        v, i = mvt_varint(b, i)
        out.append(v)
    return out


def mvt_value(b):
    for num, v in mvt_fields(b):
        if num == 1:
            return v.decode("utf-8", "replace")
        if num == 2:
            return struct.unpack("<f", v)[0]
        if num == 3:
            return struct.unpack("<d", v)[0]
        if num in (4, 5):
            return v
        if num == 6:
            return (v >> 1) ^ -(v & 1)
        if num == 7:
            return bool(v)
    return None


def mvt_rings(geom):
    """面の地物の輪 (タイル内の座標) の一覧。"""
    rings, cur, x, y, i = [], [], 0, 0, 0
    while i < len(geom):
        cmd, count = geom[i] & 7, geom[i] >> 3
        i += 1
        if cmd == 7:
            if len(cur) >= 3:
                rings.append(cur)
            cur = []
            continue
        for _ in range(count):
            dx, dy = geom[i], geom[i + 1]
            i += 2
            x += (dx >> 1) ^ -(dx & 1)
            y += (dy >> 1) ^ -(dy & 1)
            if cmd == 1:
                cur = [(x, y)]
            else:
                cur.append((x, y))
    return rings


def decode_tile(data, tx, ty, z):
    """ベクトルタイルの建物の外周を [(層の名前, 属性, [(lat, lon)])] で返す。"""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    out, names = [], []
    for num, layer in mvt_fields(data):
        if num != 3:
            continue
        f = mvt_fields(layer)
        name = next((v.decode() for n, v in f if n == 1), "")
        names.append(name)
        if name not in GSI_LAYERS and not any(k in name.lower() for k in ("bld", "building")):
            continue
        keys = [v.decode() for n, v in f if n == 3]
        values = [mvt_value(v) for n, v in f if n == 4]
        extent = next((v for n, v in f if n == 5), 4096)
        for n, feat in f:
            if n != 2:
                continue
            ff = mvt_fields(feat)
            if next((v for k, v in ff if k == 3), 0) != 3:  # 面だけ
                continue
            tags = mvt_packed(next((v for k, v in ff if k == 2), b""))
            props = {keys[tags[j]]: values[tags[j + 1]] for j in range(0, len(tags) - 1, 2)}
            for ring in mvt_rings(mvt_packed(next((v for k, v in ff if k == 4), b""))):
                a = np.array(ring, float)
                # 外周は (y が下向きのタイル座標で) 面積が正。負のもの (中庭の穴) は使わない
                area2 = np.sum(a[:, 0] * np.roll(a[:, 1], -1) - np.roll(a[:, 0], -1) * a[:, 1])
                if area2 <= 0:
                    continue
                n2 = 2 ** z
                lon = (tx + a[:, 0] / extent) / n2 * 360.0 - 180.0
                lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (ty + a[:, 1] / extent) / n2))))
                out.append((name, props, list(zip(lat.tolist(), lon.tolist()))))
    return out, names


def fetch_gsi(area):
    """地理院のベクトルタイルの建物 (エリアにかかるタイルすべて)。タイルは out/_cache に残す。"""
    s, w, n, e = area.bbox(margin_m=50.0)
    z = GSI_ZOOM
    n2 = 2 ** z

    def tile(lat, lon):
        x = int((lon + 180.0) / 360.0 * n2)
        y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n2)
        return x, y

    x0, y0 = tile(n, w)
    x1, y1 = tile(s, e)
    found, layer_names, missing = [], set(), 0
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            cache = os.path.join(area.cache_dir, "gsi_bvmap", str(z), str(tx), f"{ty}.pbf")
            data = http_get(GSI_TILE_URL.format(z=z, x=tx, y=ty), cache)
            if not data:
                missing += 1
                continue
            items, names = decode_tile(data, tx, ty, z)
            found += items
            layer_names.update(names)
    print(f"地理院ベクトルタイル: {(x1 - x0 + 1) * (y1 - y0 + 1)} 枚 (無し {missing})、建物 {len(found)}、層 {sorted(layer_names)}")
    return found


def fetch_osm(area):
    path = os.path.join(area.out_dir, "osm_buildings.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    s, w, n, e = area.bbox()
    b = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    query = f'[out:json][timeout:180];(way["building"]({b});relation["building"]({b}););out tags geom;'
    print("Overpass API から OSM の建物を取得中 ...")
    data = json.loads(http_post_form(OVERPASS_URL, {"data": query}))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def load_footprints(area):
    """[(UE の輪郭 (N,2) m, OSM のタグ または None, 出典)] を返す。地理院の建物と、それに無い OSM の建物。
    地理院のデータが取れないときは OSM の建物だけ。"""
    gsi_path = os.path.join(area.out_dir, "gsi_buildings.json")
    if os.path.exists(gsi_path):
        with open(gsi_path, encoding="utf-8") as f:
            gsi = json.load(f)
    else:
        try:
            gsi = fetch_gsi(area)
        except Exception as ex:  # ネットにつながらない環境 (クラウド) では OSM だけで作る
            print(f"地理院ベクトルタイルを取得できませんでした ({ex})。OSM の建物だけを使います")
            gsi = None
        if gsi is not None:
            with open(gsi_path, "w", encoding="utf-8") as f:
                json.dump(gsi, f, ensure_ascii=False)
    try:
        osm = fetch_osm(area)
    except Exception as ex:
        print(f"OSM の建物を取得できませんでした ({ex})")
        osm = {"elements": []}

    def to_ue(latlon):
        pts = np.array([area.to_local(lat, lon) for lat, lon in latlon], float)
        pts[:, 1] *= -1  # UE の +Y は南
        return pts

    osm_polys = []
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        rings = []
        if el["type"] == "way" and el.get("geometry"):
            rings = [el["geometry"]]
        elif el["type"] == "relation":
            rings = [m["geometry"] for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
        for g in rings:
            pts = [(p["lat"], p["lon"]) for p in g if p]
            if len(pts) >= 4:
                osm_polys.append((to_ue(pts), tags))
    out = []
    if gsi:
        osm_centers = np.array([p.mean(0) for p, _ in osm_polys]) if osm_polys else np.zeros((0, 2))
        used = np.zeros(len(osm_polys), bool)
        for _, props, latlon in gsi:
            poly = to_ue(latlon)
            tags = None
            if len(osm_centers):
                # 地理院の輪郭の中に中心がある OSM の建物のタグを使う
                near = np.nonzero(np.hypot(*(osm_centers - poly.mean(0)).T) < 40.0)[0]
                for j in near:
                    if point_in_poly(osm_centers[j], poly):
                        tags, used[j] = osm_polys[j][1], True
                        break
            if tags is None:
                tags = {"building": "yes"}
            # 種別のコード (最適化ベクトルタイルは vt_code。3101 普通建物、3102 堅ろう建物、3103 高層建物、3111/3112 無壁舎)
            tags = dict(tags, _gsi=str(props.get("vt_code", props.get("ftCode", ""))))
            out.append((poly, tags, "gsi"))
        # 地理院に無い OSM の建物 (新しい建物など) も足す
        for j, (poly, tags) in enumerate(osm_polys):
            if not used[j]:
                out.append((poly, tags, "osm"))
        out = drop_overlaps(out)
    else:
        out = [(p, t, "osm") for p, t in osm_polys]
    attach_pois(out, load_pois(area, to_ue), osm_polys)
    return out


def fetch_pois(area):
    """店や施設の点 (OSM の amenity / shop / tourism)。osm_pois.json に残す。"""
    path = os.path.join(area.out_dir, "osm_pois.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    s, w, n, e = area.bbox()
    b = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    query = (f'[out:json][timeout:180];(nwr["amenity"]({b});nwr["shop"]({b});'
             f'nwr["tourism"~"^(hotel|guest_house|hostel|motel|museum)$"]({b}););out tags center;')
    print("Overpass API から OSM の店や施設を取得中 ...")
    data = json.loads(http_post_form(OVERPASS_URL, {"data": query}))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def poi_look(tags):
    """OSM のタグから見た目の種類 (POI_LOOKS の名前) を決める。当てはまらなければ None。"""
    amenity, shop, tourism = tags.get("amenity", ""), tags.get("shop", ""), tags.get("tourism", "")
    name = tags.get("name", "")
    building = tags.get("building", "")
    if building == "train_station":
        return "station"
    if amenity == "place_of_worship" or building in ("shrine", "temple"):
        if tags.get("religion") == "buddhist" or building == "temple" or name.endswith(("寺", "院", "庵")):
            return "temple"
        return "shrine"
    if shop == "convenience":
        return "konbini"
    if amenity in ("cafe", "restaurant", "fast_food", "bar", "pub", "ice_cream", "food_court"):
        return "cafe"
    if amenity in ("school", "kindergarten", "townhall", "community_centre", "post_office", "police", "clinic",
                   "hospital", "library", "fire_station", "social_facility", "doctors", "bank") or tourism == "museum":
        return "public"
    if tourism in ("hotel", "guest_house", "hostel", "motel"):
        return "inn"
    if shop and shop not in ("vacant", "no"):
        return "shop"
    return None


def load_pois(area, to_ue):
    """[(UE の位置 (2,) m, 見た目の種類)]。取れないときは空。"""
    try:
        data = fetch_pois(area)
    except Exception as ex:
        print(f"OSM の店や施設を取得できませんでした ({ex})")
        return []
    out = []
    for el in data.get("elements", []):
        look = poi_look(el.get("tags", {}))
        c = el.get("center") or ({"lat": el["lat"], "lon": el["lon"]} if "lat" in el else None)
        if look and c:
            out.append((to_ue([(c["lat"], c["lon"])])[0], look))
    return out


def attach_pois(footprints, pois, osm_polys):
    """店や施設の点を、それを含む (無ければ POI_SEARCH_M 以内でいちばん近い) 建物に付ける (tags["_look"])。
    OSM の建物自体に amenity などが書かれていればそれも使う。"""
    for poly, tags, _ in footprints:
        look = poi_look(tags)
        if look:
            tags["_look"] = look
    if not pois or not footprints:
        return
    centers = np.array([p.mean(0) for p, _, _ in footprints])
    for pos, look in pois:
        d = np.hypot(*(centers - pos).T)
        near = np.argsort(d)[:8]
        hit = next((j for j in near if point_in_poly(pos, footprints[j][0])), None)
        if hit is None and d[near[0]] < POI_SEARCH_M:
            hit = near[0]
        if hit is not None:
            footprints[hit][1]["_look"] = look


def drop_overlaps(items):
    """中心が先の建物の輪郭の中に入る、後ろの建物 (地理院と重なる OSM の建物) を除く。"""
    keep, centers = [], []
    grid = {}
    for poly, tags, src in items:
        c = poly.mean(0)
        key = (int(c[0] // 50), int(c[1] // 50))
        hit = False
        if src == "osm":
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for q in grid.get((key[0] + dx, key[1] + dy), ()):
                        if point_in_poly(c, q):
                            hit = True
        if not hit:
            keep.append((poly, tags, src))
            grid.setdefault(key, []).append(poly)
    return keep


# ---------------------------------------------------------------- 多角形
def point_in_poly(p, poly):
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def signed_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def clean_poly(poly, min_edge=0.4, collinear_deg=8.0):
    """閉じた輪郭の重複点・短すぎる辺・ほぼ一直線の点を除く。向きは (x, y) で正の面積にそろえる。"""
    p = np.asarray(poly, float)
    if len(p) > 1 and np.allclose(p[0], p[-1]):
        p = p[:-1]
    changed = True
    while changed and len(p) >= 3:
        changed = False
        for i in range(len(p)):
            a, b, c = p[i - 1], p[i], p[(i + 1) % len(p)]
            ab, bc = b - a, c - b
            la, lb = np.linalg.norm(ab), np.linalg.norm(bc)
            if la < min_edge:
                p = np.delete(p, i, 0)
                changed = True
                break
            cross = ab[0] * bc[1] - ab[1] * bc[0]
            if lb > 1e-9 and abs(math.degrees(math.asin(np.clip(cross / (la * lb), -1, 1)))) < collinear_deg \
                    and np.dot(ab, bc) > 0:
                p = np.delete(p, i, 0)
                changed = True
                break
    if len(p) < 3:
        return None
    if signed_area(p) < 0:
        p = p[::-1]
    return p


def convex_hull(pts):
    pts = sorted(map(tuple, pts))
    if len(pts) <= 2:
        return np.array(pts)

    def half(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h

    lo, hi = half(pts), half(reversed(pts))
    return np.array(lo[:-1] + hi[:-1])


def min_rect(poly):
    """面積が最小の外接長方形 (中心, 長い辺の向き, 長さ, 幅)。"""
    hull = convex_hull(poly)
    best = None
    for i in range(len(hull)):
        e = hull[(i + 1) % len(hull)] - hull[i]
        if np.linalg.norm(e) < 1e-6:
            continue
        a = e / np.linalg.norm(e)
        b = np.array([-a[1], a[0]])
        pa, pb = hull @ a, hull @ b
        area = (pa.max() - pa.min()) * (pb.max() - pb.min())
        if best is None or area < best[0]:
            c = a * (pa.max() + pa.min()) / 2 + b * (pb.max() + pb.min()) / 2
            best = (area, c, a, b, pa.max() - pa.min(), pb.max() - pb.min())
    _, c, a, b, la, lb = best
    if lb > la:
        a, b, la, lb = b, -a, lb, la
    return c, a, la, lb


def triangulate(poly):
    """単純な多角形 (正の面積の向き) を耳を切って三角形に分ける。"""
    idx = list(range(len(poly)))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-9:
                continue
            tri = np.array([a, b, c])
            if any(point_in_tri(poly[j], tri) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break  # 自己交差など。残りは扇形で埋める
    for k in range(1, len(idx) - 1):
        tris.append((idx[0], idx[k], idx[k + 1]))
    return tris


def point_in_tri(p, t):
    d = [(t[(i + 1) % 3][0] - t[i][0]) * (p[1] - t[i][1]) - (t[(i + 1) % 3][1] - t[i][1]) * (p[0] - t[i][0]) for i in range(3)]
    return all(x > 0 for x in d) or all(x < 0 for x in d)


# ---------------------------------------------------------------- 形
class Builder:
    """建物の面をチャンク (500m 四方) ごとの Mesh に足していく。"""

    def __init__(self, half_m):
        self.half_m = half_m
        self.meshes = {}

    def mesh(self, center):
        n = int(math.ceil(2 * self.half_m / CHUNK_M))
        i = int(np.clip((center[0] + self.half_m) // CHUNK_M, 0, n - 1))
        j = int(np.clip((center[1] + self.half_m) // CHUNK_M, 0, n - 1))
        name = f"SM_FD_Buildings_{i}_{j}"
        if name not in self.meshes:
            self.meshes[name] = sm.Mesh(name, flat=True)
        return self.meshes[name]


def wall_quads(mesh, poly, z_lo, z_floor, levels, floor_m, color, seed, style, rng):
    """輪郭 poly (正の面積の向き) の外向きの壁。窓は style (STYLE_*) の描き方。下の基礎 (z_lo..z_floor) には窓を描かない。"""
    z_top = z_floor + levels * floor_m
    v, t, nrm, uv, col, uv1 = [], [], [], [], [], []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        d = b - a
        length = float(np.linalg.norm(d))
        if length < 1e-3:
            continue
        out = np.array([d[1], -d[0], 0.0]) / length  # 正の面積の向き (反時計回り) なら右が外
        bays = int(round(length / BAY_M))
        win = float(style) if bays >= 1 else 0.0
        bays = max(bays, 1)
        u0 = float(rng.integers(0, 8))
        # 基礎は V が負 (マテリアルがコンクリートにする)
        for zl, zh, vl, vh, w in ((z_lo, z_floor, -(z_floor - z_lo) / floor_m, 0.0, 0.0),
                                  (z_floor, z_top, 0.0, float(levels), win)):
            if zh - zl < 1e-3:
                continue
            base = len(v)
            v += [[a[0], a[1], zl], [b[0], b[1], zl], [b[0], b[1], zh], [a[0], a[1], zh]]
            t += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
            nrm += [out] * 4
            uv += [[u0, vl], [u0 + bays, vl], [u0 + bays, vh], [u0, vh]]
            col += [color] * 4
            uv1 += [[seed, w]] * 4
    if v:
        mesh.add_cards("FD_BuildingWall", v, t, nrm, uv, col, orient=True, uv1=uv1)


def solid(mesh, material, verts, faces, color, uv1=None):
    """閉じた形 (面は四角形か三角形、向きはそろっていればどちらでも) を、面ごとの法線の板として足す。"""
    verts = np.asarray(verts, float)
    tris = []
    for f in faces:
        tris += [(f[0], f[k], f[k + 1]) for k in range(1, len(f) - 1)]
    tris = np.array(tris)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum()
    fn = np.cross(b - a, c - a)
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    if vol < 0:
        fn = -fn
    keep = np.linalg.norm(np.cross(b - a, c - a), axis=1) > 1e-8
    tris, fn = tris[keep], fn[keep]
    v = verts[tris].reshape(-1, 3)
    nrm = np.repeat(fn, 3, axis=0)
    t = np.arange(len(v)).reshape(-1, 3)
    uv = np.c_[v[:, 0] + v[:, 1], v[:, 2]]
    col = np.repeat([color], len(v), axis=0)
    mesh.add_cards(material, v, t, nrm, uv, col, orient=True,
                   uv1=None if uv1 is None else np.repeat([uv1], len(v), axis=0))


def gable_roof(mesh, c, a, b, length, width, z_eave, pitch_deg, roof_color, wall_color, seed, roof_kind,
               eave=EAVE_M, gable_walls=True):
    """切妻屋根 (棟は長い辺の向き) と、両端の三角の妻壁。"""
    EAVE_M = eave
    tp = math.tan(math.radians(pitch_deg))
    hw = width / 2
    z_edge = z_eave - EAVE_M * tp
    z_ridge = z_eave + hw * tp
    prof = [(-(hw + EAVE_M), z_edge), (0.0, z_ridge), (hw + EAVE_M, z_edge),
            (hw + EAVE_M, z_edge - ROOF_T_M), (0.0, z_ridge - ROOF_T_M), (-(hw + EAVE_M), z_edge - ROOF_T_M)]
    half = length / 2 + VERGE_M
    verts = []
    for s in (-half, half):
        for pb, pz in prof:
            p = c + a * s + b * pb
            verts.append([p[0], p[1], pz])
    faces = [(k, (k + 1) % 6, 6 + (k + 1) % 6, 6 + k) for k in range(6)]
    faces += [(0, 1, 4, 5), (1, 2, 3, 4), (6, 11, 10, 7), (7, 10, 9, 8)]
    solid(mesh, "FD_BuildingRoof", verts, faces, roof_color, uv1=(seed, roof_kind))
    # 妻壁 (窓なし)
    for s in ((-1, 1) if gable_walls else ()):
        p0, p1 = c + a * s * length / 2 - b * hw, c + a * s * length / 2 + b * hw
        top = c + a * s * length / 2
        v = [[p0[0], p0[1], z_eave], [p1[0], p1[1], z_eave], [top[0], top[1], z_ridge]]
        n = [*(a * s), 0.0]
        mesh.add_cards("FD_BuildingWall", v, [(0, 1, 2)], [n] * 3, [[0, 9.0]] * 3, [wall_color] * 3,
                       orient=True, uv1=[[seed, 0.0]] * 3)


def hip_roof(mesh, c, a, b, length, width, z_eave, pitch_deg, roof_color, seed, roof_kind, eave=EAVE_M):
    """寄棟屋根。軒の高さで平らな底を持つ閉じた形。"""
    EAVE_M = eave
    tp = math.tan(math.radians(pitch_deg))
    hl, hw = length / 2 + EAVE_M, width / 2 + EAVE_M
    z_edge = z_eave - EAVE_M * tp
    z_ridge = z_edge + hw * tp
    r = max(hl - hw, 0.0)
    corners = [c + a * sa * hl + b * sb * hw for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    verts = [[p[0], p[1], z_edge] for p in corners]
    for s in (-1, 1):
        p = c + a * s * r
        verts.append([p[0], p[1], z_ridge])
    # 0..3 軒の角 (反時計回り)、4 = 棟の -a 端、5 = +a 端
    faces = [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4), (3, 2, 1, 0)]
    solid(mesh, "FD_BuildingRoof", verts, faces, roof_color, uv1=(seed, roof_kind))


def posts(mesh, rect, z_lo, z_top, color, seed):
    """無壁舎の柱 (長方形の角と、辺に沿って POST_SPACING_M おき)。"""
    for i in range(4):
        a, b = rect[i], rect[(i + 1) % 4]
        n = max(1, int(round(np.linalg.norm(b - a) / POST_SPACING_M)))
        for k in range(n):
            p = a + (b - a) * k / n
            p = p + (rect.mean(0) - p) / np.linalg.norm(rect.mean(0) - p) * POST_M  # 少し内側
            v, f = sm.box((p[0], p[1], (z_lo + z_top) / 2), (POST_M, POST_M, z_top - z_lo))
            solid(mesh, "FD_BuildingWall", v, f, color, uv1=(seed, 0.0))


def flat_roof(mesh, poly, z, color, seed):
    tris = triangulate(poly)
    v = [[p[0], p[1], z] for p in poly]
    mesh.add_cards("FD_BuildingRoof", v, tris, [[0, 0, 1]] * len(v), [[0, 0]] * len(v), [color] * len(v), orient=True,
                   uv1=[[seed, ROOF_FLAT]] * len(v))


def pick(rng, table):
    w = np.array([wt for _, wt in table], float)
    return table[int(np.searchsorted(np.cumsum(w) / w.sum(), rng.random()))][0]


# ---------------------------------------------------------------- 置き方
def classify(tags, area_m2, rng):
    """(区分, 階数, 1 階分の高さ, 屋根の形)。区分は house / shed / big / tall。"""
    kind = (tags.get("building") or "yes").lower()
    if kind in SKIP_KINDS:
        return None
    gsi = str(tags.get("_gsi", ""))
    if gsi in OPEN_CODES and not tags.get("_look"):
        return "open", 1, rng.uniform(*OPEN_HEIGHT_M), "gabled"
    levels = None
    try:
        levels = max(1, min(15, int(round(float(tags.get("building:levels", ""))))))
    except ValueError:
        pass
    shape = (tags.get("roof:shape") or "").lower()
    if kind in TALL_KINDS or (kind == "yes" and area_m2 > 600):
        cls = "tall"
    elif kind in BIG_KINDS or gsi in ("3102", "3103") and area_m2 > 150:
        cls = "big"
    elif kind in SHED_KINDS or area_m2 < 35:
        cls = "shed"
    else:
        cls = "house"
    if levels is None:
        if cls == "big":
            levels = 4 if gsi == "3103" else (3 if kind == "apartments" else 2)
        elif cls in ("tall", "shed"):
            levels = 1
        else:
            levels = 2 if (area_m2 > 60 and rng.random() < 0.7) else 1
    floor_m = FLOOR_TALL_M if cls == "tall" else FLOOR_M
    if shape not in ("gabled", "hipped", "flat"):
        if cls == "big" or levels >= 3 or area_m2 > PITCHED_MAX_AREA_M2 and cls != "tall":
            shape = "flat"
        elif cls in ("shed", "tall") or kind in TEMPLE_KINDS:
            shape = "gabled"
        else:
            shape = "hipped" if rng.random() < 0.5 else "gabled"
    return cls, levels, floor_m, shape


LOOK_NAMES = {"konbini": "コンビニ", "cafe": "カフェ", "shop": "店", "shrine": "神社", "temple": "寺",
              "public": "公共", "inn": "宿", "beach_cafe": "海辺のカフェ", "station": "駅舎"}


def near_sea(grid, center):
    """center から BEACH_SEA_M 以内 (8 方向) に海 (高さ 0.3m 未満) があるか。"""
    for k in range(8):
        ang = k * math.pi / 4
        for r in (BEACH_SEA_M / 2, BEACH_SEA_M):
            x, y = center[0] + r * math.cos(ang), center[1] + r * math.sin(ang)
            h = grid.height_m(np.array([x * 100]), np.array([y * 100]))[0]
            if h < 0.3:   # 範囲外 (nan) は海と見なさない
                return True
    return False


placed_looks = []   # 最後の place_buildings で店や施設の見た目にした建物 [{look, x_m, y_m}] (UE の座標)


def place_buildings(grid, roads, stamp_roads, footprints, keep_clear_cm=()):
    """建物のメッシュ {名前: Mesh} と、木や花を除く範囲の格子 (1m、True が建物と周り) と、数の記録を返す。"""
    rng = sm.Rng(SEED)
    road_mask = stamp_roads(grid, roads, 1.0, 0.3)
    main_mask = stamp_roads(grid, [r for r in roads if r.get("highway") in MAIN_ROADS], 1.0, ROADSIDE_M)
    n = road_mask.shape[0]
    half_m = grid.half_cm / 100
    builder = Builder(half_m)
    clear_img = Image.new("1", (n, n), 0)
    draw = ImageDraw.Draw(clear_img)
    placed_looks.clear()
    stats = {"置いた": 0, "道路にかかる": 0, "海・範囲外": 0, "小さい・種類": 0, "切妻": 0, "寄棟": 0, "平屋根": 0, "屋根だけ": 0}
    for poly, tags, _ in footprints:
        poly = clean_poly(poly)
        if poly is None:
            stats["小さい・種類"] += 1
            continue
        area_m2 = signed_area(poly)
        center = poly.mean(0)
        if abs(center[0]) > half_m - 5 or abs(center[1]) > half_m - 5:
            stats["海・範囲外"] += 1
            continue
        if not (MIN_AREA_M2 <= area_m2 <= MAX_AREA_M2):
            stats["小さい・種類"] += 1
            continue
        if any(math.hypot(center[0] * 100 - x, center[1] * 100 - y) < r for x, y, r in keep_clear_cm):
            stats["海・範囲外"] += 1
            continue
        spec = classify(tags, area_m2, rng)
        if spec is None:
            stats["小さい・種類"] += 1
            continue
        cls, levels, floor_m, shape = spec
        # 輪郭の中の点 (1m おき) で、道路にかかる割合と地面の高さを調べる
        lo, hi = poly.min(0), poly.max(0)
        gx, gy = np.meshgrid(np.arange(lo[0] + 0.5, hi[0], 1.0), np.arange(lo[1] + 0.5, hi[1], 1.0))
        pts = np.c_[gx.ravel(), gy.ravel()]
        inside = np.array([point_in_poly(p, poly) for p in pts], bool) if len(pts) else np.zeros(0, bool)
        pts = np.r_[pts[inside], poly, [center]]
        ci = np.clip(((pts[:, 0] + half_m) / grid.mpp).astype(int), 0, n - 1)
        ri = np.clip(((pts[:, 1] + half_m) / grid.mpp).astype(int), 0, n - 1)
        if road_mask[ri, ci].mean() > ROAD_OVERLAP or road_mask[ri[-1], ci[-1]]:
            stats["道路にかかる"] += 1
            continue
        z = grid.height_m(pts[:, 0] * 100, pts[:, 1] * 100)
        if np.isnan(z).any() or np.nanmax(z) < 0.8:
            stats["海・範囲外"] += 1
            continue
        z_lo, z_hi = float(np.nanmin(z)) - 0.4, float(np.nanmax(z))
        mesh = builder.mesh(center)
        seed = float(rng.random())
        look = tags.get("_look")
        if look is None and cls in ("house", "big", "shed"):
            if cls != "big" and z_hi < BEACH_MAX_Z_M and 40 <= area_m2 <= 300 and near_sea(grid, center):
                stats["海辺の候補"] = stats.get("海辺の候補", 0) + 1
                if rng.random() < BEACH_CAFE:
                    look = "beach_cafe"
            elif cls != "shed" and main_mask[ri, ci].any():
                r = rng.random()
                for name, share, (a0, a1) in ROADSIDE_LOOKS:
                    if r < share and a0 <= area_m2 <= a1:
                        look = name
                        break
                    r -= share
        spec = POI_LOOKS.get("cafe" if look == "beach_cafe" else look)
        walls = SHED_WALLS if cls in ("shed", "tall", "open") else BIG_WALLS if cls == "big" else HOUSE_WALLS
        if cls == "big":
            style = STYLE_OFFICE
        elif area_m2 >= NO_WINDOW_AREA_M2 and cls != "open":
            style = STYLE_HOUSE
        else:
            style = STYLE_NONE
        pitch_v, eave, foundation, roofs_v = None, EAVE_M, FOUNDATION_M, None
        if spec:
            levels = int(rng.integers(spec["levels"][0], spec["levels"][1] + 1))
            floor_m, style, walls = spec["floor"], spec["style"], spec["walls"]
            shape = spec["roof"]
            pitch_v, roofs_v = spec.get("pitch"), spec.get("roofs")
            eave = spec.get("eave", EAVE_M)
            foundation = spec.get("foundation", FOUNDATION_M)
            stats[LOOK_NAMES[look]] = stats.get(LOOK_NAMES[look], 0) + 1
            placed_looks.append({"look": look, "x_m": round(float(center[0]), 1), "y_m": round(float(center[1]), 1)})
        z_floor = z_hi + foundation
        wall_color = pick(rng, walls)
        c, a, la, lb = min_rect(poly)
        rect_fill = area_m2 / max(la * lb, 1e-6)
        b = np.array([-a[1], a[0]])
        if cls == "open" and lb >= 2.0:
            # 無壁舎 (車庫・作業場・牛舎の屋根だけの建物): 柱と、緩い金属の屋根
            rect = np.array([c + a * sa * la / 2 + b * sb * lb / 2 for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            z_eave = z_hi + floor_m
            posts(mesh, rect, z_lo, z_eave, wall_color, seed)
            gable_roof(mesh, c, a, b, la, lb, z_eave, float(rng.uniform(10, 14)), pick(rng, SHED_ROOFS), wall_color,
                       seed, ROOF_METAL, eave=0.3, gable_walls=False)
            stats["屋根だけ"] += 1
            outline = rect
        elif cls == "open":
            stats["小さい・種類"] += 1
            continue
        elif shape != "flat" and rect_fill >= RECT_FILL and lb >= 2.5:
            rect = np.array([c + a * sa * la / 2 + b * sb * lb / 2 for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            rect = clean_poly(rect)
            wall_quads(mesh, rect, z_lo, z_floor, levels, floor_m, wall_color, seed, style, rng)
            z_eave = z_floor + levels * floor_m
            roofs = roofs_v or (SHED_ROOFS if cls in ("shed", "tall") else HOUSE_ROOFS)
            roof_color = pick(rng, roofs)
            if shape == "gabled_metal":
                metal, shape = True, "gabled"
                roof_color = pick(rng, SHED_ROOFS)
            elif roofs_v:
                metal = look == "shrine"   # 銅板葺き
            else:
                metal = cls in ("shed", "tall") or rng.random() < METAL_HOUSE_ROOF
                if metal and cls == "house":
                    roof_color = pick(rng, SHED_ROOFS)
            roof_kind = ROOF_METAL if metal else ROOF_KAWARA
            pitch = pitch_v or PITCH_DEG["shed" if metal else "house"]
            if shape == "hipped" and la - lb > -1e-6:
                hip_roof(mesh, c, a, b, la, lb, z_eave, pitch, roof_color, seed, roof_kind, eave=eave)
                stats["寄棟"] += 1
            else:
                gable_roof(mesh, c, a, b, la, lb, z_eave, pitch, roof_color, wall_color, seed, roof_kind, eave=eave)
                stats["切妻"] += 1
            outline = rect
        else:
            wall_quads(mesh, poly, z_lo, z_floor, levels, floor_m, wall_color, seed, style, rng)
            flat_roof(mesh, poly, z_floor + levels * floor_m + 0.02, FLAT_ROOF, seed)
            stats["平屋根"] += 1
            outline = poly
        stats["置いた"] += 1
        # 木や花を除く範囲 (輪郭を CLEAR_M 広げたもの、格子の画素)
        cc = outline.mean(0)
        grown = cc + (outline - cc) * (1 + CLEAR_M / max(math.sqrt(area_m2) / 2, 1.0))
        draw.polygon([((x + half_m) / grid.mpp, (y + half_m) / grid.mpp) for x, y in grown], fill=1)
    clear = np.array(clear_img, bool)
    return builder.meshes, clear, stats


def remove_in_mask(instances, mask, mpp, half_m, names):
    """mask (True の所) の上にある names の置き場所を除く。除いた数を返す。"""
    removed = 0
    n = mask.shape[0]
    for name in names:
        items = instances.get(name)
        if not items:
            continue
        a = np.array([it[:2] for it in items], float)
        ci = np.clip(((a[:, 0] / 100 + half_m) / mpp).astype(int), 0, n - 1)
        ri = np.clip(((a[:, 1] / 100 + half_m) / mpp).astype(int), 0, n - 1)
        keep = ~mask[ri, ci]
        removed += int((~keep).sum())
        instances[name] = [it for it, k in zip(items, keep) if k]
    return removed


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "fetch":
        sys.exit("使い方: python buildings.py fetch areas/<エリア>.json")
    area = Area(sys.argv[2])
    fps = load_footprints(area)
    print(f"建物の輪郭 {len(fps)} (地理院 {sum(1 for f in fps if f[2] == 'gsi')}、OSM {sum(1 for f in fps if f[2] == 'osm')})")


if __name__ == "__main__":
    main()
