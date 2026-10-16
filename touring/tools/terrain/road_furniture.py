"""道路の付属物 (区画線・側溝・電柱と電線・標識) の置き場所を決める。build_scenery.py から呼ぶ。

電柱・標識・電線は同じ形を並べるだけ (UE では FDInstances、当たり判定なし) なので、数が多くても軽い。
置き場所は scenery.json の instances に [x, y, z, yaw, 拡大率, pitch] (cm, 度) で入る。
電線は「X だけ拡大」(stretch_x) で長さを合わせ、pitch で坂に沿わせる。
区画線と側溝は、短い部品を並べると継ぎ目で向きや高さがずれてがたがたに見えるので、道路に沿ってつながった形
(全部の道路の分をまとめた1つのメッシュ、原点に置く。scenery.json の world_meshes) にする。

決め方
- 中央線: 幅 5.5m 以上の対面通行の道路。白の破線 (5m 引いて 5m あける)。半径 120m より急なカーブ (見通しが悪い所) は黄色の実線
- 外側線: 主要道路と幅 5.5m 以上の道路。舗装の端から 0.5m 内側に白の実線。脇道との交差部はあける
- 側溝: 主要道路の両側の舗装の端 (L 形のコンクリート)。交差部はあける
- 電柱: 主要道路と県道クラスの道路の山側 (路肩の外の地面が高い側) に約 35m おき。隣の電柱と電線でつなぐ
- 防犯灯: 電柱の 3 本に 1 本と、交差部の近くの電柱に、道路の側へ腕を出した LED の街灯。光源の位置は scenery.json の lights
- 標識: 左側通行なので進む向きの左の路肩に、こちらを向けて立てる。
  県道の番号 (ref がある道路) は約 1.2km おき、最高速度 40km/h は約 0.9km おき、
  急なカーブ (半径 80m より急) の約 50m 手前にカーブの警戒標識
"""

import math

import numpy as np

import scenery_meshes as sm

LINE_W_M = 0.15
DASH_M, GAP_M = 5.0, 5.0
LINE_MIN_ROAD_W_M = 5.5
EDGE_INSET_M = 0.5
YELLOW_RADIUS_M = 120.0
YELLOW_EXTEND_M = 30.0         # 黄色の区間をカーブの前後に延ばす長さ
CURVE_WINDOW_M = 30.0          # カーブの半径を測る区間の長さ
GUTTER_W_M = 0.42
JUNCTION_EXTRA_M = 2.5         # 交差する道路の幅にこれを足した範囲は線や側溝をあける

POLE_SPACING_M = 35.0
POLE_OFFSET_M = 1.3            # 舗装の端から電柱の中心まで
POLE_SHIFT_M = 8.0             # 交差部にかかるときに前後へずらす距離の上限
POLE_MAX_SPAN_M = 60.0         # これより離れた電柱は電線でつながない
POLE_GROUND_DZ_M = (-1.5, 4.0)  # 路面からの地面の高さがこの範囲の所にだけ立てる
TRANSFORMER_EVERY = 5          # 何本おきに柱上変圧器を付けるか
CLEAR_TORII_M = 70.0           # 鳥居の前 (夫婦岩が見える浜) には電柱と標識を立てない
# 防犯灯 (電柱に付けた LED の街灯)。田舎の県道なので、数本おきと交差部の近くだけ
LAMP_EVERY = 3                 # 何本おきに付けるか
LAMP_JUNCTION_M = 15.0         # 交差部からこの距離までの電柱には必ず付ける
LAMP_TILT_DEG = 15.0           # 光を真下から道路の側へ傾ける角度

SIGN_OFFSET_M = 0.7
ROUTE_SIGN_EVERY_M = 1200.0
SPEED_SIGN_EVERY_M = 900.0
SPEED_LIMIT = "40"
CURVE_SIGN_RADIUS_M = 80.0
CURVE_SIGN_BEFORE_M = 50.0
CURVE_JOIN_M = 80              # これより近いカーブは続きとみなし、標識は1つ目の手前にだけ立てる
SIGN_MIN_GAP_M = 25.0

