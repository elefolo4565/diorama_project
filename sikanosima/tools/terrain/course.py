"""コースの設定 (areas/<コース名>.json) を読み、タイルの名前・置き場・UE のレベル名などを決める。

いま作るコースは tools/terrain/course.txt に 1 行で書く (無ければ itoshima_loop)。
setup_project.py (UE の中の Python) もこのファイルを読み込んで使うので、標準ライブラリだけで書く。

コースの設定 (すべて任意。無ければ下の既定値):
    "map":         UE のレベル名 (/Game/FukuokaDrive/Maps/<map>)。既定はコース名
    "tile_prefix": タイルの名前の頭 (<tile_prefix>_<i>_<j>)。既定はコース名
    "origin_tile": タイル (0, 0) に使う既存のエリア設定の名前 (areas/<名前>.json)。既定は無し (<tile_prefix>_0_0)
    "sun":         [緯度, 経度] 太陽と星の計算に使う。既定はコースの中心
    "route":       GPX か KML のファイル (areas/ からの相対パス)。あればその線をそのままコースにする
    "polygon":     [[緯度, 経度], ...]。あれば道筋ではなく、この多角形にかかるタイルを全部作る
                   (tools/kit/area_picker.py で地図に描いて書き出せる)
    "rotation_deg": タイルの升目を反時計回りに回す角度 (度)。斜めに長い範囲を少ないタイルで覆う。
                   area_picker.py がタイルの枚数がいちばん少なくなる角度を選んで書く。既定 0 (北が上)
    "sea":         "none" なら海を置かない。既定の "auto" はどれかのタイルに海があれば置く (build_tiles.py が tiles.json に書く)
    "loop":        true なら最後の点から最初の点へ戻る一周コース。既定は route も polygon も無ければ true

使い方 (コマンドライン):
    python course.py                今のコースの設定を表示
    python course.py base_area      共通のアセットを作るタイルのエリア設定のパス (rebuild.bat が使う)
"""

import json
import math
import os
import sys
import xml.etree.ElementTree as ET

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
AREAS_DIR = os.path.join(TOOLS_DIR, "areas")
OUT_DIR = os.path.join(TOOLS_DIR, "out")
ACTIVE_FILE = os.path.join(TOOLS_DIR, "course.txt")
DEFAULT_COURSE = "itoshima_loop"

# 汎用化の前に作ったコース。設定ファイル (と、それを材料にした作り方のハッシュ) を変えずに、
# これまでと同じ名前と値になるようにする
LEGACY = {
    "itoshima_loop": {"map": "Itoshima", "tile_prefix": "itoshima", "tile_dir": "itoshima",
                      "origin_tile": "futamigaura", "sun": [33.641, 130.196]},
}


