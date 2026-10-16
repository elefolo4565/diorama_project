"""景観物 (夫婦岩・しめ縄・白い鳥居・ガードレール・木) の形と置き場所を作る。

apply_roads.py の後に実行する。UE への配置は tools/ue/setup_project.py が scenery.json を読んで行う。

使い方:
    python build_scenery.py areas/futamigaura.json

出力 (out/<エリア名>/scenery/):
    *.gltf        景観物の形 (UE に取り込む)
    scenery.json  置き場所 (UE 座標 cm)
    preview.png   木 (緑)・ガードレール (白)・岩と鳥居 (赤)・電柱 (青)・防犯灯 (黄)・標識 (紫)・花と桜 (花の色) の配置の確認用画像

置き方の決め方
- 夫婦岩: OSM の「夫婦岩」の近くにある、標高データ上の小さな島2つ。大きい方を男岩とする
- 鳥居: OSM の「Tori Viewpoint」の位置に、夫婦岩の方を向けて置く
- ガードレール: 主要道路 (県道) の路肩の外が 2.5m 以上落ち込んでいる所。脇道との交差部はあける
- 木: 斜面と標高の高い所は森 (広葉樹が主、尾根は松が混じる)、海岸の近くは松、平地 (田畑) はまばら
- 道路の付属物 (区画線・側溝・電柱と電線・防犯灯・標識): road_furniture.py
- 季節の花と桜並木: flowers.py
- 足した植物 (plants/<種類>.py): habitat の所の木の一部を入れ替えるか、森の木の足もとに足す (plants/__init__.py)
- 建物 (地理院と OSM の輪郭、夜は窓が灯る): buildings.py。建物の上と周りの木や花は除く
- 神社 (鳥居・参道・灯籠・狛犬・拝殿・本殿・鎮守の森): shrines.py。コースの "features" の "shrines" が true のとき
- 線路と駅 (道床・枕木・レール・踏切・架線・鉄橋・トンネルの入口・ホーム・駅舎): railways.py。"railways" が true のとき
  (道床は apply_roads.py が地形に焼いてある)。線路とホームの上の木・花・建物は除く
- 名所 (その土地にしかない記念碑・建物、meisho/<名前>.py): タイルの中にある名所を地形に合わせて作る。周りの木・花・家はよける
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image

import bark
import building_textures
import buildings
import flowers
import meisho
import plants
import railways
import road_furniture
import shrines
import foliage as fo
import scenery_meshes as sm
from course import course_features, course_of_area, course_overrides
from geo import Area
from road_furniture import Path, place_road_furniture
from road_furniture import runs as road_runs

SEED = 20261012

ROCK_SEARCH_M = 120.0       # OSM の夫婦岩の点からこの範囲の島を探す
ROCKS = (("男岩", 11.8, 5.2), ("女岩", 11.2, 4.4))  # (名前, 海面からの高さ m, 根元の半径 m)
ROPE_ANCHOR_FRACTION = 0.8  # しめ縄を結ぶ高さ (岩の高さに対する割合)
ROPE_SAG_M = 3.0

GUARDRAIL_SEGMENT_M = 4.0
GUARDRAIL_DROP_M = 2.5      # 路肩の外がこれ以上低ければガードレールを付ける
GUARDRAIL_LOOK_M = (3.0, 6.0, 9.0, 12.0)  # 路肩からこの距離の地面の高さを見る
GUARDRAIL_MIN_RUN = 4       # これより短い (区間数) ものは付けない
GUARDRAIL_FILL_GAP = 2      # これ以下のすき間は埋める
GUARDRAIL_CLEAR_TORII_M = 70.0  # 鳥居の前の浜はあけておく (海が見えるように)

TREE_SPACING_M = 9.0        # 森の木の間隔 (ずらした格子)
TREE_FAR_FROM_ROAD_M = 350.0   # 主要な道路からこれより遠い所は木を減らす
TREE_FAR_DENSITY = 0.35
TREE_ROAD_CLEAR_M = 3.0     # 路肩から木までの最低の距離
TREE_MIN_Z_M = 2.5          # これより低い所 (砂浜・海) には木を置かない (砂浜は海面 +2.2m まで)
COAST_PINE_M = 100.0        # 海からこの距離までは松林
FARM_MAX_SLOPE_DEG = 5.0    # これより緩く、標高が FARM_MAX_Z_M 未満なら田畑とみなす
FARM_MAX_Z_M = 30.0
TREE_CLEAR_TORII_M = 35.0
# 竹林: 里山の谷あい (田畑に近い緩い斜面) に、まとまって生える
BAMBOO_SLOPE_DEG = (6.0, 25.0)
BAMBOO_Z_M = (5.0, 80.0)
BAMBOO_PATCH = 0.3         # まとまりの多さ (0..1、大きいほど竹林が広い)
# スギの植林地: 標高の高い急な斜面に、まとまって植わっている
CEDAR_MIN_Z_M = 70.0
CEDAR_MIN_SLOPE_DEG = 12.0
CEDAR_PATCH = 0.5
PATCH_WAVELENGTH_M = (150.0, 450.0)  # まとまりの大きさ
# 草原 (阿蘇の外輪山のような、野焼きで保たれた草原)。None なら無し。コースの設定の "vegetation" で決める
GRASSLAND_MIN_Z_M = None    # この標高より高く
GRASSLAND_MAX_SLOPE_DEG = 30.0   # この傾きより緩い所は草原 (急な谷や崖は森のまま)
GRASSLAND_TREE_P = 0.008    # 草原にぽつんと立つ茂みの割合

# ヤシ (カナリーヤシ): 県道54号の海側の路肩に並木として植える (二見ヶ浦の前後)
PALM_ROAD_REF = "54"
PALM_RANGE_M = 1500.0       # 鳥居からこの距離までの区間
PALM_SPACING_M = 24.0
PALM_OFFSET_M = 3.5         # 路肩からの距離
PALM_GROUND_Z_M = (0.6, 8.0)

TREE_KINDS = {
    # 種類: (メッシュの作り方, 1本の高さの目安 m)
    "SM_FD_Pine_A": lambda: fo.pine("SM_FD_Pine_A", 11, 9.0),
    "SM_FD_Pine_B": lambda: fo.pine("SM_FD_Pine_B", 12, 11.0),
    "SM_FD_Broadleaf_A": lambda: fo.broadleaf("SM_FD_Broadleaf_A", 21, 9.0, "shii"),
    "SM_FD_Broadleaf_B": lambda: fo.broadleaf("SM_FD_Broadleaf_B", 22, 11.0, "tabu"),
    "SM_FD_Broadleaf_C": lambda: fo.broadleaf("SM_FD_Broadleaf_C", 23, 7.5, "shii"),
    "SM_FD_Broadleaf_D": lambda: fo.broadleaf("SM_FD_Broadleaf_D", 24, 10.0, "kusu"),
    "SM_FD_Bush": lambda: fo.bush("SM_FD_Bush", 31),
    "SM_FD_Bamboo": lambda: fo.bamboo("SM_FD_Bamboo", 41),
    "SM_FD_Cedar_A": lambda: fo.cedar("SM_FD_Cedar_A", 51, 18.0),
    "SM_FD_Cedar_B": lambda: fo.cedar("SM_FD_Cedar_B", 52, 15.0),
    "SM_FD_Palm_A": lambda: sm.palm("SM_FD_Palm_A", 61, 7.0),
    "SM_FD_Palm_B": lambda: sm.palm("SM_FD_Palm_B", 62, 9.0),
}


# ---------------------------------------------------------------- 格子と座標
class Grid:
    """height_road_m.npy (row 0 = 北端 = UE の最小 Y、1px = meters_per_px m)。"""

    def __init__(self, area, h):
        self.h = h
        self.n = h.shape[0]
        self.mpp = area.meters_per_px
        self.half_cm = area.half_m * 100.0

    def ue_to_px(self, x_cm, y_cm):
        return (np.asarray(x_cm) + self.half_cm) / (self.mpp * 100), (np.asarray(y_cm) + self.half_cm) / (self.mpp * 100)

    def px_to_ue(self, col, row):
        return np.asarray(col) * self.mpp * 100 - self.half_cm, np.asarray(row) * self.mpp * 100 - self.half_cm

    def height_m(self, x_cm, y_cm):
        """双一次補間した地面の高さ (m)。範囲外は nan。"""
        c, r = self.ue_to_px(x_cm, y_cm)
        c, r = np.atleast_1d(c).astype(float), np.atleast_1d(r).astype(float)
        out = np.full(c.shape, np.nan)
        ok = (c >= 0) & (r >= 0) & (c < self.n - 1) & (r < self.n - 1)
        c0, r0 = np.floor(c[ok]).astype(int), np.floor(r[ok]).astype(int)
        fc, fr = c[ok] - c0, r[ok] - r0
        h = self.h
        out[ok] = (h[r0, c0] * (1 - fc) * (1 - fr) + h[r0, c0 + 1] * fc * (1 - fr)
                   + h[r0 + 1, c0] * (1 - fc) * fr + h[r0 + 1, c0 + 1] * fc * fr)
        return out


def dilate(mask, steps):
    """8近傍で steps 回広げる (距離のおおよその判定に使う)。"""
    m = mask.copy()
    for _ in range(steps):
        p = np.pad(m, 1)
        m = (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
             | p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:])
    return m


def densify(pts, spacing_m):
    """UE 座標 (cm) のポイント列を spacing_m 間隔に細かくする。"""
    pts = np.asarray(pts, float)
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b[:2] - a[:2]) / (spacing_m * 100))))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    return np.array(out)


def stamp_roads(grid, roads, cell_m, extra_m):
    """道路の幅 (+ extra_m) の範囲を cell_m 間隔の格子に塗る。"""
    n = int(math.ceil(grid.n * grid.mpp / cell_m))
    mask = np.zeros((n, n), bool)
    for r in roads:
        pts = densify(r["points_cm"], cell_m * 0.5)
        c, w = grid.ue_to_px(pts[:, 0], pts[:, 1])
        c, w = (c * grid.mpp / cell_m).astype(int), (w * grid.mpp / cell_m).astype(int)
        rad = int(math.ceil((r["width_cm"] / 200 + extra_m) / cell_m))
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                if dx * dx + dy * dy > rad * rad:
                    continue
                yy, xx = w + dy, c + dx
                ok = (yy >= 0) & (xx >= 0) & (yy < n) & (xx < n)
                mask[yy[ok], xx[ok]] = True
    return mask


# ---------------------------------------------------------------- 夫婦岩・鳥居
def find_islets(grid, center_cm, radius_m, min_px=20):
    """center の近くで、陸地とつながっていない海面上の小さな島 (面積の大きい順)。"""
    c, r = grid.ue_to_px(*center_cm[:2])
    rad = int(radius_m / grid.mpp)
    r0, c0 = int(r) - rad, int(c) - rad
    sub = grid.h[r0:r0 + 2 * rad, c0:c0 + 2 * rad] > 0.3
    labels = np.zeros(sub.shape, int)
    found, n = [], 0
    for y, x in zip(*np.nonzero(sub)):
        if labels[y, x]:
            continue
        n += 1
        stack, cells, edge = [(y, x)], [], False
        labels[y, x] = n
        while stack:
            a, b = stack.pop()
            cells.append((a, b))
            edge |= a in (0, sub.shape[0] - 1) or b in (0, sub.shape[1] - 1)
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                aa, bb = a + da, b + db
                if 0 <= aa < sub.shape[0] and 0 <= bb < sub.shape[1] and sub[aa, bb] and not labels[aa, bb]:
                    labels[aa, bb] = n
                    stack.append((aa, bb))
        if edge or len(cells) < min_px or len(cells) > 5000:
            continue
        ys, xs = np.array(cells).T
        x_cm, y_cm = grid.px_to_ue(xs.mean() + c0, ys.mean() + r0)
        found.append({"area_m2": len(cells) * grid.mpp ** 2, "x": float(x_cm), "y": float(y_cm)})
    return sorted(found, key=lambda f: -f["area_m2"])


def place_meoto(grid, landmarks):
    rocks_lm = next((lm for lm in landmarks if "夫婦岩" in lm["name"]), None)
    torii_lm = next((lm for lm in landmarks if "tori" in lm["name"].lower() or "鳥居" in lm["name"]), None)
    if rocks_lm is None:
        print("夫婦岩の目印がないため、夫婦岩と鳥居は置きません")
        return None
    islets = find_islets(grid, rocks_lm["location_cm"], ROCK_SEARCH_M)
    if len(islets) >= 2:
        spots = [(i["x"], i["y"]) for i in islets[:2]]
        print(f"夫婦岩: 標高データの島 {islets[0]['area_m2']:.0f} m2 / {islets[1]['area_m2']:.0f} m2")
    else:
        # 島が見つからなければ、OSM の点の両側に置く
        x, y = rocks_lm["location_cm"][:2]
        spots = [(x - 1500, y - 800), (x + 1500, y + 800)]
        print("夫婦岩: 標高データに島が見つからないため OSM の点の両側に置きます")
    mid = np.mean(spots, axis=0)
    if torii_lm:
        tx, ty = torii_lm["location_cm"][:2]
    else:
        tx, ty = mid[0] + 6000, mid[1] + 13000
    tz = float(grid.height_m(tx, ty)[0]) * 100
    torii_yaw = math.degrees(math.atan2(mid[1] - ty, mid[0] - tx))
    rocks, meshes = [], {}
    for (name, height, radius), (x, y), seed in zip(ROCKS, spots, (101, 102)):
        mesh_name = "SM_FD_MeotoIwa_" + ("Otoko" if name == "男岩" else "Me")
        meshes[mesh_name] = sm.meoto_rock(mesh_name, height, radius, seed)
        # 岩の形は Y が少しつぶれているので、広い面 (X に沿った面) を鳥居の方へ向ける
        rocks.append({"name": name, "mesh": mesh_name, "location_cm": [x, y, 0.0],
                      "yaw": torii_yaw + 90.0, "height_m": height, "radius_m": radius})
    # しめ縄: 互いに向き合う面の、高さの 8 割の所に結ぶ
    a, b = np.array(spots[0]) / 100, np.array(spots[1]) / 100
    d = (b - a) / np.linalg.norm(b - a)
    p0 = [*(a + d * ROCKS[0][2] * 0.45), ROCKS[0][1] * ROPE_ANCHOR_FRACTION]
    p1 = [*(b - d * ROCKS[1][2] * 0.45), ROCKS[1][1] * ROPE_ANCHOR_FRACTION]
    rope, origin = sm.shimenawa(p0, p1, sag=ROPE_SAG_M)
    meshes[rope.name] = rope
    meshes["SM_FD_Torii"] = sm.torii()
    return {
        "rocks": rocks,
        "rope": {"mesh": rope.name, "location_cm": (origin * 100).tolist(), "length_m": float(np.linalg.norm(b - a))},
        "torii": {"mesh": "SM_FD_Torii", "location_cm": [tx, ty, tz], "yaw": torii_yaw},
    }, meshes


# ---------------------------------------------------------------- ガードレール
def place_guardrails(grid, roads, torii_cm):
    """主要道路の、路肩の外が落ち込んでいる所にガードレールを付ける。
    支柱は GUARDRAIL_SEGMENT_M おきに並べ (FDInstances)、ビームは区間ごとに道路に沿ってつながった1本の形にする
    (4m の部品を並べると、カーブや坂の継ぎ目で折れてがたがたに見えたため)。(支柱の置き方, ビームのメッシュ) を返す。"""
    main = [r for r in roads if r["priority"] <= 1 and not r["tunnel"]]
    side = [r for r in roads if r["priority"] >= 2]
    side_mask = stamp_roads(grid, side, 1.0, 4.0)
    posts = []
    beams = sm.Mesh("SM_FD_GuardrailBeams", flat=True)
    step = int(GUARDRAIL_SEGMENT_M)
    total_m = 0.0
    for r in main:
        path = Path(r)
        if len(path.s) < 3 * step:
            continue
        for sign in (1, -1):
            n = path.right * sign
            edge = path.p[:, :2] + n * (path.half_m + 0.5) * 100
            drops = []
            for look in GUARDRAIL_LOOK_M:
                q = path.p[:, :2] + n * (path.half_m + look) * 100
                drops.append(path.p[:, 2] / 100 - grid.height_m(q[:, 0], q[:, 1]))
            drops = np.nan_to_num(np.array(drops), nan=0.0)
            want = drops.max(axis=0) > GUARDRAIL_DROP_M
            c, w = grid.ue_to_px(edge[:, 0], edge[:, 1])
            ci = np.clip(c.astype(int), 0, side_mask.shape[1] - 1)
            wi = np.clip(w.astype(int), 0, side_mask.shape[0] - 1)
            want &= ~side_mask[wi, ci]
            if torii_cm is not None:
                want &= np.hypot(edge[:, 0] - torii_cm[0], edge[:, 1] - torii_cm[1]) > GUARDRAIL_CLEAR_TORII_M * 100
            want = clean_runs(want, GUARDRAIL_FILL_GAP * step, GUARDRAIL_MIN_RUN * step)
            for a, b in road_runs(want):
                ground = grid.height_m(edge[a:b, 0], edge[a:b, 1])
                ground = np.where(np.isnan(ground), path.p[a:b, 2] / 100, ground)
                # 地面のでこぼこでビームが波打たないよう、高さを前後 5m でならす
                k = 5
                z = np.convolve(np.pad(ground, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid")
                centers = np.c_[edge[a:b] / 100, z]
                for prof in sm.GUARDRAIL_BEAMS:
                    beams.add("FD_Guardrail", *sm.profile_sweep(centers, n[a:b], prof))
                total_m += path.s[b - 1] - path.s[a]
                for i in range(a, b, step):
                    yaw = math.degrees(path.heading[i]) + (0.0 if sign > 0 else 180.0)  # 支柱の形は +Y が道路の外
                    posts.append([round(float(edge[i, 0]), 1), round(float(edge[i, 1]), 1),
                                  round(float(z[i - a]) * 100, 1), round(yaw % 360, 2), 1.0])
    return posts, beams, total_m


def clean_runs(flags, fill_gap=GUARDRAIL_FILL_GAP, min_run=GUARDRAIL_MIN_RUN):
    f = flags.copy()
    n = len(f)
    i = 0
    while i < n:  # 短いすき間を埋める
        if not f[i]:
            j = i
            while j < n and not f[j]:
                j += 1
            if i > 0 and j < n and j - i <= fill_gap:
                f[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < n:  # 短い区間を消す
        if f[i]:
            j = i
            while j < n and f[j]:
                j += 1
            if j - i < min_run:
                f[i:j] = False
            i = j
        else:
            i += 1
    return f


# ---------------------------------------------------------------- 木
def patch_field(rng, x_m, y_m):
    """なめらかに変わる 0..1 の値 (竹林や植林地のまとまりを作る)。"""
    v = np.zeros_like(x_m, dtype=float)
    for _ in range(6):
        ang = rng.uniform(0, 2 * math.pi)
        k = 2 * math.pi / rng.uniform(*PATCH_WAVELENGTH_M)
        v += np.sin((x_m * math.cos(ang) + y_m * math.sin(ang)) * k + rng.uniform(0, 2 * math.pi))
    return 0.5 + v / 6 * 1.2


def place_trees(grid, roads, keep_clear_cm, extra=None):
    """森・海岸・田畑の木。extra は plants/ の植物 ({メッシュ名: 置き方}、plants/__init__.py を参照)。"""
    rng = sm.Rng(SEED)
    cell = 8.0  # 遠さの判定に使う粗い格子 (m)
    major = [r for r in roads if r["priority"] <= 2]
    near_road = dilate(stamp_roads(grid, major, cell, 0.0), int(TREE_FAR_FROM_ROAD_M / cell))
    sea = grid.h[::int(cell), ::int(cell)] <= 0.0
    near_sea = dilate(sea, int(COAST_PINE_M / cell))
    road_clear = stamp_roads(grid, roads, 1.0, TREE_ROAD_CLEAR_M)

    # ずらした格子の候補点 (ピクセル座標)
    size_m = (grid.n - 1) * grid.mpp
    g = np.arange(TREE_SPACING_M / 2, size_m, TREE_SPACING_M)
    gx, gy = np.meshgrid(g, g)
    gx = gx + rng.uniform(-0.45, 0.45, gx.shape) * TREE_SPACING_M
    gy = gy + rng.uniform(-0.45, 0.45, gy.shape) * TREE_SPACING_M
    gx, gy = gx.ravel() / grid.mpp, gy.ravel() / grid.mpp
    ok = (gx >= 1) & (gy >= 1) & (gx < grid.n - 2) & (gy < grid.n - 2)
    gx, gy = gx[ok], gy[ok]
    ci, ri = gx.astype(int), gy.astype(int)
    z = grid.h[ri, ci]
    dzdx = (grid.h[ri, ci + 1] - grid.h[ri, ci - 1]) / (2 * grid.mpp)
    dzdy = (grid.h[ri + 1, ci] - grid.h[ri - 1, ci]) / (2 * grid.mpp)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    coarse_r = np.clip((ri * grid.mpp / cell).astype(int), 0, near_road.shape[0] - 1)
    coarse_c = np.clip((ci * grid.mpp / cell).astype(int), 0, near_road.shape[1] - 1)
    by_road = near_road[coarse_r, coarse_c]
    by_sea = near_sea[np.clip(coarse_r, 0, near_sea.shape[0] - 1), np.clip(coarse_c, 0, near_sea.shape[1] - 1)]
    rc_r = np.clip((ri * grid.mpp).astype(int), 0, road_clear.shape[0] - 1)
    rc_c = np.clip((ci * grid.mpp).astype(int), 0, road_clear.shape[1] - 1)

    farm = (slope < FARM_MAX_SLOPE_DEG) & (z < FARM_MAX_Z_M)
    p = np.where(farm, 0.04, np.clip(0.55 + slope / 60, 0.0, 0.92))
    coast = by_sea & (z < 25)
    p = np.where(coast, 0.5, p)
    px_m, py_m = gx * grid.mpp, gy * grid.mpp
    bamboo = ((slope >= BAMBOO_SLOPE_DEG[0]) & (slope <= BAMBOO_SLOPE_DEG[1]) & (z >= BAMBOO_Z_M[0]) & (z <= BAMBOO_Z_M[1])
              & ~coast & (patch_field(rng, px_m, py_m) > 1 - BAMBOO_PATCH))
    cedar = ((z >= CEDAR_MIN_Z_M) & (slope >= CEDAR_MIN_SLOPE_DEG) & ~bamboo
             & (patch_field(rng, px_m, py_m) > 1 - CEDAR_PATCH))
    grass = np.zeros_like(farm)
    if GRASSLAND_MIN_Z_M is not None:
        grass = (z >= GRASSLAND_MIN_Z_M) & (slope < GRASSLAND_MAX_SLOPE_DEG)
        bamboo, cedar = bamboo & ~grass, cedar & ~grass
    p = np.where(bamboo, 0.85, p)
    p = np.where(cedar, 0.95, p)
    p = np.where(grass, GRASSLAND_TREE_P, p)
    p = np.where(by_road, p, p * TREE_FAR_DENSITY)
    p[(z < TREE_MIN_Z_M) | road_clear[rc_r, rc_c]] = 0
    x_cm, y_cm = grid.px_to_ue(gx, gy)
    for cx, cy, rad in keep_clear_cm:
        p[np.hypot(x_cm - cx, y_cm - cy) < rad] = 0
    keep = rng.random(len(p)) < p
    x_cm, y_cm, z, slope, coast, farm = x_cm[keep], y_cm[keep], z[keep], slope[keep], coast[keep], farm[keep]
    bamboo, cedar, grass = bamboo[keep], cedar[keep], grass[keep]
    z = grid.height_m(x_cm, y_cm) * 100

    # 種類: 海岸は松、尾根 (標高の高い所) は松が混じる、ほかは広葉樹。田畑のあぜは茂みが多い
    u = rng.random(len(x_cm))
    pine_share = np.where(coast, 0.85, np.where(z > 6000, 0.35, 0.12))
    kind = np.where(u < pine_share, np.where(rng.random(len(u)) < 0.5, "SM_FD_Pine_A", "SM_FD_Pine_B"),
                    rng.choice(["SM_FD_Broadleaf_A", "SM_FD_Broadleaf_B", "SM_FD_Broadleaf_C", "SM_FD_Broadleaf_D"], len(u)))
    kind = np.where(farm & (rng.random(len(u)) < 0.6), "SM_FD_Bush", kind)
    kind = plant_kinds(kind, extra, coast, farm, grass, z)
    kind = np.where(bamboo, "SM_FD_Bamboo", kind)
    kind = np.where(grass, "SM_FD_Bush", kind)
    kind = np.where(cedar, np.where(rng.random(len(u)) < 0.5, "SM_FD_Cedar_A", "SM_FD_Cedar_B"), kind)
    scale = rng.uniform(0.75, 1.25, len(u))
    yaw = rng.uniform(0, 360, len(u))
    out = {k: [] for k in list(TREE_KINDS) + list(extra or {})}
    for k, x, y, zz, s, a in zip(kind, x_cm, y_cm, z, scale, yaw):
        out[str(k)].append([round(float(x), 1), round(float(y), 1), round(float(zz) - 10, 1), round(float(a), 1), round(float(s), 3)])
    forest = ~coast & ~farm & ~grass
    add_understory(out, extra, grid, x_cm[forest], y_cm[forest], road_clear, keep_clear_cm)
    return out


def _habitat_mask(habitat, coast, farm, grass, z):
    forest = ~coast & ~farm & ~grass
    return {"coast": coast, "farm": farm, "grassland": grass, "forest": forest, "ridge": forest & (z > 6000)}[habitat]


def plant_kinds(kind, extra, coast, farm, grass, z):
    """plants/ の植物のうち木を入れ替えるもの: habitat の所の木の share の割合を、その種類にする。
    乱数は木の並びと別にして、植物を足しても今の木の場所は変えない。"""
    if not extra:
        return kind
    rng = sm.Rng(SEED + 101)
    for name, spec in sorted(extra.items()):
        if "place_with" in spec:   # 別のメッシュと同じ所に置くもの (季節ちがいの形)
            continue
        where = np.zeros(len(kind), bool)
        for h in spec["habitat"]:
            if h in plants.REPLACE_HABITATS:
                where |= _habitat_mask(h, coast, farm, grass, z)
        if where.any():
            kind = np.where(where & (rng.random(len(kind)) < spec["share"]), name, kind)
    return kind


def add_understory(out, extra, grid, x_cm, y_cm, road_clear, keep_clear_cm):
    """plants/ の植物のうち "understory" のもの: 森の木 1 本ごとに share の確率で、その足もと (1.5〜4m 先) に 1 株足す。"""
    rng = sm.Rng(SEED + 102)
    for name, spec in sorted((extra or {}).items()):
        if "understory" not in spec["habitat"] or "place_with" in spec or not len(x_cm):
            continue
        pick = rng.random(len(x_cm)) < spec["share"]
        n = int(pick.sum())
        ang = rng.uniform(0, 2 * math.pi, n)
        dist = rng.uniform(150, 400, n)
        x, y = x_cm[pick] + np.cos(ang) * dist, y_cm[pick] + np.sin(ang) * dist
        z = grid.height_m(x, y) * 100
        c, r = grid.ue_to_px(x, y)
        rr = np.clip((np.nan_to_num(r) * grid.mpp).astype(int), 0, road_clear.shape[0] - 1)
        rc = np.clip((np.nan_to_num(c) * grid.mpp).astype(int), 0, road_clear.shape[1] - 1)
        ok = np.isfinite(z) & (z >= TREE_MIN_Z_M * 100) & ~road_clear[rr, rc]
        for cx, cy, rad in keep_clear_cm:
            ok &= np.hypot(x - cx, y - cy) >= rad
        x, y, z = x[ok], y[ok], z[ok]
        n = len(x)
        for xx, yy, zz, a, s in zip(x, y, z, rng.uniform(0, 360, n), rng.uniform(0.8, 1.2, n)):
            out.setdefault(name, []).append([round(float(xx), 1), round(float(yy), 1), round(float(zz) - 5, 1),
                                             round(float(a), 1), round(float(s), 3)])


def place_palms(grid, roads, torii_cm):
    """県道54号の海側の路肩に、ヤシを並木にする。海側は、路肩の外の地面が低い方。"""
    rng = sm.Rng(SEED + 7)
    if torii_cm is None:
        return {}
    road_clear = stamp_roads(grid, roads, 1.0, 1.5)
    out = {"SM_FD_Palm_A": [], "SM_FD_Palm_B": []}
    for r in roads:
        if r["ref"] != PALM_ROAD_REF or r["tunnel"] or r["bridge"]:
            continue
        pts = densify(r["points_cm"], 2.0)
        d = np.gradient(pts[:, :2], axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
        right = np.stack([-d[:, 1], d[:, 0]], 1)
        half = r["width_cm"] / 200
        step = int(PALM_SPACING_M / 2.0)
        start = int(rng.integers(0, step))
        for i in range(start, len(pts), step):
            if math.hypot(pts[i, 0] - torii_cm[0], pts[i, 1] - torii_cm[1]) > PALM_RANGE_M * 100:
                continue
            probe = [pts[i, :2] + right[i] * s * (half + 10) * 100 for s in (1, -1)]
            hz = [grid.height_m(q[0], q[1])[0] for q in probe]
            if any(np.isnan(hz)):
                continue
            sea_side = right[i] * (1 if hz[0] < hz[1] else -1)
            off = (half + PALM_OFFSET_M + rng.uniform(-0.5, 0.8)) * 100
            q = pts[i, :2] + sea_side * off + d[i] * rng.uniform(-200, 200)
            z = grid.height_m(q[0], q[1])[0]
            c, w = grid.ue_to_px(q[0], q[1])
            if not (PALM_GROUND_Z_M[0] <= z <= PALM_GROUND_Z_M[1]) or road_clear[int(w), int(c)]:
                continue
            kind = "SM_FD_Palm_A" if rng.random() < 0.6 else "SM_FD_Palm_B"
            out[kind].append([round(float(q[0]), 1), round(float(q[1]), 1), round(float(z) * 100 - 10, 1),
                              round(rng.uniform(0, 360), 1), round(rng.uniform(0.85, 1.15), 3)])
    return out


# ---------------------------------------------------------------- 確認用画像
def write_preview(grid, doc, path, scale=2, building_mask=None):
    h = grid.h[::scale, ::scale]
    n = h.shape[0]
    img = np.zeros((n, n, 3), np.uint8)
    land = np.clip(h / 120, 0, 1)
    img[..., 0] = (60 + 120 * land).astype(np.uint8) * (h > 0)
    img[..., 1] = (70 + 100 * land).astype(np.uint8) * (h > 0)
    img[..., 2] = np.where(h > 0, 60, 120).astype(np.uint8)

    def plot(items, color, r=0):
        if not items:
            return
        a = np.array([it[:2] for it in items], float)   # 枕木などは pitch の有無で長さが違う
        c, w = grid.ue_to_px(a[:, 0], a[:, 1])
        c, w = (c / scale).astype(int), (w / scale).astype(int)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ok = (w + dy >= 0) & (c + dx >= 0) & (w + dy < n) & (c + dx < n)
                img[w[ok] + dy, c[ok] + dx] = color

    flower_colors = {"Nanohana": (250, 220, 30), "Renge": (220, 110, 200), "Hydrangea": (110, 130, 240),
                     "Sunflower": (255, 160, 0), "Higanbana": (230, 20, 20), "Cosmos": (170, 60, 255),
                     "Suisen": (255, 255, 255), "Sakura": (255, 190, 220)}
    for k, items in doc["instances"].items():
        if (k.startswith("SM_FD_Guardrail") or k.startswith("SM_FD_Road") or k.startswith("SM_FD_Flower") or "Sakura" in k
                or k.startswith("SM_FD_Shrine") or k.startswith("SM_FD_Rail")
                or k.split("_")[2] in ("Momiji", "Haze", "Yamazakura", "Keyaki")):
            continue
        plot(items, (40, 200, 60) if "Pine" not in k else (20, 120, 40))
    autumn_colors = {"Momiji": (230, 30, 30), "Haze": (255, 90, 20), "Yamazakura": (255, 170, 40), "Keyaki": (190, 170, 60)}
    for k, items in doc["instances"].items():  # 落葉樹 (秋の色)
        if k.endswith("_Autumn") and k.split("_")[2] in autumn_colors:
            plot(items, autumn_colors[k.split("_")[2]])
    for k, items in doc["instances"].items():  # 花と桜 (季節がちがうものも重ねて描く)
        kind = k.replace("SM_FD_Flower_", "").replace("SM_FD_", "").split("_")[0]
        if kind in flower_colors and not k.endswith(("_Leaf", "_Bare")):
            plot(items, flower_colors[kind], r=1 if kind == "Sakura" else 0)
    if building_mask is not None:  # 建物 (と周り 2m)
        bm = building_mask[::scale, ::scale][:n, :n]
        img[bm] = (235, 120, 40)
    inst = doc["instances"]
    plot(inst.get("SM_FD_GuardrailPost"), (255, 255, 255))
    plot((inst.get("SM_FD_RoadPole") or []) + (inst.get("SM_FD_RoadPoleT") or []), (60, 60, 255), r=1)
    plot([i for k, v in inst.items() if k.startswith("SM_FD_RoadSign") for i in v], (255, 0, 255), r=2)
    plot([i for v in doc.get("lights", {}).values() for i in v], (255, 220, 0), r=1)
    plot([i for k, v in inst.items() if k.startswith("SM_FD_RailSleeper") for i in v], (40, 30, 30))
    plot(inst.get("SM_FD_RailCrossingSignal"), (255, 255, 0), r=2)
    plot([i for k, v in inst.items() if k.startswith("SM_FD_Shrine") for i in v], (230, 30, 30), r=2)
    if doc.get("meoto"):
        m = doc["meoto"]
        plot([r["location_cm"] for r in m["rocks"]] + [m["torii"]["location_cm"]], (255, 40, 40), r=3)
    Image.fromarray(img).save(path)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    course_overrides(sys.argv[1], {"build_scenery": sys.modules[__name__], "flowers": flowers, "buildings": buildings,
                                   "road_furniture": road_furniture})
    grid = Grid(area, np.load(os.path.join(area.out_dir, "height_road_m.npy")))
    with open(os.path.join(area.out_dir, "roads.json"), encoding="utf-8") as f:
        roads = json.load(f)["roads"]
    landmarks_path = os.path.join(area.out_dir, "landmarks.json")
    landmarks = []
    if os.path.exists(landmarks_path):
        with open(landmarks_path, encoding="utf-8") as f:
            landmarks = json.load(f)["landmarks"]
    out = os.path.join(area.out_dir, "scenery")
    os.makedirs(out, exist_ok=True)

    # コースの設定の "features" で、糸島の名所 (夫婦岩・鳥居・ヤシ並木) と道路の付属物を切れる
    features = course_features(sys.argv[1])
    meshes = {}
    meoto, torii_cm, keep_clear = None, None, []
    res = place_meoto(grid, landmarks) if features["landmarks"] else None
    if res:
        meoto, m = res
        meshes.update(m)
        torii_cm = meoto["torii"]["location_cm"]
        keep_clear.append((torii_cm[0], torii_cm[1], TREE_CLEAR_TORII_M * 100))
    # 線路と駅 (タイルの中の線路、踏切、駅のホーム)
    rail_doc = railways.load(area) if features["railways"] else None
    tracks = railways.tracks_in_tile(rail_doc, grid.half_cm) if rail_doc else []
    rail_plans, rail_clear = [], []
    if tracks:
        railways.mark_crossings(tracks, grid, roads, stamp_roads)
        rail_plans = railways.plan_stations(rail_doc, tracks, grid, roads, stamp_roads)
        rail_clear = railways.rail_roads(tracks) + [
            {"points_cm": (p["path"] * 100).tolist(), "width_cm": p["width"] * 100 + 100, "priority": 99,
             "bridge": False, "tunnel": False, "highway": "railway"} for pl in rail_plans for p in pl["platforms"]]
    elif features["railways"]:
        print("線路: タイルの中に地上の線路はありません" if rail_doc else "線路: railways.json がありません (apply_roads.py を実行し直してください)")
    shrine_plans = []
    if features["shrines"]:  # 神社の参道と建物の所は、木・花・家をよける
        shrine_plans, shrine_clear = shrines.plan(area, grid, roads, stamp_roads)
        keep_clear += shrine_clear
    # meisho/ の名所 (金印公園など)。周りの木・花・家はよける
    spots = meisho.find(area, grid, roads) if features["meisho"] else []
    keep_clear += meisho.keep_clear(spots)
    # plants/ の植物 (Codex などが足す)。コースの地方 (九州・四国…) の植物だけ
    course = course_of_area(sys.argv[1])
    region = plants.region_of(area.center_lat, area.center_lon, course.cfg if course else None)
    extra, extra_leaves, extra_barks, _ = plants.load(region=region)
    print(f"植物の地方: {plants.REGIONS.get(region, region)} (plants/ から {len(extra)} 種類の形)")
    instances = place_trees(grid, roads, keep_clear, extra)
    for name, items in shrines.forest(grid, roads, shrine_plans, keep_clear, stamp_roads).items():  # 鎮守の森
        instances.setdefault(name, []).extend(items)
    if features["landmarks"]:
        instances.update(place_palms(grid, roads, torii_cm))
    flower_items, seasons, cull, occupied = flowers.place_flowers(grid, roads, densify, stamp_roads, dilate, keep_clear)
    removed = flowers.remove_near(instances, occupied, list(TREE_KINDS) + list(extra))
    deciduous, moved = flowers.place_deciduous(
        instances, grid, ["SM_FD_Broadleaf_A", "SM_FD_Broadleaf_B", "SM_FD_Broadleaf_C", "SM_FD_Broadleaf_D"])
    instances.update(deciduous)
    instances.update(flower_items)
    removed_by_rails = 0
    if rail_clear:  # 線路とホームの上 (と 1.5m) の木と花
        removed_by_rails = buildings.remove_in_mask(instances, stamp_roads(grid, rail_clear, 1.0, 1.5), 1.0,
                                                    grid.half_cm / 100, list(instances))
    footprints = buildings.load_footprints(area)
    station_buildings = railways.station_footprints(rail_plans, footprints, rail_doc, tracks) if rail_plans else 0
    building_meshes, building_mask, building_stats = buildings.place_buildings(grid, roads + rail_clear, stamp_roads,
                                                                               footprints, keep_clear)
    removed_by_buildings = buildings.remove_in_mask(instances, building_mask, grid.mpp, grid.half_cm / 100, list(instances))
    world, rail_m, stretch_extra, shrine_stats = {}, 0.0, [], {}
    if shrine_plans:  # 神社の部品は家の周りの除外より後に足す (近くの家に消されないように)
        shrine_items, sando, shrine_stats = shrines.place(shrine_plans, grid, roads)
        instances.update(shrine_items)
        meshes.update({k: v for k, v in shrines.meshes().items() if k in shrine_items})
        stretch_extra = [k for k in shrines.STRETCH if k in shrine_items]
        if sando.parts:
            world[sando.name] = sando
    world.update(meisho.build(spots))
    rail_lights, rail_stats = {}, {}
    if tracks:
        rail_items, rail_world, rail_lights, rail_stats = railways.place(tracks, rail_plans, grid, roads, out)
        instances.update(rail_items)
        meshes.update(railways.meshes(rail_items))
        world.update(rail_world)
        cull.update({k: v for k, v in railways.CULL_CM.items() if k in rail_items})
    meshes.update(flowers.flower_meshes())
    deciduous_meshes, deciduous_seasons = flowers.deciduous_meshes()
    meshes.update(deciduous_meshes)
    seasons.update(deciduous_seasons)
    if features["guardrails"]:
        posts, beams, rail_m = place_guardrails(grid, roads, torii_cm)
        instances["SM_FD_GuardrailPost"] = posts
        meshes["SM_FD_GuardrailPost"] = sm.guardrail_post()
        if beams.parts:
            world[beams.name] = beams
    for name, make in TREE_KINDS.items():
        meshes[name] = make()
    for name, spec in extra.items():
        if "place_with" in spec:   # 季節ちがいの形: 相手と同じ位置・向きに置き、季節で出し入れする
            instances[name] = list(instances.get(spec["place_with"]) or [])
    for name, spec in extra.items():
        if instances.get(name):
            meshes[name] = spec["make"]()
            if spec.get("seasons", plants.ALL_SEASONS) != plants.ALL_SEASONS:
                seasons[name] = spec["seasons"]
    if features["road_markings"] or features["utility_poles"]:
        road_items, road_meshes, stretch, road_world, lights = place_road_furniture(
            grid, roads, torii_cm, markings=features["road_markings"], poles=features["utility_poles"])
    else:
        road_items, road_meshes, stretch, road_world, lights = {}, {}, [], {}, {}
    instances.update(road_items)
    meshes.update(road_meshes)
    stretch = stretch + stretch_extra
    world.update(road_world)
    world.update(building_meshes)
    for kind, items in rail_lights.items():   # ホームの灯り
        lights.setdefault(kind, []).extend(items)
    meshes.update(world)
    # 置く物が 1 つも無い形 (海ばかりのタイルの建物の区画など) は書かない
    empty = [n for n, m in meshes.items() if not m.parts and not m.cards]
    for n in empty:
        meshes.pop(n)
        world.pop(n, None)
        instances.pop(n, None)

    files = {}
    for name, mesh in meshes.items():
        fname = f"{name}.gltf"
        tris = sm.write_gltf(mesh, os.path.join(out, fname))
        lo, hi = mesh.bounds()
        files[name] = fname
        print(f"  {fname}: 三角形 {tris}、大きさ {hi[0] - lo[0]:.1f} x {hi[1] - lo[1]:.1f} x {hi[2] - lo[2]:.1f} m")
    textures = {}
    for kind, spec in fo.LEAF_KINDS.items():  # 葉の絵 (葉の板のマテリアルが使う)
        fo.leaf_texture(kind, os.path.join(out, spec["texture"]))
        textures[kind] = spec["texture"]
    for kind, fname in flowers.FLOWER_TEXTURES.items():  # 花の絵 (葉と同じマテリアルで貼る)
        flowers.flower_texture(kind, os.path.join(out, fname))
        textures[kind] = fname
    for kind, fname in flowers.AUTUMN_TEXTURES.items():  # 落葉樹の葉の絵 (季節の色)
        flowers.autumn_leaf_texture(kind, os.path.join(out, fname))
        textures[kind] = fname
    for kind, (fname, draw) in extra_leaves.items():  # plants/ の葉と花の絵
        draw(os.path.join(out, fname))
        textures[kind] = fname
    # 建物の壁と屋根の模様と凹凸 ({名前: [色の絵, 凹凸の絵, 大きさ m]})
    building_tex = building_textures.write_all(out) if building_meshes else {}
    bark_textures = {}
    for kind in bark.BARK_KINDS:  # 樹皮の絵と凹凸 (幹と枝のマテリアルが使う)
        color, normal = bark.texture_names(kind)
        bark.bark_textures(kind, os.path.join(out, color), os.path.join(out, normal))
        bark_textures[kind] = [color, normal]
    for kind, (color, normal, draw) in extra_barks.items():  # plants/ の樹皮の絵
        draw(os.path.join(out, color), os.path.join(out, normal))
        bark_textures[kind] = [color, normal]
    doc = {
        "area": area.name, "units": "cm", "axes": "UE: +X 東, +Y 南, +Z 上",
        "instance_format": "[x, y, z, yaw (度), 拡大率 (, pitch (度))]。stretch_x のメッシュは X だけ拡大する",
        "stretch_x": stretch,
        # 原点に1つだけ置く、道路に沿ってつながった形 (ガードレールのビーム・区画線・側溝)。shadow は影を落とすか
        "world_meshes": {name: {"shadow": name in ("SM_FD_GuardrailBeams", "SM_FD_Railway", "SM_FD_RailStations")
                                           or name.startswith(("SM_FD_Buildings", meisho.MESH_PREFIX))}
                         for name in world},
        # 細い電線の影は地面に濃い線になって目立つので落とさない
        "no_shadow": [n for n in stretch],
        "meshes": files, "leaf_textures": textures, "bark_textures": bark_textures, "meoto": meoto, "instances": instances,
        # 建物の壁と屋根の絵 ({名前: [色, 凹凸, 1 枚が覆う大きさ m]})。マテリアルがワールド座標で貼る
        "building_textures": building_tex,
        # 夜に点く光源 (防犯灯)。[x, y, z, yaw, pitch] は光の出る所と光の向き (pitch -90 が真下)
        "lights": lights,
        # 咲く季節 (ビット: 1 春, 2 夏, 4 秋, 8 冬)。C++ の AFDInstances が Y キーの季節で出し入れする。ないものはいつも見える
        "seasons": seasons,
        # 見える距離 (cm)。小さな花の株は遠くでは消す
        "cull_cm": cull,
    }
    with open(os.path.join(out, "scenery.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    write_preview(grid, doc, os.path.join(out, "preview.png"), building_mask=building_mask)
    counts = ", ".join(f"{k.replace('SM_FD_', '')} {len(v)}" for k, v in instances.items())
    print(f"配置: {counts}")
    print(f"花と桜の場所と重なる木 {removed} 本を除きました。広葉樹 {moved} 本を落葉樹 (モミジ・ハゼノキ・ヤマザクラ・ケヤキ) にしました")
    print("建物: " + ", ".join(f"{k} {v}" for k, v in building_stats.items())
          + f"。建物と重なる木や花 {removed_by_buildings} を除きました")
    with open(os.path.join(area.out_dir, "building_looks.json"), "w", encoding="utf-8") as f:
        json.dump(buildings.placed_looks, f, ensure_ascii=False, indent=1)
    print(f"ガードレール 計 {rail_m / 1000:.2f} km")
    if features["shrines"]:
        print("神社: " + (", ".join(f"{k} {v}" for k, v in shrine_stats.items()) or "なし"))
    if features["railways"]:
        print("線路と駅: " + (", ".join(f"{k} {v}" for k, v in rail_stats.items()) or "なし")
              + f"。駅舎 {station_buildings}、線路の上の木や花 {removed_by_rails} を除きました")
    if spots:
        print("名所: " + "、".join(mod.NAME_JA for _, mod, _ in spots))
    print("夜の光源: " + ", ".join(f"{k} {len(v)}" for k, v in lights.items()))


if __name__ == "__main__":
    main()