SMOOTH_POINTS = 7              # 中心線の折れ目を丸める幅 (1m おきの点の数)
ROAD_Z_OFFSET_CM = 5.0         # roads.json の Z は路面より 5cm 上 (build_roads.ROAD_Z_OFFSET_M)


# ---------------------------------------------------------------- 道路の形
class Path:
    """道路の中心線を 1m おきにしたもの。s は始点からの水平距離 (m)。"""

    def __init__(self, road):
        pts = np.asarray(road["points_cm"], float)
        seg = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)]) / 100
        keep = np.concatenate([[True], seg > 1e-3])
        pts, s = pts[keep], s[keep]
        self.length = float(s[-1])
        self.s = np.arange(0.0, self.length, 1.0)
        if self.length - self.s[-1] > 1e-3:
            self.s = np.append(self.s, self.length)
        self.p = np.stack([np.interp(self.s, s, pts[:, k]) for k in range(3)], 1)
        self.p[:, 2] -= ROAD_Z_OFFSET_CM
        # OSM の線は点で折れ曲がる。そのまま横へずらすと、折れ目で線が途切れて横にずれる (外側はすき間、内側は重なる)。
        # 中心線の折れ目を丸めてからずらす (舗装は焼き込んだ線のままなので、丸めは小さく: 30° の折れ目で約 0.5m 内へ)
        k = SMOOTH_POINTS // 2
        if len(self.p) > SMOOTH_POINTS:
            pad = np.pad(self.p[:, :2], ((k, k), (0, 0)), mode="edge")
            box = np.ones(SMOOTH_POINTS) / SMOOTH_POINTS
            self.p[:, :2] = np.stack([np.convolve(pad[:, j], box, "valid") for j in range(2)], 1)
        d = np.gradient(self.p[:, :2], axis=0)
        self.d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        # UE は +Y が南。進む向きの右手 (上から見て時計回りに 90°) は (-dy, dx)
        self.right = np.stack([-self.d[:, 1], self.d[:, 0]], 1)
        self.heading = np.unwrap(np.arctan2(self.d[:, 1], self.d[:, 0]))
        self.half_m = road["width_cm"] / 200

    def at(self, s, offset_m=0.0):
        """距離 s の所から、右へ offset_m ずらした点 (cm)。"""
        p = np.array([np.interp(s, self.s, self.p[:, k]) for k in range(3)])
        h = np.interp(s, self.s, self.heading)
        right = np.array([-math.sin(h), math.cos(h)])
        p[:2] += right * offset_m * 100
        return p, h

    def signed_curvature(self):
        """各点の曲がり具合 (1/m)。正は右カーブ (UE は +Y が南なので、向きの角度が増えると右へ曲がる)。"""
        k = max(1, int(CURVE_WINDOW_M / 2))
        h = self.heading
        idx = np.arange(len(h))
        a, b = np.clip(idx - k, 0, len(h) - 1), np.clip(idx + k, 0, len(h) - 1)
        span = np.maximum(self.s[b] - self.s[a], 1.0)
        return (h[b] - h[a]) / span


def segment_item(p0, p1, length_unit=1.0):
    """p0 から p1 (cm) へ伸びる形 (長さ length_unit m) の置き方 [x, y, z, yaw, X の拡大率, pitch]。"""
    m = (p0 + p1) / 2
    d = p1 - p0
    horiz = math.hypot(d[0], d[1])
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = math.degrees(math.atan2(d[2], horiz))
    return [round(float(m[0]), 1), round(float(m[1]), 1), round(float(m[2]), 1), round(yaw, 2),
            round(float(np.linalg.norm(d)) / 100 / length_unit, 4), round(pitch, 3)]


