"""海岸からの距離で「砂浜にしてよい所」の絵を作る。build_terrain.py (一周コースは境目のそろえ直し) の後に実行する。

ランドスケープのマテリアルは低い所 (標高 2.2m 未満) を砂浜の色にするが、そのままだと海から遠い低い田んぼや
埋立地まで砂浜になる。この絵が 0 の所 (海から COAST_FAR_M 以上離れた所) は、低くても草地のままにする。

使い方:
    python build_coast.py areas/itoshima/itoshima_1_m2.json

出力 (out/<エリア名>/):
    coast_mask.png  1024 x 1024 (RGB、3 色とも同じ値)。255 = 砂浜にしてよい (海岸から COAST_NEAR_M 以内と海)、
                    0 = 砂浜にしない。上が北、範囲はランドスケープと同じ
"""

import os
import sys

import numpy as np
from PIL import Image

from geo import Area

COAST_NEAR_M = 100.0   # 海からこの距離までは砂浜にしてよい
COAST_FAR_M = 160.0    # この距離より遠い所は砂浜にしない (間はなめらかに変える)
CELL_M = 4.0           # 距離を数える升目の大きさ
OUT_PX = 1024


def sea_with_margin(area):
    """タイルの外側も含めた海の印と、タイルの範囲 (行, 列の slice)。外側は標高が海面より低い所を海とみなす。"""
    out = area.out_dir
    sea = np.load(os.path.join(out, "sea_mask.npy")).astype(bool)
    path = os.path.join(out, "height_margin_m.npy")
    if not os.path.exists(path):
        n = sea.shape[0]
        return sea, (slice(0, n), slice(0, n))
    big = np.load(path) < -0.05
    m = (big.shape[0] - sea.shape[0]) // 2
    crop = (slice(m, m + sea.shape[0]), slice(m, m + sea.shape[1]))
    big[crop] = sea
    return big, crop


def pool_any(mask, k):
    """k x k ごとに、1 つでも True なら True (端の余りは切り捨てずに含める)。"""
    h = -(-mask.shape[0] // k) * k
    w = -(-mask.shape[1] // k) * k
    padded = np.zeros((h, w), dtype=bool)
    padded[:mask.shape[0], :mask.shape[1]] = mask
    return padded.reshape(h // k, k, w // k, k).any(axis=(1, 3))


def distance_cells(sea, steps):
    """海からの距離 (升目の数、8 近傍で 1 歩ずつ広げる)。steps 歩で届かない所は steps + 1。"""
    dist = np.full(sea.shape, steps + 1, dtype=np.int32)
    reached = sea.copy()
    dist[reached] = 0
    for s in range(1, steps + 1):
        grown = reached.copy()
        grown[1:, :] |= reached[:-1, :]
        grown[:-1, :] |= reached[1:, :]
        grown[:, 1:] |= reached[:, :-1]
        grown[:, :-1] |= reached[:, 1:]
        grown[1:, 1:] |= reached[:-1, :-1]
        grown[:-1, :-1] |= reached[1:, 1:]
        grown[1:, :-1] |= reached[:-1, 1:]
        grown[:-1, 1:] |= reached[1:, :-1]
        dist[grown & ~reached] = s
        reached = grown
    return dist


def build(area):
    sea, crop = sea_with_margin(area)
    k = max(1, int(round(CELL_M / area.meters_per_px)))
    cells = pool_any(sea, k)
    cell_m = k * area.meters_per_px
    dist_m = distance_cells(cells, int(np.ceil(COAST_FAR_M / cell_m))).astype(np.float32) * cell_m
    allow = np.clip((COAST_FAR_M - dist_m) / (COAST_FAR_M - COAST_NEAR_M), 0.0, 1.0)
    # 升目の値をタイルの範囲に戻す (1 画素 = 元の 1 画素に引き伸ばしてから切り取る)
    full = np.repeat(np.repeat(allow, k, axis=0), k, axis=1)[:sea.shape[0], :sea.shape[1]]
    tile = full[crop]
    img = Image.fromarray(np.round(tile * 255).astype(np.uint8)).resize((OUT_PX, OUT_PX), Image.BILINEAR)
    # RGB で書く (グレースケールの PNG は UE でグレースケールの絵になり、マテリアルの色のサンプラーと合わない)
    img = img.convert("RGB")
    path = os.path.join(area.out_dir, "coast_mask.png")
    img.save(path)
    land = ~sea[crop]
    inland = np.count_nonzero(land & (tile < 0.5)) / max(1, np.count_nonzero(land))
    print(f"海岸の絵: {path} (陸のうち砂浜にしない所 {inland * 100:.0f}%)")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(Area(sys.argv[1]))


if __name__ == "__main__":
    main()
