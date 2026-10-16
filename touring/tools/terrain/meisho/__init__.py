"""名所 (その土地にしかない記念碑・建物・展望台など) の受け口。このフォルダの名所を集めて build_scenery.py と check.py に渡す。

1 つの名所 = 1 ファイル (<名前のローマ字>.py)。見た目の基準は notes/<名前>.md (写真から書いた特徴メモ)。
ファイルが定義するもの:
    NAME_JA    和名 (例 "金印公園")
    LATLON     (緯度, 経度)。OSM の点など。build(ctx) の ctx.x, ctx.y がこの点の UE 座標 (m) になる
    CLEAR      [(道路からの奥行き m, 道路に沿った位置 m, 半径 m), ...] (省略可)。木・花・家をよける円。
               位置は ctx.frame の座標 (下の「道路の座標」)。ctx で決めるときは関数 clear(ctx) で同じリストを返す
    TERRACES   地形を平らにする所 (省略可。ctx で決めるときは関数 terraces(ctx) で同じリストを返す)。
               apply_roads.py が道路を焼いた後に地形へ焼く (UE の地面も平らになる)
               dict(kind="rect", s=(s0, s1), u=(u0, u1), z="road", dz=0.1, feather=2.0)   道路の座標の四角
               dict(kind="circle", s=s, u=u, r=半径, z="ground", dz=0.0, feather=3.0)      円
               z: "road" = いちばん近い道路の路面の高さ、"ground" = 平らにする前のその中心の地面の高さ。dz を足す。
               feather (m) の幅で元の斜面へなめらかにつなぐ。道路の路面は変えない
    MATERIALS  {マテリアル名: scenery_meshes.MATERIALS と同じ書き方} (省略可)。名前は FD_Meisho<名前> にする
    REPLACES_SHRINES  (省略可) この名所で置き換える神社の名前 (OSM の name)。shrines.py の一般の神社は置かない
    build(ctx) -> scenery_meshes.Mesh。タイルの UE 座標 (m、X 東寄り・Y 南寄り・Z 上) で作る
               (地面の高さに合わせて作るので、名所の形はタイルごとの形 world_meshes として原点に置く)

ctx (build に渡すもの):
    ctx.x, ctx.y, ctx.z     LATLON の点 (m)。z はその点の地面の高さ
    ctx.ground(x, y)        地面の高さ (m)。x, y は数でも numpy 配列でも可
    ctx.road                いちばん近い道路 dict(name, width, point=(x, y), tangent=(tx, ty), z, dist)
    ctx.latlon(lat, lon)    緯度経度 -> UE 座標 (m)
    ctx.frame(s, u)         道路の座標 -> UE 座標 (m)。s は道路の中心から名所の方への奥行き、u は道路に沿った位置
                            (どちらも m、原点は名所にいちばん近い道路の中心の点)。名所を道路の向きに合わせて並べるのに使う

道路の座標で並べると、OSM の点が少しずれていても道路との位置関係 (道路ぎわの碑、奥の広場) が保たれる。
"""

import importlib
import math
import os

import numpy as np

import scenery_meshes as sm

HERE = os.path.dirname(os.path.abspath(__file__))
MESH_PREFIX = "SM_FD_Meisho_"
SEARCH_ROAD_M = 200.0     # この距離までの道路を「いちばん近い道路」として探す


def module_names():
    return sorted(f[:-3] for f in os.listdir(HERE)
                  if f.endswith(".py") and not f.startswith("_") and f not in ("check.py",))


def load_module(name):
    mod = importlib.import_module(f"meisho.{name}")
    for mat, spec in getattr(mod, "MATERIALS", {}).items():
        if mat in sm.MATERIALS and sm.MATERIALS[mat] != spec:
            raise ValueError(f"meisho/{name}.py の {mat} は、ほかで決めたマテリアルと名前が同じです")
        sm.MATERIALS[mat] = spec
    return mod


def mesh_name(name):
    return MESH_PREFIX + "".join(p.capitalize() for p in name.split("_"))