def ribbon(path, s0, s1, offset_m, half_w_m, grid=None, tol_cm=1.0):
    """s0..s1 を道路に沿ってつながった1本の帯にするための点列。(中心 (K,3) m, 右向き (K,2)) を返す。
    1m おきに取り、まっすぐで平らな所は点を間引く (横と高さのずれが tol_cm 以下なら飛ばす)。
    grid があれば、帯の中心と両端の地面が路面より高い所では地面に合わせて持ち上げる (埋もれないように)。"""
    ss = np.arange(s0, s1, 1.0)
    ss = np.append(ss, s1) if len(ss) == 0 or s1 - ss[-1] > 0.05 else ss
    if len(ss) < 2:
        return None, None
    h = np.interp(ss, path.s, path.heading)
    right = np.stack([-np.sin(h), np.cos(h)], 1)
    c = np.stack([np.interp(ss, path.s, path.p[:, k]) for k in range(3)], 1)
    c[:, :2] += right * offset_m * 100
    if grid is not None:
        zs = [c[:, 2]]
        for lat in (0.0, half_w_m, -half_w_m):
            q = c[:, :2] + right * lat * 100
            zs.append(np.nan_to_num(grid.height_m(q[:, 0], q[:, 1]) * 100, nan=-1e9))
        c[:, 2] = np.max(zs, axis=0)
    keep = [0]
    i = 0
    while i < len(c) - 1:
        j = i + 1
        while j + 1 < len(c) and j + 1 - i <= 8:
            t = (np.arange(i + 1, j + 1) - i) / (j + 1 - i)
            chord = c[i] + (c[j + 1] - c[i]) * t[:, None]
            if np.abs(c[i + 1:j + 1] - chord).max() > tol_cm:
                break
            j += 1
        keep.append(j)
        i = j
    return c[keep] / 100, right[keep]


def runs(flags, join_gap=0):
    """True が続く区間の (始め, 終わり+1) の一覧。join_gap 以下のすき間でへだてられた区間は1つにする。"""
    f = np.concatenate([[False], np.asarray(flags, bool), [False]])
    d = np.diff(f.astype(int))
    out = []
    for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
        if out and a - out[-1][1] <= join_gap:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


# ---------------------------------------------------------------- 交差部
class Junctions:
    """1m 格子に道路の向きを塗り、ある点が「向きの違う道路」の幅の中かを調べる (交差部の判定)。
    同じ向きの道路 (OSM で途中で分かれた同じ道路) は交差部とみなさない。"""

    def __init__(self, grid, roads):
        self.grid = grid
        n = grid.n
        self.dirs = [np.full((n, n), 255, np.uint8), np.full((n, n), 255, np.uint8)]  # 向き (0..179 度)、255 は無し
        for r in sorted(roads, key=lambda r: r["priority"]):
            path = Path(r)
            if len(path.s) < 2:
                continue
            rad = path.half_m + JUNCTION_EXTRA_M
            ang = (np.degrees(np.arctan2(path.d[:, 1], path.d[:, 0])) % 180).astype(np.uint8)
            c, w = grid.ue_to_px(path.p[:, 0], path.p[:, 1])
            ri = int(math.ceil(rad / grid.mpp))
            for dy in range(-ri, ri + 1):
                for dx in range(-ri, ri + 1):
                    if dx * dx + dy * dy > (rad / grid.mpp) ** 2:
                        continue
                    yy, xx = np.round(w).astype(int) + dy, np.round(c).astype(int) + dx
                    ok = (yy >= 0) & (xx >= 0) & (yy < n) & (xx < n)
                    yy, xx, a = yy[ok], xx[ok], ang[ok]
                    first, second = self.dirs
                    empty = first[yy, xx] == 255
                    first[yy[empty], xx[empty]] = a[empty]
                    diff = angle_diff(first[yy, xx], a)
                    other = ~empty & (diff > 30)
                    second[yy[other], xx[other]] = a[other]

    def crossing(self, x_cm, y_cm, heading_rad):
        """(x, y) が向き heading と 35° 以上違う道路の幅の中なら True。"""
        c, w = self.grid.ue_to_px(np.atleast_1d(x_cm), np.atleast_1d(y_cm))
        c, w = np.round(c).astype(int), np.round(w).astype(int)
        n = self.grid.n
        ok = (c >= 0) & (w >= 0) & (c < n) & (w < n)
        a = (np.degrees(np.atleast_1d(heading_rad)) % 180).astype(np.uint8)
        out = np.zeros(len(c), bool)
        for layer in self.dirs:
            v = np.full(len(c), 255, np.uint8)
            v[ok] = layer[w[ok], c[ok]]
            out |= (v != 255) & (angle_diff(v, a) > 35)
        return out