def active_name():
    if os.path.exists(ACTIVE_FILE):
        with open(ACTIVE_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    return line
    return DEFAULT_COURSE


class Course:
    def __init__(self, name_or_path=None):
        name_or_path = name_or_path or active_name()
        if name_or_path.endswith(".json"):
            self.path = os.path.abspath(name_or_path)
        else:
            self.path = os.path.join(AREAS_DIR, f"{name_or_path}.json")
        with open(self.path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.name = self.cfg["name"]
        legacy = LEGACY.get(self.name, {})
        get = lambda k, d: self.cfg.get(k, legacy.get(k, d))
        self.map = get("map", self.name)
        self.tile_prefix = get("tile_prefix", self.name)
        self.tile_dir = os.path.join(AREAS_DIR, get("tile_dir", self.name))
        self.origin_tile = get("origin_tile", None)
        self.route_file = self.cfg.get("route")
        self.rotation = float(self.cfg.get("rotation_deg", 0.0))   # タイルの升目の回転 (度、反時計回り)。geo.py を参照
        self.loop = bool(self.cfg.get("loop", not self.route_file and not self.cfg.get("polygon")))
        sun = get("sun", None)
        if sun is None and "center_lat" in self.cfg:
            sun = [self.cfg["center_lat"], self.cfg["center_lon"]]
        self.sun = tuple(sun) if sun else None
        self.out_dir = os.path.join(OUT_DIR, self.name)

    # --- タイル ---
    def tile_name(self, i, j):
        if (i, j) == (0, 0) and self.origin_tile:
            return self.origin_tile
        f = lambda v: f"m{-v}" if v < 0 else str(v)
        return f"{self.tile_prefix}_{f(i)}_{f(j)}"

    def tile_area_path(self, i, j, create=True):
        """タイルのエリア設定のパス。無ければ作る (タイル (0, 0) が既存のエリアなら、それをそのまま使う)。"""
        if (i, j) == (0, 0) and self.origin_tile:
            return os.path.join(AREAS_DIR, f"{self.origin_tile}.json")
        path = os.path.join(self.tile_dir, f"{self.tile_name(i, j)}.json")
        if create and not os.path.exists(path):
            os.makedirs(self.tile_dir, exist_ok=True)
            first = self.origin_tile or "原点"
            want = {"name": self.tile_name(i, j),
                    "description": f"{self.cfg.get('description', self.name).split('。')[0]} のタイル ({i}, {j})。"
                                   f"i が東、j が北へ 1 枚 ({(self.cfg['tile_size_px'] - 1) * self.cfg['meters_per_px']:.0f}m) ずつ。"
                                   f"原点は {first} の中心",
                    "origin_lat": self.cfg["center_lat"], "origin_lon": self.cfg["center_lon"], "tile": [i, j],
                    **({"rotation_deg": self.rotation} if self.rotation else {}),
                    "size_px": self.cfg["tile_size_px"], "meters_per_px": self.cfg["meters_per_px"]}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(want, f, ensure_ascii=False, indent=2)
                f.write("\n")
        return path

    def tiles_doc(self):
        path = os.path.join(self.out_dir, "tiles.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def base_tile(self):
        """木や花など、どのタイルでも同じ形のアセットを作るタイルの名前。
        tiles.json の base_tile、無ければタイル (0, 0)、それも無ければ最初のタイル。"""
        doc = self.tiles_doc()
        if doc:
            if doc.get("base_tile"):
                return doc["base_tile"]
            names = {tuple(t["tile"]): t["name"] for t in doc["tiles"]}
            return names.get((0, 0)) or sorted(names.values())[0]
        return self.tile_name(0, 0)

    def base_area_path(self):
        doc = self.tiles_doc()
        if doc:
            for t in doc["tiles"]:
                if t["name"] == self.base_tile():
                    return os.path.join(TOOLS_DIR, t["area"])
        return self.tile_area_path(0, 0, create=False)


def course_of_area(area_path):
    """タイルのエリア設定 (areas/<コース>/<タイル>.json) が属するコース。無ければ None。"""
    d = os.path.dirname(os.path.abspath(area_path))
    path = os.path.join(os.path.dirname(d), f"{os.path.basename(d)}.json")
    if os.path.basename(os.path.dirname(d)) == "areas" and os.path.exists(path):
        return Course(path)
    return None


# コースの設定の "features" で切れるもの。無ければすべて入れる (糸島一周と同じ)
FEATURES = {
    "landmarks": True,        # 夫婦岩・しめ縄・鳥居・県道 54 号のヤシ並木 (OSM に夫婦岩が無ければ、入れても何も置かれない)
    "road_markings": True,    # 区画線・側溝・標識 (道路そのものは常に作る)
    "utility_poles": True,    # 電柱と電線・防犯灯 (街灯)
    "guardrails": True,       # ガードレール
    "city_glow": True,        # 夜空の福岡市・前原の方向の街明かり
    # 神社 (鳥居・参道・拝殿・本殿・鎮守の森、tools/terrain/shrines.py)。前からあるコースの見た目を変えないよう、
    # 書いていなければ作らない (地図で範囲を選ぶ画面は true を書く)
    "shrines": False,
}
# 前の書き方: "road_furniture" は区画線・側溝・標識・電柱・防犯灯・ガードレールをまとめて切り替える
# (個別のキーが書いてあればそちらが勝つ)
ROAD_FURNITURE = ("road_markings", "utility_poles", "guardrails")


def features_of(course):
    """{機能: 入れるか}。コースが無い (二見ヶ浦だけのエリアなど) ときはすべて入れる。"""
    out = dict(FEATURES)
    if course is not None:
        given = dict(course.cfg.get("features", {}))
        unknown = set(given) - set(FEATURES) - {"road_furniture"}
        if unknown:
            sys.exit(f"{course.path} の features の {sorted(unknown)} は知らない名前です ({sorted(FEATURES)})")
        if "road_furniture" in given:
            all_road = bool(given.pop("road_furniture"))
            out.update({k: all_road for k in ROAD_FURNITURE})
        out.update({k: bool(v) for k, v in given.items()})
    return out


def course_features(area_path):
    """タイルのエリア設定から、そのコースの features を返す。"""
    return features_of(course_of_area(area_path))


def course_overrides(area_path, modules):
    """コースの設定の "vegetation" ({"モジュール.定数": 値}) で、景観物を作るスクリプトの定数を変える。
    例: {"build_scenery.GRASSLAND_MIN_Z_M": 650, "flowers.FIELD_Z_M": [2.5, 800]}。リストはタプルにする。"""
    course = course_of_area(area_path)
    if course is None:
        return
    for key, value in course.cfg.get("vegetation", {}).items():
        mod_name, _, const = key.partition(".")
        mod = modules.get(mod_name)
        if mod is None or not hasattr(mod, const):
            sys.exit(f"{course.path} の vegetation の {key} は変えられる定数ではありません")
        setattr(mod, const, tuple(value) if isinstance(value, list) else value)
        print(f"  {course.name}: {key} = {value}")


# ---------------------------------------------------------------- GPX / KML
def read_track(path):
    """GPX (trkpt / rtept) か KML (LineString の coordinates) から [(緯度, 経度), ...] を読む。"""
    root = ET.parse(path).getroot()
    local = lambda tag: tag.rsplit("}", 1)[-1]
    pts = []
    if local(root.tag) == "gpx":
        for kind in ("trkpt", "rtept"):
            for el in root.iter():
                if local(el.tag) == kind:
                    pts.append((float(el.get("lat")), float(el.get("lon"))))
            if pts:
                break
    else:
        for el in root.iter():
            if local(el.tag) == "coordinates" and el.text:
                for tok in el.text.split():
                    lon, lat = tok.split(",")[:2]
                    pts.append((float(lat), float(lon)))
    out = []
    for p in pts:   # 同じ点の連続を省く
        if not out or p != out[-1]:
            out.append(p)
    if len(out) < 2:
        sys.exit(f"{path} に線の点がありません (GPX の trkpt / rtept か KML の LineString が必要)")
    return out


def track_extent(track):
    """コースの線の中心 (緯度, 経度) と、中心から最も遠い点までの東西・南北の距離 (m)。"""
    lats = [p[0] for p in track]
    lons = [p[1] for p in track]
    clat, clon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    k = math.pi / 180.0 * 6378137.0
    half_x = (max(lons) - min(lons)) / 2 * k * math.cos(math.radians(clat))
    half_y = (max(lats) - min(lats)) / 2 * k
    return (clat, clon), half_x, half_y


def main():
    c = Course()
    if sys.argv[1:] == ["base_area"]:
        print(c.base_area_path())
        return
    print(json.dumps({"name": c.name, "path": c.path, "map": c.map, "tile_prefix": c.tile_prefix,
                      "tile_dir": c.tile_dir, "origin_tile": c.origin_tile, "sun": c.sun, "loop": c.loop,
                      "route": c.route_file, "base_tile": c.base_tile()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