class Ctx:
    def __init__(self, grid, roads, x, y, area=None):
        self.grid = grid
        self.area = area
        self.x, self.y = float(x), float(y)
        self.z = float(self.ground(x, y))
        self.road = nearest_road(roads, self.x, self.y)
        if self.road:
            px, py = self.road["point"]
            tx, ty = self.road["tangent"]
            nx, ny = self.x - px, self.y - py
            d = math.hypot(nx, ny)
            # 名所の方を向く道路の法線 (名所が道路の真上なら、接線を左へ 90 度回した向き)
            self._n = (nx / d, ny / d) if d > 0.5 else (-ty, tx)
            self._t = (tx, ty)
            self._o = (px, py)
        else:   # 道路が無ければ、点を原点に東西南北で並べる
            self._n, self._t, self._o = (0.0, -1.0), (1.0, 0.0), (self.x, self.y)

    def ground(self, x, y):
        h = self.grid.height_m(np.asarray(x, float) * 100, np.asarray(y, float) * 100)
        h = np.where(np.isnan(h), 0.0, h)
        return float(h[0]) if np.ndim(x) == 0 else h.reshape(np.shape(x))

    def frame(self, s, u):
        s, u = np.asarray(s, float), np.asarray(u, float)
        x = self._o[0] + self._n[0] * s + self._t[0] * u
        y = self._o[1] + self._n[1] * s + self._t[1] * u
        return (float(x), float(y)) if x.ndim == 0 else (x, y)

    def latlon(self, lat, lon):
        """緯度経度 -> UE 座標 (m)。OSM の輪郭などをそのまま置くときに使う。"""
        e, n = self.area.to_local(lat, lon)
        return float(e), float(-n)

    def to_frame(self, x, y):
        """UE 座標 (m) -> 道路の座標 (s, u)。"""
        dx, dy = np.asarray(x, float) - self._o[0], np.asarray(y, float) - self._o[1]
        return dx * self._n[0] + dy * self._n[1], dx * self._t[0] + dy * self._t[1]

    @property
    def yaw_deg(self):
        """道路の座標の s (奥行き) の向き (度、UE の yaw)。"""
        return math.degrees(math.atan2(self._n[1], self._n[0]))


def nearest_road(roads, x, y):
    best = None
    for r in roads:
        if r.get("tunnel"):
            continue
        p = np.asarray(r["points_cm"], float) / 100.0
        for i in range(len(p) - 1):
            a, b = p[i, :2], p[i + 1, :2]
            d = b - a
            L = float(np.hypot(*d))
            if L < 1e-6:
                continue
            t = float(np.clip(np.dot((x - a[0], y - a[1]), d) / (L * L), 0.0, 1.0))
            q = a + d * t
            dist = float(np.hypot(x - q[0], y - q[1]))
            if dist <= SEARCH_ROAD_M and (best is None or dist < best["dist"]):
                best = dict(name=r.get("name", ""), width=r["width_cm"] / 100.0, point=(float(q[0]), float(q[1])),
                            tangent=(float(d[0] / L), float(d[1] / L)), z=float(p[i, 2] + (p[i + 1, 2] - p[i, 2]) * t),
                            dist=dist)
    return best


def find(area, grid, roads, names=None):
    """タイルの中にある名所の一覧 [(名前, モジュール, Ctx)]。"""
    out = []
    for name in names or module_names():
        mod = load_module(name)
        e, n = area.to_local(*mod.LATLON)
        x, y = e, -n    # UE: +Y は南
        if abs(x) >= area.half_m or abs(y) >= area.half_m:
            continue
        out.append((name, mod, Ctx(grid, roads, x, y, area)))
    return out


def replaced_shrines(spots):
    return {n for _, mod, _ in spots for n in getattr(mod, "REPLACES_SHRINES", ())}