def angle_diff(a, b):
    d = np.abs(a.astype(int) - b.astype(int)) % 180
    return np.minimum(d, 180 - d)


# ---------------------------------------------------------------- 区画線・側溝
class Drawn:
    """引いた線の位置 (1m 格子) と、どの道路が引いたか。
    OSM で同じ所に重なった道路や、つなぎ目で重なる区間に、線や側溝が二重に引かれないようにする。"""

    def __init__(self, grid):
        self.grid = grid
        self.owner = np.full((grid.n, grid.n), -1, np.int16)

    def _cells(self, q):
        c, w = self.grid.ue_to_px(q[:, 0], q[:, 1])
        return np.round(w).astype(int), np.round(c).astype(int)

    def taken(self, q, rid):
        """q (cm) の各点のまわり 1 マスに、別の道路が引いた線があれば True。"""
        n = self.grid.n
        w, c = self._cells(q)
        out = np.zeros(len(q), bool)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yy, xx = w + dy, c + dx
                ok = (yy >= 0) & (xx >= 0) & (yy < n) & (xx < n)
                v = np.full(len(q), -1, np.int16)
                v[ok] = self.owner[yy[ok], xx[ok]]
                out |= (v >= 0) & (v != rid)
        return out

    def mark(self, q, rid):
        n = self.grid.n
        w, c = self._cells(q)
        ok = (w >= 0) & (c >= 0) & (w < n) & (c < n)
        self.owner[w[ok], c[ok]] = rid

def lined(r):
    return not (r["tunnel"] or r["bridge"]) and (r["priority"] <= 1 or r["width_cm"] >= LINE_MIN_ROAD_W_M * 100)


LINE_PROFILE = ((LINE_W_M / 2, 0.025), (-LINE_W_M / 2, 0.025), (-LINE_W_M / 2, -0.045), (LINE_W_M / 2, -0.045))
# 側溝 (外向きの位置 m, 高さ m)。底の板と外側の縁
GUTTER_PROFILES = (
    ((GUTTER_W_M / 2, 0.02), (-GUTTER_W_M / 2, 0.02), (-GUTTER_W_M / 2, -0.10), (GUTTER_W_M / 2, -0.10)),
    ((GUTTER_W_M / 2, 0.06), (GUTTER_W_M / 2 - 0.08, 0.06), (GUTTER_W_M / 2 - 0.08, 0.0), (GUTTER_W_M / 2, 0.0)),
)


