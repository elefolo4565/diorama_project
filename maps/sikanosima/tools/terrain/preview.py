"""地形・道路・目印を1枚の画像にして、エリアの範囲が狙いどおりか確認する。

使い方:
    python preview.py areas/futamigaura.json

出力: out/<エリア名>/preview.png (上が北)
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from geo import Area

PREVIEW_PX = 1600
ROAD_COLORS = {0: (230, 60, 40), 1: (240, 120, 30), 2: (250, 200, 40), 3: (255, 255, 255),
               4: (200, 200, 200), 5: (170, 150, 120)}


def hillshade(h, cell_m):
    gy, gx = np.gradient(h.astype(np.float64), cell_m)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(45)
    shade = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)


def load_font(size):
    for name in ("meiryo.ttc", "msgothic.ttc", "YuGothM.ttc", "NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    area = Area(sys.argv[1])
    out = area.out_dir
    road_h = os.path.join(out, "height_road_m.npy")
    h = np.load(road_h if os.path.exists(road_h) else os.path.join(out, "height_m.npy"))
    sea = np.load(os.path.join(out, "sea_mask.npy"))

    step = max(1, h.shape[0] // PREVIEW_PX)
    hs, ss = h[::step, ::step], sea[::step, ::step]
    shade = hillshade(hs, area.meters_per_px * step)
    land_t = np.clip(hs / max(1.0, float(hs.max())), 0, 1)
    rgb = np.empty(hs.shape + (3,), dtype=np.float64)
    base = np.stack([90 + 120 * land_t, 140 + 60 * land_t, 80 + 60 * land_t], axis=-1)
    rgb[:] = base * (0.45 + 0.55 * shade[..., None])
    depth_t = np.clip(-hs / 30.0, 0, 1)
    sea_rgb = np.stack([60 - 40 * depth_t, 150 - 70 * depth_t, 200 - 40 * depth_t], axis=-1)
    rgb[ss] = sea_rgb[ss]
    img = Image.fromarray(rgb.astype(np.uint8))
    draw = ImageDraw.Draw(img)

    def ue_to_px(x_cm, y_cm):
        # UE (cm): X 東, Y 南 -> ローカル m: x 東, y 北
        col, row = area.local_to_pixel(x_cm / 100.0, -y_cm / 100.0)
        return col / step, row / step

    roads_path = os.path.join(out, "roads.json")
    if os.path.exists(roads_path):
        with open(roads_path, encoding="utf-8") as f:
            roads = json.load(f)["roads"]
        for r in sorted(roads, key=lambda r: -r["priority"]):
            pts = [ue_to_px(p[0], p[1]) for p in r["points_cm"]]
            w = 4 if r["priority"] <= 1 else 3 if r["priority"] == 2 else 1
            draw.line(pts, fill=ROAD_COLORS.get(r["priority"], (255, 255, 255)), width=w)

    font = load_font(18)
    lm_path = os.path.join(out, "landmarks.json")
    if os.path.exists(lm_path):
        with open(lm_path, encoding="utf-8") as f:
            landmarks = json.load(f)["landmarks"]
        for lm in landmarks:
            x, y = ue_to_px(lm["location_cm"][0], lm["location_cm"][1])
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(255, 0, 160), outline=(0, 0, 0))
            draw.text((x + 8, y - 10), lm["name"], fill=(255, 255, 255), font=font,
                      stroke_width=2, stroke_fill=(0, 0, 0))

    # 縮尺バー (1 km) と方位
    km_px = 1000.0 / (area.meters_per_px * step)
    y0 = img.height - 30
    draw.rectangle([20, y0, 20 + km_px, y0 + 8], fill=(255, 255, 255), outline=(0, 0, 0))
    draw.text((20, y0 - 26), "1 km", fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    draw.text((img.width - 40, 10), "N↑", fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    path = os.path.join(out, "preview.png")
    img.save(path)
    print(f"プレビュー: {path}")


if __name__ == "__main__":
    main()