def keep_clear(spots):
    """木・花・家をよける円 [(x cm, y cm, 半径 cm)]。"""
    out = []
    for _, mod, ctx in spots:
        c = getattr(mod, "clear", None)
        for s, u, r in (c(ctx) if callable(c) else getattr(mod, "CLEAR", ())):
            x, y = ctx.frame(s, u)
            out.append((x * 100.0, y * 100.0, r * 100.0))
    return out


def terraces_of(mod, ctx):
    t = getattr(mod, "terraces", None)
    return t(ctx) if callable(t) else list(getattr(mod, "TERRACES", ()))


def flatten(area, height, roads, road_w=None, names=None, ref=None):
    """名所の TERRACES を地形 (height: タイルの高さの格子 m、row 0 が北端) に焼く。(新しい高さ, 焼いた名所の和名のリスト)。
    road_w (道路の重み 0..1) のある所は元の高さ (焼いた路面) を残す。"ground" の高さは ref (道路を焼く前の地形
    height_m.npy) で決める (何度焼いても同じ高さになるように)。"""
    from build_scenery import Grid   # build_scenery は重いので、使うときだけ読む

    grid = Grid(area, height if ref is None else ref)
    spots = [sp for sp in find(area, grid, roads, names) if terraces_of(sp[1], sp[2])]
    if not spots:
        return height, []
    h = height.astype(np.float64)
    n = h.shape[0]
    mpp = area.meters_per_px
    jobs = []
    for _, mod, ctx in spots:   # 高さの目標は、平らにする前の地面で決める
        for t in terraces_of(mod, ctx):
            if t["kind"] == "rect":
                cs, cu = (t["s"][0] + t["s"][1]) / 2, (t["u"][0] + t["u"][1]) / 2
                reach = math.hypot(t["s"][1] - t["s"][0], t["u"][1] - t["u"][0]) / 2
            else:
                cs, cu, reach = t["s"], t["u"], t["r"]
            if t["z"] == "road" and ctx.road:
                z = ctx.road["z"]
            else:
                z = ctx.ground(*ctx.frame(cs, cu))
            jobs.append((ctx, t, cs, cu, reach + t.get("feather", 2.0), z + t.get("dz", 0.0)))
    for ctx, t, cs, cu, reach, z in jobs:
        cx, cy = ctx.frame(cs, cu)
        c0, r0 = (cx + area.half_m) / mpp, (cy + area.half_m) / mpp
        pad = reach / mpp + 2
        cmin, cmax = max(int(c0 - pad), 0), min(int(c0 + pad) + 1, n - 1)
        rmin, rmax = max(int(r0 - pad), 0), min(int(r0 + pad) + 1, n - 1)
        if cmin > cmax or rmin > rmax:
            continue
        cc, rr = np.meshgrid(np.arange(cmin, cmax + 1), np.arange(rmin, rmax + 1))
        s, u = ctx.to_frame(cc * mpp - area.half_m, rr * mpp - area.half_m)
        if t["kind"] == "rect":
            ds = np.maximum(np.maximum(t["s"][0] - s, s - t["s"][1]), 0.0)
            du = np.maximum(np.maximum(t["u"][0] - u, u - t["u"][1]), 0.0)
            d = np.hypot(ds, du)
        else:
            d = np.maximum(np.hypot(s - t["s"], u - t["u"]) - t["r"], 0.0)
        x = np.clip(d / max(t.get("feather", 2.0), 1e-3), 0.0, 1.0)
        w = 1.0 - x * x * (3.0 - 2.0 * x)
        win = (slice(rmin, rmax + 1), slice(cmin, cmax + 1))
        h[win] = h[win] * (1.0 - w) + z * w
    if road_w is not None:
        h = h * (1.0 - road_w) + height * road_w
    return h.astype(np.float32), [mod.NAME_JA for _, mod, _ in spots]


def build(spots):
    """{メッシュ名: Mesh} (タイルの原点に置く形)。"""
    meshes = {}
    for name, mod, ctx in spots:
        m = mod.build(ctx)
        m.name = mesh_name(name)
        meshes[m.name] = m
    return meshes