def place_lines(grid, roads, junctions):
    """区画線と側溝を、道路に沿ってつながった形 (道路ごとの細長いメッシュをまとめた1つのメッシュ) で作る。
    短い部品を並べると、継ぎ目で向きや高さがずれてがたがたに見えるため。"""
    white = sm.Mesh("SM_FD_RoadMarkWhite", flat=True)
    yellow = sm.Mesh("SM_FD_RoadMarkYellow", flat=True)
    gutter = sm.Mesh("SM_FD_RoadGutterStrip", flat=True)
    total = {"white": 0.0, "yellow": 0.0, "gutter": 0.0}

    def add(mesh, key, path, s0, s1, off, profile, half_w, outward=1):
        if s1 - s0 < 0.3:
            return
        c, right = ribbon(path, s0, s1, off, half_w, grid)
        if c is None:
            return
        mat = {"white": "FD_RoadWhite", "yellow": "FD_RoadYellow", "gutter": "FD_Concrete"}[key]
        mesh.add(mat, *sm.profile_sweep(c, right * outward, profile))
        total[key] += s1 - s0

    center_drawn, edge_drawn, gutter_drawn = Drawn(grid), Drawn(grid), Drawn(grid)
    for rid, r in enumerate(roads):
        if not lined(r):
            continue
        path = Path(r)
        if path.length < 10:
            continue
        # 中央線
        if not r["oneway"] and r["width_cm"] >= LINE_MIN_ROAD_W_M * 100:
            free = ~center_drawn.taken(path.p[:, :2], rid)
            sharp = np.abs(path.signed_curvature()) > 1 / YELLOW_RADIUS_M
            ext = int(YELLOW_EXTEND_M)
            sharp = np.convolve(sharp.astype(int), np.ones(2 * ext + 1))[ext:ext + len(sharp)] > 0  # "same" は道路が窓より短いと長さが変わる
            for a, b in runs(sharp & free):
                add(yellow, "yellow", path, path.s[a], path.s[min(b, len(path.s) - 1)], 0.0, LINE_PROFILE, LINE_W_M / 2)
            s = 0.0
            while s < path.length:
                e = min(s + DASH_M, path.length)
                i0, i1 = int(s), min(int(e), len(path.s) - 1)
                if not sharp[i0:i1 + 1].any() and free[i0:i1 + 1].all():
                    add(white, "white", path, s, e, 0.0, LINE_PROFILE, LINE_W_M / 2)
                s += DASH_M + GAP_M
            center_drawn.mark(path.p[free, :2], rid)
        # 外側線と側溝 (交差部と、別の道路がもう引いた所はあける)
        for side in (1, -1):
            off = side * (path.half_m - EDGE_INSET_M)
            q = path.p[:, :2] + path.right * off * 100
            clear = ~junctions.crossing(q[:, 0], q[:, 1], path.heading) & ~edge_drawn.taken(q, rid)
            for a, b in runs(clear):
                if b - a >= 3:
                    add(white, "white", path, path.s[a], path.s[b - 1], off, LINE_PROFILE, LINE_W_M / 2)
                    edge_drawn.mark(q[a:b], rid)
            if r["priority"] > 1:
                continue
            goff = side * (path.half_m + GUTTER_W_M / 2)
            q = path.p[:, :2] + path.right * goff * 100
            clear = ~junctions.crossing(q[:, 0], q[:, 1], path.heading) & ~gutter_drawn.taken(q, rid)
            for a, b in runs(clear):
                if b - a >= 3:
                    gutter_drawn.mark(q[a:b], rid)
                    for prof in GUTTER_PROFILES:  # 外側の縁は道路の外の側 (左の側溝は右向きを反対にする)
                        add(gutter, "gutter", path, path.s[a], path.s[b - 1], goff, prof, GUTTER_W_M / 2, side)
                    total["gutter"] -= path.s[b - 1] - path.s[a]  # 2つの形で同じ区間を2回数えたので1回分引く
    print(f"区画線 白 {total['white'] / 1000:.1f} km、黄 {total['yellow'] / 1000:.1f} km、側溝 {total['gutter'] / 1000:.1f} km")
    return {m.name: m for m in (white, yellow, gutter) if m.parts}


# ---------------------------------------------------------------- 電柱
def place_poles(grid, roads, junctions, torii_cm):
    """(電柱・電線の instances, 防犯灯の光源 [[x, y, z, yaw, pitch] ...]) を返す。"""
    poles, poles_t, wires, lamps, lights = [], [], [], [], []
    for r in roads:
        if r["priority"] > 2 or r["tunnel"] or r["bridge"]:
            continue
        path = Path(r)
        if path.length < POLE_SPACING_M * 2:
            continue
        # 山側: 路肩の外 12m の地面が高い側 (道路全体で多い方)
        probe = [path.p[:, :2] + path.right * side * (path.half_m + 12) * 100 for side in (1, -1)]
        hz = [np.nan_to_num(grid.height_m(q[:, 0], q[:, 1]), nan=-99.0) for q in probe]
        side = 1 if np.sum(hz[0] > hz[1]) >= len(path.s) / 2 else -1
        off = side * (path.half_m + POLE_OFFSET_M)
        placed = []
        count = 0
        for s in np.arange(POLE_SPACING_M / 2, path.length - 5, POLE_SPACING_M):
            spot = None
            for shift in (0, 3, -3, 6, -6, POLE_SHIFT_M, -POLE_SHIFT_M):
                ss = s + shift
                if not 0 <= ss <= path.length:
                    continue
                p, h = path.at(ss, off)
                g = grid.height_m(p[0], p[1])[0]
                if np.isnan(g) or g < 0.3:
                    continue
                dz = g - p[2] / 100
                if not POLE_GROUND_DZ_M[0] <= dz <= POLE_GROUND_DZ_M[1]:
                    continue
                if torii_cm is not None and math.hypot(p[0] - torii_cm[0], p[1] - torii_cm[1]) < CLEAR_TORII_M * 100:
                    continue
                # 交差部と、電柱のまわり 2m に別の道路がかからない所
                if junctions.crossing(p[0], p[1], h)[0]:
                    continue
                spot = (p[0], p[1], g * 100, h, ss)
                break
            if spot is None:
                placed.append(None)
                continue
            x, y, z, h, ss = spot
            item = [round(float(x), 1), round(float(y), 1), round(float(z) - 5, 1), round(math.degrees(h), 2), 1.0]
            count += 1
            (poles_t if count % TRANSFORMER_EVERY == 0 else poles).append(item)
            placed.append(np.array([x, y, z]))
            if count % LAMP_EVERY == 1 or near_junction(path, junctions, ss):
                lamp, light = pole_lamp(item, side)
                lamps.append(lamp)
                lights.append(light)
        for a, b in zip(placed[:-1], placed[1:]):
            if a is None or b is None or np.linalg.norm(b[:2] - a[:2]) / 100 > POLE_MAX_SPAN_M:
                continue
            o = np.array([0, 0, sm.WIRE_ORIGIN_Z_M * 100])
            wires.append(segment_item(a + o, b + o, sm.WIRE_SPAN_M)[:6])
            # segment_item は中点に置く。電線の形は始めの電柱が原点なので、始点に置き直す
            wires[-1][:3] = [round(float(v), 1) for v in (a + o)]
    return {"SM_FD_RoadPole": poles, "SM_FD_RoadPoleT": poles_t, "SM_FD_RoadWires": wires, "SM_FD_RoadLamp": lamps}, lights


