"""共通処理: エリア設定、座標変換、HTTP取得(キャッシュ付き)。

座標系の約束
- ローカル平面座標はエリア中心を原点とした簡易正距円筒図法 (東 = +x, 北 = +y, 単位 m)。
  数km〜20km 程度の範囲なら誤差は無視できる。
  コースの設定に "rotation_deg" (θ) があれば、タイルの升目ごと反時計回りに θ 度回す (斜めに長い範囲を少ない
  タイルで覆うため)。そのとき +x は東から θ 度北へ回った向き、+y は北から θ 度西へ回った向きになる。
  UE の上では真北が (sin θ, -cos θ) の向き (FDCourseInfo.GridRotationDeg)。
- UE の座標は X = 東, Y = 南 (UE は左手系で上から見て +Y が画面下), Z = 上, 単位 cm。
- ハイトマップの画素 (col, row) は row 0 が北端。UE のランドスケープは row 0 を最小 Y に置くので、
  そのまま取り込めば UE の +X が東、+Y が南になる。
"""

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

EARTH_RADIUS_M = 6378137.0
USER_AGENT = "fukuoka_drive-terrain-tools/0.1 (+https://github.com/elefolo4565/fukuoka_drive)"

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))


class Area:
    """エリア (ランドスケープ 1 枚分) の設定。

    一周コースのタイルは "origin_lat" / "origin_lon" (全タイル共通の原点 = 最初の区間の中心) と
    "tile": [i, j] (i が東、j が北へ 1 枚ずつ) で指定する。投影は原点を基準にするので、隣のタイルと
    境目の位置がぴったり合う。ローカル座標 (m) と出力する UE 座標 (cm) はどちらもタイルの中心が原点で、
    UE ではタイルを ue_offset_cm だけずらして置く。原点やタイルの指定が無ければ中心 = 原点。
    """

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        self.name = cfg["name"]
        self.size_px = int(cfg["size_px"])
        self.meters_per_px = float(cfg["meters_per_px"])
        self.origin_lat = float(cfg.get("origin_lat", cfg.get("center_lat", 0.0)))
        self.origin_lon = float(cfg.get("origin_lon", cfg.get("center_lon", 0.0)))
        self.tile = tuple(cfg.get("tile", (0, 0)))
        self.rotation_deg = float(cfg.get("rotation_deg", 0.0))
        self._cos_r = math.cos(math.radians(self.rotation_deg))
        self._sin_r = math.sin(math.radians(self.rotation_deg))
        tile_m = (self.size_px - 1) * self.meters_per_px
        self.offset_x = self.tile[0] * tile_m   # 原点からタイル中心まで (m、東 +)
        self.offset_y = self.tile[1] * tile_m   # (m、北 +)
        self.center_lat, self.center_lon = self.to_latlon(0.0, 0.0)
        self.landmarks = cfg.get("landmarks", [])
        self.out_dir = os.path.join(TOOLS_DIR, "out", self.name)
        self.cache_dir = os.path.join(TOOLS_DIR, "out", "_cache")
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    @property
    def ue_offset_cm(self):
        """このタイルの中心の UE 座標 (cm)。タイルの出力はすべてここを原点にしている。"""
        return [self.offset_x * 100.0 + 0.0, -self.offset_y * 100.0 + 0.0, 0.0]

    @property
    def size_m(self):
        return (self.size_px - 1) * self.meters_per_px

    @property
    def half_m(self):
        return self.size_m / 2.0

    # --- ローカル平面 (m、タイル中心が原点) <-> 緯度経度 ---
    def to_local(self, lat, lon):
        k = math.pi / 180.0 * EARTH_RADIUS_M
        e = (lon - self.origin_lon) * k * math.cos(math.radians(self.origin_lat))
        n = (lat - self.origin_lat) * k
        if self.rotation_deg:
            e, n = e * self._cos_r + n * self._sin_r, -e * self._sin_r + n * self._cos_r
        return e - self.offset_x, n - self.offset_y

    def to_latlon(self, x, y):
        """x, y はスカラーでも numpy 配列でも可。"""
        k = math.pi / 180.0 * EARTH_RADIUS_M
        e, n = x + self.offset_x, y + self.offset_y
        if self.rotation_deg:
            e, n = e * self._cos_r - n * self._sin_r, e * self._sin_r + n * self._cos_r
        lat = self.origin_lat + n / k
        lon = self.origin_lon + e / (k * math.cos(math.radians(self.origin_lat)))
        return lat, lon

    def bbox(self, margin_m=0.0):
        """(south, west, north, east)。升目を回しているときは、タイルの 4 隅をすべて含む緯度経度の範囲"""
        h = self.half_m + margin_m
        corners = [self.to_latlon(cx, cy) for cx in (-h, h) for cy in (-h, h)]
        lats, lons = [c[0] for c in corners], [c[1] for c in corners]
        return min(lats), min(lons), max(lats), max(lons)

    # --- ローカル平面 (m) <-> ハイトマップ画素 ---
    def local_to_pixel(self, x, y):
        col = (x + self.half_m) / self.meters_per_px
        row = (self.half_m - y) / self.meters_per_px
        return col, row

    def pixel_to_local(self, col, row):
        x = col * self.meters_per_px - self.half_m
        y = self.half_m - row * self.meters_per_px
        return x, y

    # --- ローカル平面 (m) -> UE (cm)。ランドスケープは中心が原点になるよう配置する ---
    @staticmethod
    def local_to_ue(x, y, z_m=0.0):
        return x * 100.0, -y * 100.0, z_m * 100.0


# --- Web メルカトルのタイル計算 ---
def latlon_to_global_px(lat, lon, zoom):
    """緯度経度 -> ズーム zoom での全球ピクセル座標 (256px タイル)。numpy 配列可。"""
    import numpy as np

    n = 256.0 * (2 ** zoom)
    lat_r = np.radians(lat)
    px = (np.asarray(lon) + 180.0) / 360.0 * n
    py = (1.0 - np.log(np.tan(lat_r) + 1.0 / np.cos(lat_r)) / math.pi) / 2.0 * n
    return px, py


def http_get(url, cache_path, retries=4):
    """キャッシュがあればそれを返す。404 は None を返し、空ファイルでキャッシュする。"""
    if os.path.exists(cache_path):
        if os.path.getsize(cache_path) == 0:
            return None
        with open(cache_path, "rb") as f:
            return f.read()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            with open(cache_path, "wb") as f:
                f.write(data)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                open(cache_path, "wb").close()
                return None
            if attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    return None


def http_post_form(url, data, retries=4):
    body = urllib.parse.urlencode(data).encode("utf-8")
    delay = 5.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2