def near_junction(path, junctions, s):
    """道路の距離 s の前後 LAMP_JUNCTION_M に交差部 (向きの違う道路) があるか。"""
    for k in np.arange(-LAMP_JUNCTION_M, LAMP_JUNCTION_M + 0.1, 5.0):
        if 0 <= s + k <= path.length:
            p, h = path.at(s + k)
            if junctions.crossing(p[0], p[1], h)[0]:
                return True
    return False


def pole_lamp(pole_item, side):
    """電柱 pole_item に付ける防犯灯の (置き方, 光源 [x, y, z, yaw, pitch])。
    防犯灯の形は腕が +Y へ伸びているので、+Y が道路の側を向くように回す。電柱は道路の右 (side = 1) か左 (-1) にある。"""
    x, y, z, yaw = pole_item[:4]
    lamp_yaw = (yaw + (180.0 if side > 0 else 0.0)) % 360
    a = math.radians(lamp_yaw)
    _, head_y, head_z = sm.LAMP_LIGHT_M
    # 形の +Y を lamp_yaw だけ回すと (-sin, cos) を向く
    lx, ly = x - math.sin(a) * head_y * 100, y + math.cos(a) * head_y * 100
    lamp = [x, y, z, round(lamp_yaw, 2), 1.0]
    light = [round(lx, 1), round(ly, 1), round(z + head_z * 100, 1), round((lamp_yaw + 90.0) % 360, 2), -90.0 + LAMP_TILT_DEG]
    return lamp, light


# ---------------------------------------------------------------- 標識
def place_signs(grid, roads, junctions, torii_cm):
    out = {}
    taken = []

    def put(name, path, s, direction):
        """進む向き direction (+1 は点の順) の左の路肩に、こちらへ向けて立てる。"""
        for shift in (0, 5, -5, 10, -10, 15):
            ss = s + shift * direction
            if not 0 <= ss <= path.length:
                continue
            p, h = path.at(ss, -direction * (path.half_m + SIGN_OFFSET_M))
            travel = h if direction > 0 else h + math.pi
            if torii_cm is not None and math.hypot(p[0] - torii_cm[0], p[1] - torii_cm[1]) < CLEAR_TORII_M * 100:
                return
            if junctions.crossing(p[0], p[1], h)[0]:
                continue
            if any(math.hypot(p[0] - t[0], p[1] - t[1]) < SIGN_MIN_GAP_M * 100 for t in taken):
                continue
            g = grid.height_m(p[0], p[1])[0]
            if np.isnan(g) or g * 100 < p[2] - 150:   # 路肩の外が落ち込んでいる所 (崖や海) には立てない
                continue
            z = min(p[2], g * 100)
            taken.append(p)
            yaw = math.degrees(travel) + 180.0  # 板は +X を向いているので、進む向きと反対へ向ける
            out.setdefault(name, []).append([round(float(p[0]), 1), round(float(p[1]), 1), round(float(z), 1),
                                             round(yaw % 360, 2), 1.0])
            return

    refs = set()
    for r in roads:
        if r["tunnel"] or r["bridge"]:
            continue
        path = Path(r)
        if path.length < 60:
            continue
        for direction in (1, -1):
            if r["oneway"] and direction < 0:
                continue
            # 進む向きの距離 t を、点の順の距離 s に直す
            to_s = (lambda t: t) if direction > 0 else (lambda t: path.length - t)
            if r["priority"] <= 1:
                ref = r["ref"] if r["ref"].isdigit() else ""
                if ref:
                    refs.add(ref)
                    for t in np.arange(150.0, path.length - 50, ROUTE_SIGN_EVERY_M):
                        put(f"SM_FD_RoadSignRoute{ref}", path, to_s(t), direction)
                for t in np.arange(450.0, path.length - 50, SPEED_SIGN_EVERY_M):
                    put(f"SM_FD_RoadSignSpeed{SPEED_LIMIT}", path, to_s(t), direction)
            if r["priority"] <= 2:
                k = path.signed_curvature() * direction
                if direction < 0:
                    k = k[::-1]   # 進む向きの順に並べ直す
                sharp = np.abs(k) > 1 / CURVE_SIGN_RADIUS_M
                for a, b in runs(sharp, CURVE_JOIN_M):
                    if np.sign(k[a:b]).std() > 0.9:   # S 字 (左右が入れ替わる) は最初の向きで
                        b = a + int(np.argmax(np.sign(k[a:b]) != np.sign(k[a])) or b - a)
                    t = float(a) - CURVE_SIGN_BEFORE_M
                    if t < 10:
                        continue
                    right = k[a:b].mean() > 0
                    put("SM_FD_RoadSignCurve" + ("R" if right else "L"), path, to_s(t), direction)
    return out, sorted(refs)


# ---------------------------------------------------------------- まとめ
def place_road_furniture(grid, roads, torii_cm, markings=True, poles=True):
    """(instances, meshes, stretch_x の名前, world, lights) を返す。world は原点に1つ置く、道路に沿ったつながった形 (区画線・側溝)。
    lights は夜に点く光源 {種類: [[x, y, z, yaw, pitch] ...]} (UE の FDNightLights が置く)。
    markings: 区画線・側溝・標識、poles: 電柱・電線・防犯灯。"""
    junctions = Junctions(grid, roads)
    world, instances, meshes, stretch, lights = {}, {}, {}, [], {}
    if markings:
        world = place_lines(grid, roads, junctions)
        signs, refs = place_signs(grid, roads, junctions, torii_cm)
        instances.update(signs)
        meshes.update({
            f"SM_FD_RoadSignSpeed{SPEED_LIMIT}": sm.speed_sign(SPEED_LIMIT),
            "SM_FD_RoadSignCurveL": sm.curve_sign(False),
            "SM_FD_RoadSignCurveR": sm.curve_sign(True),
        })
        for ref in refs:
            if signs.get(f"SM_FD_RoadSignRoute{ref}"):   # 1つも立たなかった番号の標識は作らない
                meshes[f"SM_FD_RoadSignRoute{ref}"] = sm.route_sign(ref)
    if poles:
        pole_items, lamp_lights = place_poles(grid, roads, junctions, torii_cm)
        instances.update(pole_items)
        meshes.update({
            "SM_FD_RoadPole": sm.utility_pole("SM_FD_RoadPole"),
            "SM_FD_RoadPoleT": sm.utility_pole("SM_FD_RoadPoleT", transformer=True),
            "SM_FD_RoadWires": sm.power_lines(),
            "SM_FD_RoadLamp": sm.pole_lamp(),
        })
        stretch = ["SM_FD_RoadWires"]
        lights = {"RoadLamp": lamp_lights}
    instances = {k: v for k, v in instances.items() if v}
    return instances, meshes, stretch, world, lights
