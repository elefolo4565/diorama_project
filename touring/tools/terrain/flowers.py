"""季節の花と桜。花の絵 (透過 PNG) を描き、その絵を貼った板で花の株・茂み・桜の木を作り、置き場所を決める。

花は Y キーの季節 (C++ の AFDTimeOfDay の日付) に合わせて、咲く季節だけ見える (AFDInstances の SeasonMask)。
    春 (3/20): 菜の花 (道ばたと畑)、レンゲ (田んぼ)、桜 (花)
    夏 (6/21): アジサイ (道ばた)、ヒマワリ (畑)、桜 (葉)
    秋 (9/23): 彼岸花 (道ばたと田んぼのあぜ)、コスモス (畑)、桜 (色づいた葉)
    冬 (12/21): スイセン (道ばた、海に近い所)、桜 (枝だけ)
森には季節で色の変わる落葉樹 (モミジ・ハゼノキ・ヤマザクラ・ケヤキ) の林を混ぜる (deciduous_*)。

花の株は、絵を貼った縦の板を 2 枚 (十字) 組んだものを 1 か所に何十本も並べた「株のまとまり」(半径 1m ほど)。
板の法線は上向き寄りにそろえる (草と同じく、板の向きで明るさが変わらないように)。
頂点の色 (R) は根元ほど暗い値で、UE の葉のマテリアル (M_FD_Foliage) が花の色に掛ける。
置き場所は実際の花の名所ではなく、道路・地形 (田畑とみなす平地) からの推定。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

import foliage as fo
from bark import bark_tube
from scenery_meshes import Mesh, Rng, bezier

# 季節のビット (C++ の AFDInstances::SeasonBit と同じ)
SPRING, SUMMER, AUTUMN, WINTER = 1, 2, 4, 8

# 花の絵。マテリアル名 = scenery_meshes.MATERIALS の名前。UE では setup_project.py が M_FD_Foliage のインスタンスにする
FLOWER_TEXTURES = {
    "FD_Flower_Nanohana": "T_FD_Flower_Nanohana.png",
    "FD_Flower_Renge": "T_FD_Flower_Renge.png",
    "FD_Flower_Hydrangea": "T_FD_Flower_Hydrangea.png",
    "FD_Flower_Sunflower": "T_FD_Flower_Sunflower.png",
    "FD_Flower_Higanbana": "T_FD_Flower_Higanbana.png",
    "FD_Flower_Cosmos": "T_FD_Flower_Cosmos.png",
    "FD_Flower_Suisen": "T_FD_Flower_Suisen.png",
    "FD_Flower_Sakura": "T_FD_Flower_Sakura.png",
}
SAKURA_LEAF = "FD_Leaf_Kusu"   # 葉の季節の桜は、クスノキの明るい緑の葉の絵を使う

SEED = 20261014

# 道ばたの花: 路肩の外 (舗装の端から OFFSET_M) に、帯 (STRIP_M くらいの長さ) になって咲く
ROADSIDE_STEP_M = 2.0
ROADSIDE_OFFSET_M = (0.9, 2.6)
ROADSIDE_MAX_SLOPE_DEG = 32.0
ROADSIDE_Z_M = (2.5, 120.0)
# 畑・田んぼ: 標高 FIELD_Z_M、傾き FIELD_MAX_SLOPE_DEG 未満の平地を FIELD_CELL_M 四方の区画に分け、道路の近くの区画に作る
FIELD_CELL_M = 36.0
FIELD_INSET_M = 1.6           # あぜの幅 (区画の端はあける)
FIELD_Z_M = (2.5, 30.0)
FIELD_MAX_SLOPE_DEG = 4.0
FIELD_NEAR_ROAD_M = 160.0
FIELD_FLAT_SHARE = 0.85       # 区画の中でこれ以上が平地なら畑にできる
# 桜並木: 田畑の近くの道路の両側に、まとまった区間だけ
SAKURA_SPACING_M = 9.0
SAKURA_OFFSET_M = 3.2
SAKURA_THRESHOLD = 1.0       # 道路に沿ったノイズ (-1.8..1.8) がこれより高い区間を並木にする (大きいほど短い)
# 見える距離 (cm)。小さな株は遠くでは点にもならないので消す。畑は遠くから色の帯に見えるので遠くまで
CULL_ROADSIDE_CM = 45000.0
CULL_FIELD_CM = 150000.0

# 花の株の種類: (板の絵, 株のまとまりの半径 m, 本数, 1 本の高さ m, 高さのばらつき)
PATCHES = {
    "SM_FD_Flower_Nanohana": ("FD_Flower_Nanohana", 1.1, 22, 0.95, 0.25),
    "SM_FD_Flower_Renge": ("FD_Flower_Renge", 1.25, 40, 0.24, 0.3),
    "SM_FD_Flower_Sunflower": ("FD_Flower_Sunflower", 0.9, 7, 1.75, 0.15),
    "SM_FD_Flower_Higanbana": ("FD_Flower_Higanbana", 0.7, 14, 0.5, 0.25),
    "SM_FD_Flower_Cosmos": ("FD_Flower_Cosmos", 1.1, 22, 1.15, 0.25),
    "SM_FD_Flower_Suisen": ("FD_Flower_Suisen", 0.45, 9, 0.4, 0.2),
}


# ---------------------------------------------------------------- 花の絵
def _col(r, rgb, amount=12):
    return fo._jitter(rgb, r, amount)


def _leaf(draw, P, base, ang, length, width, col, n=10):
    draw.polygon([P(q) for q in fo._leaf_polygon(base, ang, length, width, n)], fill=col)


def _stem(draw, P, pts, col, width):
    draw.line([P(p) for p in pts], fill=col, width=max(1, int(width)), joint="curve")


def _curve(x0, y0, x1, y1, bend, n=8):
    """(x0, y0) から (x1, y1) へ、横に bend だけふくらんだ線。"""
    out = []
    for t in np.linspace(0, 1, n):
        out.append((x0 + (x1 - x0) * t + bend * math.sin(math.pi * t), y0 + (y1 - y0) * t))
    return out


def _petals(draw, P, c, radius, count, col, width=0.5, phase=0.0, center=None, center_r=0.3):
    """c を中心に花びらを count 枚。center は花の芯の色。"""
    for k in range(count):
        a = phase + 2 * math.pi * k / count
        _leaf(draw, P, c, a, radius, width, col, n=6)
    if center:
        cr = radius * center_r
        draw.ellipse([P((c[0] - cr, c[1] - cr)), P((c[0] + cr, c[1] + cr))], fill=center)


def _nanohana(draw, r, s, P):
    stem_col, leaf_cols = (72, 112, 40), ((58, 98, 36), (74, 116, 44), (88, 128, 50))
    for _ in range(r.randrange(5, 8)):
        x0 = s * r.uniform(0.25, 0.75)
        x1, y1 = x0 + s * r.uniform(-0.15, 0.15), s * r.uniform(0.08, 0.32)
        _stem(draw, P, _curve(x0, s, x1, y1, s * r.uniform(-0.05, 0.05)), stem_col, s * 0.012)
        for _ in range(r.randrange(3, 6)):  # 下の方の葉
            t = r.uniform(0.0, 0.45)
            base = (x0 + (x1 - x0) * t, s - (s - y1) * t)
            side = r.choice((1, -1))
            _leaf(draw, P, base, -math.pi / 2 + side * r.uniform(0.5, 1.2), s * r.uniform(0.1, 0.2), 0.38,
                  _col(r, r.choice(leaf_cols)))
        # 茎の先の花の房 (小さな黄色い花がまるく集まり、てっぺんはつぼみ)
        cx, cy = x1, y1 + s * 0.07
        for _ in range(55):
            a, q = r.uniform(0, 2 * math.pi), math.sqrt(r.random())
            x, y = cx + math.cos(a) * q * s * 0.06, cy + math.sin(a) * q * s * 0.085
            fr = s * r.uniform(0.009, 0.014)
            col = _col(r, (250, 214, 30) if y > y1 + s * 0.015 else (190, 200, 60), 14)
            draw.ellipse([P((x - fr, y - fr)), P((x + fr, y + fr))], fill=col)


def _renge(draw, r, s, P):
    leaf = ((48, 92, 34), (62, 108, 40))
    for _ in range(90):  # 足もとの小さな丸い葉
        x, y = s * r.uniform(0.02, 0.98), s * r.uniform(0.45, 1.0)
        e = s * r.uniform(0.012, 0.022)
        draw.ellipse([P((x - e, y - e * 0.7)), P((x + e, y + e * 0.7))], fill=_col(r, r.choice(leaf)))
    for _ in range(r.randrange(12, 17)):
        x0 = s * r.uniform(0.06, 0.94)
        y1 = s * r.uniform(0.15, 0.55)
        x1 = x0 + s * r.uniform(-0.05, 0.05)
        _stem(draw, P, _curve(x0, s, x1, y1, s * 0.02), (80, 118, 50), s * 0.008)
        col = _col(r, r.choice(((206, 92, 176), (222, 120, 190), (188, 76, 160))), 10)
        for k in range(9):  # 輪のように並んだ小さな花
            a = 2 * math.pi * k / 9
            x, y = x1 + math.cos(a) * s * 0.03, y1 + math.sin(a) * s * 0.022
            e = s * 0.016
            draw.ellipse([P((x - e, y - e)), P((x + e, y + e))], fill=col)
        e = s * 0.015
        draw.ellipse([P((x1 - e, y1 - e)), P((x1 + e, y1 + e))], fill=(236, 200, 226))


def _sunflower(draw, r, s, P):
    x0, top = s * 0.5, s * r.uniform(0.18, 0.24)
    x1 = x0 + s * r.uniform(-0.05, 0.05)
    _stem(draw, P, _curve(x0, s, x1, top + s * 0.08, s * 0.02), (80, 116, 44), s * 0.026)
    for k in range(6):  # 大きなハート形の葉
        t = 0.15 + 0.12 * k
        base = (x0 + (x1 - x0) * t, s - (s - top) * t)
        side = 1 if k % 2 else -1
        _leaf(draw, P, base, -math.pi / 2 + side * r.uniform(0.9, 1.4), s * r.uniform(0.16, 0.22) * (1.1 - t * 0.5), 0.75,
              _col(r, (56, 94, 34)))
    R = s * r.uniform(0.12, 0.15)
    c = (x1, top)
    for k in range(26):  # 舌状花 (黄色い花びら)
        a = 2 * math.pi * k / 26 + r.uniform(-0.05, 0.05)
        _leaf(draw, P, (c[0] + math.cos(a) * R * 0.4, c[1] + math.sin(a) * R * 0.4), a, R * 0.62, 0.32,
              _col(r, (248, 196, 18), 12), n=6)
    d = R * 0.48
    draw.ellipse([P((c[0] - d, c[1] - d)), P((c[0] + d, c[1] + d))], fill=(78, 48, 18))
    for _ in range(60):  # 種のつぶつぶ
        a, q = r.uniform(0, 2 * math.pi), math.sqrt(r.random()) * d * 0.9
        e = s * 0.004
        x, y = c[0] + math.cos(a) * q, c[1] + math.sin(a) * q
        draw.ellipse([P((x - e, y - e)), P((x + e, y + e))], fill=_col(r, (50, 30, 12), 8))


def _higanbana(draw, r, s, P):
    for _ in range(r.randrange(4, 7)):
        x0 = s * r.uniform(0.2, 0.8)
        x1, y1 = x0 + s * r.uniform(-0.06, 0.06), s * r.uniform(0.22, 0.45)
        _stem(draw, P, _curve(x0, s, x1, y1, s * 0.01, n=4), (82, 124, 52), s * 0.012)  # 葉のない茎
        R = s * r.uniform(0.09, 0.12)
        for k in range(r.randrange(5, 8)):  # 反り返った細い花びらと、長く上へ曲がるしべ
            a = -math.pi / 2 + (k / 6 - 0.5) * math.pi * 1.6 + r.uniform(-0.15, 0.15)
            col = _col(r, (204, 22, 26), 14)
            tip = (x1 + math.cos(a) * R * 0.6, y1 + math.sin(a) * R * 0.45)
            draw.line([P((x1, y1)), P(tip), P((tip[0] + math.cos(a) * R * 0.15, tip[1] + R * 0.12))], fill=col,
                      width=max(2, int(s * 0.011)))
            for _ in range(2):
                b = a + r.uniform(-0.3, 0.3)
                end = (x1 + math.cos(b) * R * 1.15, y1 + math.sin(b) * R * 1.0 - R * 0.25)
                mid = ((x1 + end[0]) / 2, (y1 + end[1]) / 2 + R * 0.15)
                draw.line([P((x1, y1)), P(mid), P(end)], fill=(214, 40, 40), width=max(1, int(s * 0.004)))


def _cosmos(draw, r, s, P):
    stems = []
    for _ in range(r.randrange(4, 6)):
        x0 = s * r.uniform(0.3, 0.7)
        x1, y1 = s * r.uniform(0.1, 0.9), s * r.uniform(0.06, 0.4)
        pts = _curve(x0, s, x1, y1, s * r.uniform(-0.06, 0.06))
        _stem(draw, P, pts, (86, 126, 50), s * 0.006)
        stems.append(pts)
        for _ in range(16):  # 細かく裂けた葉 (短い線)
            p = pts[r.randrange(1, len(pts) - 2)]
            a = -math.pi / 2 + r.uniform(-1.4, 1.4)
            q = (p[0] + math.cos(a) * s * 0.045, p[1] + math.sin(a) * s * 0.045)
            draw.line([P(p), P(q)], fill=_col(r, (70, 116, 42)), width=max(1, int(s * 0.003)))
    for pts in stems:
        c = pts[-1]
        col = _col(r, r.choice(((242, 150, 192), (226, 76, 150), (246, 236, 240), (236, 120, 176))), 8)
        _petals(draw, P, c, s * r.uniform(0.04, 0.05), 8, col, width=0.55, phase=r.uniform(0, 1),
                center=(232, 188, 40), center_r=0.28)


def _suisen(draw, r, s, P):
    for _ in range(r.randrange(7, 10)):  # 白っぽい緑の細長い葉
        x0 = s * r.uniform(0.35, 0.65)
        a = -math.pi / 2 + r.uniform(-0.45, 0.45)
        _leaf(draw, P, (x0, s), a, s * r.uniform(0.45, 0.75), 0.09, _col(r, (92, 132, 96)), n=8)
    for _ in range(r.randrange(2, 4)):
        x0 = s * r.uniform(0.4, 0.6)
        x1, y1 = x0 + s * r.uniform(-0.15, 0.15), s * r.uniform(0.15, 0.3)
        _stem(draw, P, _curve(x0, s, x1, y1, s * 0.02), (96, 136, 92), s * 0.012)
        for _ in range(r.randrange(3, 6)):  # 横向きに咲く白い花と黄色の副花冠
            c = (x1 + s * r.uniform(-0.07, 0.07), y1 + s * r.uniform(-0.03, 0.05))
            _petals(draw, P, c, s * 0.04, 6, _col(r, (246, 244, 232), 6), width=0.6, phase=r.uniform(0, 1),
                    center=(240, 186, 40), center_r=0.36)


def _hydrangea(draw, r, s, P):
    """アジサイの茂みの葉の板: 大きな卵形の葉と、まるい花の房 (青・紫・桃色)。"""
    twigs = fo._twigs(r, s, s * 0.5, 6, spread=0.4)
    for tw in twigs:
        draw.line([P(p) for p in tw], fill=(70, 86, 40), width=max(2, s // 150))
    for (p, a) in fo._points_along(twigs, r, 26):
        ang = a + r.choice((1, -1)) * r.uniform(0.5, 1.3)
        base = (p[0] + math.cos(ang) * 3, p[1] + math.sin(ang) * 3)
        _leaf(draw, P, base, ang, s * r.uniform(0.13, 0.18), 0.6, _col(r, r.choice(((46, 86, 32), (60, 100, 38)))))
    palette = r.choice((((92, 120, 214), (120, 150, 230)), ((132, 104, 206), (160, 134, 226)), ((214, 126, 178), (232, 160, 200))))
    for tw in twigs[1:3] + [twigs[0]]:
        cx, cy = tw[-1]
        R = s * r.uniform(0.13, 0.17)
        for _ in range(170):
            a, q = r.uniform(0, 2 * math.pi), math.sqrt(r.random())
            x, y = cx + math.cos(a) * q * R, cy + math.sin(a) * q * R
            k = 0.78 + 0.3 * (1 - (y - cy + R) / (2 * R))   # 房の上ほど明るい
            col = tuple(int(min(255, c * k)) for c in _col(r, r.choice(palette), 10))
            _petals(draw, P, (x, y), s * 0.018, 4, col, width=0.9, phase=r.uniform(0, 1))


def _sakura(draw, r, s, P):
    """ソメイヨシノの花の付いた小枝 (葉が出る前で、枝が透けて見える)。"""
    twigs = fo._twigs(r, s, s * 0.5, 9, spread=0.45)
    for tw in twigs:
        draw.line([P(p) for p in tw], fill=(64, 42, 38), width=max(2, s // 110))
    for (p, _) in fo._points_along(twigs, r, 140):
        for _ in range(r.randrange(2, 5)):  # 数輪ずつかたまって咲く
            c = (p[0] + r.uniform(-1, 1) * s * 0.03, p[1] + r.uniform(-1, 1) * s * 0.03)
            col = _col(r, r.choice(((252, 224, 232), (248, 206, 220), (255, 238, 242))), 6)
            _petals(draw, P, c, s * r.uniform(0.016, 0.022), 5, col, width=0.85, phase=r.uniform(0, 1.3),
                    center=(214, 104, 132), center_r=0.25)


PAINTERS = {
    "FD_Flower_Nanohana": _nanohana, "FD_Flower_Renge": _renge, "FD_Flower_Hydrangea": _hydrangea,
    "FD_Flower_Sunflower": _sunflower, "FD_Flower_Higanbana": _higanbana, "FD_Flower_Cosmos": _cosmos,
    "FD_Flower_Suisen": _suisen, "FD_Flower_Sakura": _sakura,
}


def flower_texture(kind, path, size=fo.TEXTURE_SIZE, seed=11):
    """花の種類 kind の絵 (2x2 に 4 種類の株、透過 PNG) を path に書く。株は各マスの下の辺の中央が根元。"""
    r = random.Random(f"{kind}{seed}")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy = i * cell, j * cell
            PAINTERS[kind](draw, r, cell, lambda p, ox=ox, oy=oy: (ox + p[0], oy + p[1]))
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


# ---------------------------------------------------------------- 花の株・茂み・桜の形
def plant_patch(name, material, seed, radius, count, height, spread):
    """半径 radius の中に count 本の株。1 本は絵を貼った縦の板 2 枚の十字 (表裏の面)。"""
    rng = Rng(seed)
    verts, normals, uvs, shade = [], [], [], []
    for i in range(count):
        a, q = rng.uniform(0, 2 * math.pi), math.sqrt(rng.uniform(0, 1)) * radius
        base = np.array([math.cos(a) * q, math.sin(a) * q, -0.04])
        h = height * rng.uniform(1 - spread, 1 + spread)
        yaw = rng.uniform(0, math.pi)
        tilt = rng.normal(size=2) * 0.08
        up = np.array([tilt[0], tilt[1], 1.0])
        up /= np.linalg.norm(up)
        ci, cj = rng.integers(0, fo.CELLS), rng.integers(0, fo.CELLS)
        u0, u1 = ci / fo.CELLS, (ci + 1) / fo.CELLS
        v0, v1 = cj / fo.CELLS, (cj + 1) / fo.CELLS
        if rng.random() < 0.5:
            u0, u1 = u1, u0
        for k in range(2):
            ang = yaw + k * math.pi / 2
            side = np.array([math.cos(ang), math.sin(ang), 0.0]) * h * 0.5
            face = np.cross(side, up)
            face /= np.linalg.norm(face)
            n = face * 0.3 + [0, 0, 1.0]
            n /= np.linalg.norm(n)
            for c, t, lit in ((base - side, (u0, v1), 0.35), (base + side, (u1, v1), 0.35),
                              (base + side + up * h, (u1, v0), 1.0), (base - side + up * h, (u0, v0), 1.0)):
                verts.append(c)
                normals.append(n)
                uvs.append(t)
                shade.append(lit)
    v = np.array(verts)
    q = np.arange(len(v) // 4)[:, None] * 4
    front = np.concatenate([q + [0, 1, 2], q + [0, 2, 3]])
    m = Mesh(name)
    m.add_cards(material, v, np.concatenate([front, front[:, ::-1]]), np.array(normals), np.array(uvs), np.array(shade))
    return m


def hydrangea(name, seed):
    """アジサイの茂み (高さ 1.2m、幅 1.6m)。根元から葉が地面まで茂り、上の方に花の房が付く。
    葉と花の房の板を、地面に接する低いこんもりした形に重ねる (板の下の方は透明なので、中心を低くして地面まで埋める)。"""
    rng = Rng(seed)
    m = Mesh(name)
    fol = fo.Foliage("FD_Flower_Hydrangea", rng, (0, 0, 0.4), (0.85, 0.85, 0.55))
    for _ in range(4):   # 上の方 (花の房が見える)
        c = (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0.45, 0.65))
        fo.clump(fol, c, rng.uniform(0.42, 0.55), 14, size=0.55, flat=0.8)
    for k in range(7):   # 根元のまわり (地面まで葉で埋める)
        a = 2 * math.pi * k / 7 + rng.uniform(-0.3, 0.3)
        c = (math.cos(a) * 0.5, math.sin(a) * 0.5, rng.uniform(0.12, 0.22))
        fo.clump(fol, c, rng.uniform(0.3, 0.38), 8, size=0.45, flat=0.6, up_bias=0.2)
    return fol.write(m)


def sakura(seed, height=7.5):
    """ソメイヨシノ。低い所で太い枝が斜め上へ広がり、横に広い傘の形の樹冠。
    {季節: Mesh} を返す。どれも同じ枝の形で、春は花、夏は葉、秋は色づいた葉、冬は枝だけ。"""
    rng = Rng(seed)
    wood = Mesh("wood")
    trunk_h = height * 0.28
    lean = rng.normal(size=2) * 0.05 * height
    fork = np.array([lean[0], lean[1], trunk_h])
    r0 = 0.045 * height
    bark_tube(wood, "FD_Bark", bezier((0, 0, -0.3), (lean[0] * 0.3, lean[1] * 0.3, trunk_h * 0.5), fork, 6),
              np.linspace(r0 * 1.4, r0, 6), n=14)
    crown_r, crown_h = height * 0.62, height * 0.3
    cz = height - crown_h
    cards = []  # (中心, 半径, 枚数, 板の大きさ)
    k = int(rng.integers(5, 7))
    for j in range(k):
        az = 2 * math.pi * j / k + rng.uniform(-0.3, 0.3)
        reach = crown_r * rng.uniform(0.55, 0.8)
        tip = np.array([lean[0] + math.cos(az) * reach, lean[1] + math.sin(az) * reach, cz + rng.uniform(-0.3, 0.6)])
        mid = fork + (tip - fork) * 0.5 + [0, 0, 0.6]
        path = bezier(fork - [0, 0, 0.3], mid, tip, 7)
        bark_tube(wood, "FD_Bark", path, np.linspace(r0 * 0.7, 0.05, 7), n=8)
        # 枝先から細い枝が分かれ、その先に花 (葉) のかたまり
        for _ in range(int(rng.integers(6, 9))):
            d = rng.normal(size=3)
            d[2] = abs(d[2]) * 0.5 + 0.2
            d /= np.linalg.norm(d)
            base = path[int(rng.integers(3, 7))]
            end = base + d * rng.uniform(1.0, 2.0)
            bark_tube(wood, "FD_Bark", np.array([base, (base + end) / 2 + [0, 0, 0.15], end]), [0.05, 0.03, 0.015], n=5)
            cards.append((end, rng.uniform(0.7, 1.0), 9, 1.1))
        cards.append((tip, 1.2, 12, 1.2))
    out = {}
    for season, material in ((SPRING, "FD_Flower_Sakura"), (SUMMER, SAKURA_LEAF), (AUTUMN, "FD_Leaf_AutumnOrange"),
                             (WINTER, None)):
        m = Mesh("sakura")
        m.parts = list(wood.parts)
        m.cards = list(wood.cards)
        if material:
            fol = fo.Foliage(material, Rng(seed + 1), (lean[0], lean[1], cz), (crown_r, crown_r, crown_h))
            for c, rad, n, size in cards:
                fo.clump(fol, c, rad, n, size=size, flat=0.7)
            fol.write(m)
        out[season] = m
    return out


# ---------------------------------------------------------------- 置き場所
def smooth_1d(rng, s_m, wavelength):
    """道路に沿った距離 s_m (m) でなめらかに変わる -1..1 の値 (花の帯の切れ目を作る)。"""
    v = np.zeros_like(s_m)
    for _ in range(4):
        v += np.sin(s_m * 2 * math.pi / (wavelength * rng.uniform(0.6, 1.6)) + rng.uniform(0, 2 * math.pi))
    return v / 2.2


def field_noise(seed, x_m, y_m):
    """畑の作物のまとまりを作る、なめらかに変わる値 (だいたい -1..1、波長 300-700m)。"""
    r = random.Random(seed)
    v = 0.0
    for _ in range(5):
        a = r.uniform(0, 2 * math.pi)
        k = 2 * math.pi / r.uniform(300.0, 700.0)
        v += math.sin((x_m * math.cos(a) + y_m * math.sin(a)) * k + r.uniform(0, 2 * math.pi))
    return v / 2.2


def _slope_deg(grid, x_cm, y_cm):
    d = 100.0 * grid.mpp
    gx = (grid.height_m(x_cm + d, y_cm) - grid.height_m(x_cm - d, y_cm)) / (2 * grid.mpp)
    gy = (grid.height_m(x_cm, y_cm + d) - grid.height_m(x_cm, y_cm - d)) / (2 * grid.mpp)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def roadside_points(grid, roads, densify, road_clear, keep_clear_cm):
    """すべての道路の両側の路肩の外の点。(x, y, 道路に沿った距離 m, 道路の向き (度), 道路の番号) の配列。"""
    rng = Rng(SEED)
    rows = []
    for ri, r in enumerate(roads):
        if r["tunnel"] or r["bridge"] or len(r["points_cm"]) < 2:
            continue
        pts = densify(r["points_cm"], ROADSIDE_STEP_M)
        d = np.gradient(pts[:, :2], axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
        right = np.stack([-d[:, 1], d[:, 0]], 1)
        s_m = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1))] / 100
        half = r["width_cm"] / 200
        heading = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
        for side in (1, -1):
            off = (half + rng.uniform(*ROADSIDE_OFFSET_M, size=len(pts))) * 100
            q = pts[:, :2] + right * side * off[:, None] + d * rng.uniform(-60, 60, size=len(pts))[:, None]
            rows.append(np.c_[q, s_m + side * 50000.0 + ri * 1000.0, heading, np.full(len(pts), ri)])
    if not rows:   # 海ばかりのタイルなど、陸の道路が 1 本も無い
        return np.zeros((0, 5))
    a = np.concatenate(rows)
    z = grid.height_m(a[:, 0], a[:, 1])
    c, w = grid.ue_to_px(a[:, 0], a[:, 1])
    ok = ~np.isnan(z) & (z >= ROADSIDE_Z_M[0]) & (z <= ROADSIDE_Z_M[1])
    ci = np.clip(c.astype(int), 0, road_clear.shape[1] - 1)
    wi = np.clip(w.astype(int), 0, road_clear.shape[0] - 1)
    ok &= ~road_clear[wi, ci]
    ok &= _slope_deg(grid, a[:, 0], a[:, 1]) < ROADSIDE_MAX_SLOPE_DEG
    for cx, cy, rad in keep_clear_cm:
        ok &= np.hypot(a[:, 0] - cx, a[:, 1] - cy) >= rad
    return a[ok]


def _item(rng, x, y, z, scale=(0.8, 1.2)):
    return [round(float(x), 1), round(float(y), 1), round(float(z) - 5, 1), round(rng.uniform(0, 360), 1),
            round(rng.uniform(*scale), 3)]


def place_flowers(grid, roads, densify, stamp_roads, dilate, keep_clear_cm):
    """花と桜の置き場所。({メッシュ名: [[x, y, z, yaw, 拡大率]]}, {メッシュ名: 季節のビット}, {メッシュ名: 見える距離 cm},
    [(x, y, 半径 cm)] 木を置かない所 (畑と桜)) を返す。"""
    rng = Rng(SEED + 1)
    out = {name: [] for name in list(PATCHES) + ["SM_FD_Flower_Hydrangea"] + [f"SM_FD_Sakura_{v}_{s}" for v in "AB"
                                                                               for s in ("Bloom", "Leaf", "Autumn", "Bare")]}
    road_clear = stamp_roads(grid, roads, 1.0, 0.6)
    pts = roadside_points(grid, roads, densify, road_clear, keep_clear_cm)
    near_sea = dilate(grid.h[::8, ::8] <= 0.0, 12)   # 海から約 100m
    cell = 8
    pr = np.clip(((pts[:, 1] + grid.half_cm) / 100 / cell).astype(int), 0, near_sea.shape[0] - 1)
    pc = np.clip(((pts[:, 0] + grid.half_cm) / 100 / cell).astype(int), 0, near_sea.shape[1] - 1)
    by_sea = near_sea[pr, pc]

    # 平地 (田畑) の印 (8m 格子)
    h8 = grid.h[::cell, ::cell]
    gy, gx = np.gradient(h8, cell * grid.mpp)
    flat8 = (np.degrees(np.arctan(np.hypot(gx, gy))) < FIELD_MAX_SLOPE_DEG) & (h8 >= FIELD_Z_M[0]) & (h8 <= FIELD_Z_M[1])
    farmish = dilate(flat8, 3)
    by_farm = farmish[pr, pc]

    # 道ばたの花 (季節ごとに別の帯)
    def strips(seed, wavelength, share, mask=None):
        v = smooth_1d(Rng(seed), pts[:, 2], wavelength)
        keep = v > np.quantile(v, 1 - share) if len(v) else v > 0
        return keep if mask is None else keep & mask

    zs = grid.height_m(pts[:, 0], pts[:, 1]) * 100
    for i in np.nonzero(strips(SEED + 11, 80.0, 0.35))[0]:          # 菜の花: 海沿いにも田畑にも広く
        out["SM_FD_Flower_Nanohana"].append(_item(rng, pts[i, 0], pts[i, 1], zs[i]))
    for i in np.nonzero(strips(SEED + 12, 120.0, 0.14))[0]:     # アジサイ: 植えた列 (2m おき)
        out["SM_FD_Flower_Hydrangea"].append(_item(rng, pts[i, 0], pts[i, 1], zs[i], (0.8, 1.15)))
    for i in np.nonzero(strips(SEED + 13, 60.0, 0.5, by_farm))[0]:   # 彼岸花: 田畑のまわりの道ばた
        out["SM_FD_Flower_Higanbana"].append(_item(rng, pts[i, 0], pts[i, 1], zs[i]))
        if rng.random() < 0.6:  # 帯を太く
            out["SM_FD_Flower_Higanbana"].append(_item(rng, pts[i, 0] + rng.uniform(-90, 90), pts[i, 1] + rng.uniform(-90, 90), zs[i]))
    for i in np.nonzero(strips(SEED + 14, 70.0, 0.12, ~by_farm))[0]:  # コスモス: 道ばたにも少し
        out["SM_FD_Flower_Cosmos"].append(_item(rng, pts[i, 0], pts[i, 1], zs[i]))
    for i in np.nonzero(strips(SEED + 15, 50.0, 0.55, by_sea))[0]:   # スイセン: 海に近い道ばた
        out["SM_FD_Flower_Suisen"].append(_item(rng, pts[i, 0], pts[i, 1], zs[i]))

    # 畑・田んぼ: 区画ごとに季節の作物 (春は菜の花かレンゲ、夏はヒマワリ、秋はコスモス、ほかは何も咲かない)
    occupied = []
    major = [r for r in roads if r["priority"] <= 3]
    near_road = dilate(stamp_roads(grid, major, cell, 0.0), int(FIELD_NEAR_ROAD_M / cell))
    field_clear = stamp_roads(grid, roads, 1.0, 1.5)
    size_m = (grid.n - 1) * grid.mpp
    k8 = int(FIELD_CELL_M / cell)
    for y0 in np.arange(0, size_m - FIELD_CELL_M, FIELD_CELL_M):
        for x0 in np.arange(0, size_m - FIELD_CELL_M, FIELD_CELL_M):
            r8, c8 = int(y0 / cell), int(x0 / cell)
            if flat8[r8:r8 + k8, c8:c8 + k8].mean() < FIELD_FLAT_SHARE or not near_road[r8:r8 + k8, c8:c8 + k8].any():
                continue
            # 作物の畑は、まとまった所 (なめらかなノイズの高い所) に寄せ、その中でも区画ごとにまばらにする
            crops = []
            if field_noise(SEED + 31, x0, y0) > 0.45 and rng.random() < 0.55:
                crops.append(("SM_FD_Flower_Nanohana", 2.2) if rng.random() < 0.55 else ("SM_FD_Flower_Renge", 2.3))
            if field_noise(SEED + 32, x0, y0) > 0.75 and rng.random() < 0.5:
                crops.append(("SM_FD_Flower_Sunflower", 1.9))
            elif field_noise(SEED + 33, x0, y0) > 0.6 and rng.random() < 0.5:
                crops.append(("SM_FD_Flower_Cosmos", 2.0))
            edge = rng.random() < 0.3   # あぜの彼岸花
            if not crops and not edge:
                continue
            cx_cm = (x0 + FIELD_CELL_M / 2) * 100 - grid.half_cm
            cy_cm = (y0 + FIELD_CELL_M / 2) * 100 - grid.half_cm
            if any(math.hypot(cx_cm - kx, cy_cm - ky) < rad + FIELD_CELL_M * 70 for kx, ky, rad in keep_clear_cm):
                continue
            if crops:
                occupied.append((cx_cm, cy_cm, FIELD_CELL_M * 50))

            def fill(name, step, xs, ys):
                gx_, gy_ = np.meshgrid(xs, ys)
                gx_ = gx_.ravel() + np.array(rng.uniform(-0.3, 0.3, size=gx_.size)) * step
                gy_ = gy_.ravel() + np.array(rng.uniform(-0.3, 0.3, size=gy_.size)) * step
                x_cm, y_cm = gx_ * 100 - grid.half_cm, gy_ * 100 - grid.half_cm
                z = grid.height_m(x_cm, y_cm)
                ci = np.clip(gx_.astype(int), 0, field_clear.shape[1] - 1)
                wi = np.clip(gy_.astype(int), 0, field_clear.shape[0] - 1)
                good = ~np.isnan(z) & ~field_clear[wi, ci] & (z >= FIELD_Z_M[0])
                for x, y, zz in zip(x_cm[good], y_cm[good], z[good]):
                    out[name].append(_item(rng, x, y, zz * 100, (0.85, 1.15)))

            lo, hi = FIELD_INSET_M, FIELD_CELL_M - FIELD_INSET_M
            for name, step in crops:
                fill(name, step, x0 + np.arange(lo + step / 2, hi, step), y0 + np.arange(lo + step / 2, hi, step))
            if edge:
                along = np.arange(1.0, FIELD_CELL_M, 1.6)
                for xs, ys in ((x0 + along, [y0 + 0.6]), (x0 + along, [y0 + FIELD_CELL_M - 0.6]),
                               ([x0 + 0.6], y0 + along), ([x0 + FIELD_CELL_M - 0.6], y0 + along)):
                    if rng.random() < 0.7:
                        fill("SM_FD_Flower_Higanbana", 1.6, np.asarray(xs), np.asarray(ys))

    # 桜並木: 田畑の近くの道路に、まとまった区間だけ (両側)
    tree_clear = stamp_roads(grid, roads, 1.0, 2.5)
    srng = Rng(SEED + 21)
    for ri, r in enumerate(roads):
        if r["tunnel"] or r["bridge"] or r["priority"] > 3 or len(r["points_cm"]) < 2:
            continue
        p = densify(r["points_cm"], SAKURA_SPACING_M)
        d = np.gradient(p[:, :2], axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
        right = np.stack([-d[:, 1], d[:, 0]], 1)
        s_m = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))] / 100 + ri * 777.0
        v = smooth_1d(Rng(SEED + 22), s_m, 260.0)
        r8 = np.clip(((p[:, 1] + grid.half_cm) / 100 / cell).astype(int), 0, farmish.shape[0] - 1)
        c8 = np.clip(((p[:, 0] + grid.half_cm) / 100 / cell).astype(int), 0, farmish.shape[1] - 1)
        on = (v > SAKURA_THRESHOLD) & farmish[r8, c8]
        half = r["width_cm"] / 200
        for i in np.nonzero(on)[0]:
            for side in (1, -1):
                q = p[i, :2] + right[i] * side * (half + SAKURA_OFFSET_M + srng.uniform(0, 0.8)) * 100
                z = grid.height_m(q[0], q[1])[0]
                c, w = grid.ue_to_px(q[0], q[1])
                if np.isnan(z) or z < 2.5 or tree_clear[int(w), int(c)]:
                    continue
                if any(math.hypot(q[0] - kx, q[1] - ky) < rad for kx, ky, rad in keep_clear_cm):
                    continue
                variant = "A" if srng.random() < 0.5 else "B"
                item = _item(srng, q[0], q[1], z * 100, (0.85, 1.15))
                for s in ("Bloom", "Leaf", "Autumn", "Bare"):
                    out[f"SM_FD_Sakura_{variant}_{s}"].append(item)
                occupied.append((q[0], q[1], 500.0))

    seasons = {"SM_FD_Flower_Nanohana": SPRING, "SM_FD_Flower_Renge": SPRING, "SM_FD_Flower_Hydrangea": SUMMER,
               "SM_FD_Flower_Sunflower": SUMMER, "SM_FD_Flower_Higanbana": AUTUMN, "SM_FD_Flower_Cosmos": AUTUMN,
               "SM_FD_Flower_Suisen": WINTER}
    for v in "AB":
        seasons[f"SM_FD_Sakura_{v}_Bloom"] = SPRING
        seasons[f"SM_FD_Sakura_{v}_Leaf"] = SUMMER
        seasons[f"SM_FD_Sakura_{v}_Autumn"] = AUTUMN
        seasons[f"SM_FD_Sakura_{v}_Bare"] = WINTER
    field_kinds = ("SM_FD_Flower_Renge", "SM_FD_Flower_Sunflower")
    cull = {n: (CULL_FIELD_CM if n in field_kinds or n == "SM_FD_Flower_Nanohana" or n == "SM_FD_Flower_Cosmos"
                else CULL_ROADSIDE_CM) for n in seasons if not n.startswith("SM_FD_Sakura")}
    return out, seasons, cull, occupied


def flower_meshes():
    """{メッシュ名: Mesh}。"""
    meshes = {}
    for i, (name, (material, radius, count, height, spread)) in enumerate(PATCHES.items()):
        meshes[name] = plant_patch(name, material, 300 + i, radius, count, height, spread)
    meshes["SM_FD_Flower_Hydrangea"] = hydrangea("SM_FD_Flower_Hydrangea", 320)
    for v, seed, h in (("A", 330, 7.5), ("B", 331, 8.5)):
        tree = sakura(seed, h)
        for season, label in ((SPRING, "Bloom"), (SUMMER, "Leaf"), (AUTUMN, "Autumn"), (WINTER, "Bare")):
            name = f"SM_FD_Sakura_{v}_{label}"
            tree[season].name = name
            meshes[name] = tree[season]
    return meshes


def remove_near(instances, occupied, names):
    """occupied [(x, y, 半径 cm)] の中にある木 (names) を取り除く (畑の中や桜と重ならないように)。"""
    if not occupied:
        return 0
    occ = np.array(occupied)
    removed = 0
    for name in names:
        items = instances.get(name)
        if not items:
            continue
        a = np.array([it[:2] for it in items], float)
        keep = np.ones(len(a), bool)
        # 格子で近いものだけ比べる
        cell = 4000.0
        buckets = {}
        for j, (x, y, r) in enumerate(occ):
            buckets.setdefault((int(x // cell), int(y // cell)), []).append(j)
        for i, (x, y) in enumerate(a[:, :2]):
            bx, by = int(x // cell), int(y // cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in buckets.get((bx + dx, by + dy), ()):
                        if abs(x - occ[j, 0]) < occ[j, 2] and abs(y - occ[j, 1]) < occ[j, 2]:
                            keep[i] = False
        removed += int((~keep).sum())
        instances[name] = [it for it, k in zip(items, keep) if k]
    return removed


# ---------------------------------------------------------------- 森の落葉樹 (季節で葉の色が変わる)
# 常緑の森 (シイ・タブ・クス) に混ぜて、季節の色どりにする。秋 (Y キーの 9/23) に紅葉させる
# (実際の糸島の紅葉は 11 月下旬ごろだが、Y キーの秋はこの 1 つなので、秋はいつも紅葉した姿にする)
AUTUMN_LEAVES = {
    # 葉の絵: (葉の形, 色 (sRGB))。マテリアル名 = scenery_meshes.MATERIALS の名前
    "FD_Leaf_MapleGreen": ("maple", ((88, 132, 44), (106, 150, 52), (124, 162, 60), (74, 116, 38))),
    # 秋の色は少し落ち着かせ、同じ木の中にも色の段階 (黄 -> 橙 -> 赤) を混ぜて、隣の木となじむようにする
    "FD_Leaf_MapleRed": ("maple", ((176, 44, 30), (196, 70, 34), (156, 38, 34), (204, 116, 42))),
    "FD_Leaf_HazeRed": ("narrow", ((184, 56, 30), (204, 88, 34), (164, 42, 38), (206, 132, 50))),
    "FD_Leaf_AutumnOrange": ("broad", ((206, 130, 40), (214, 162, 56), (186, 98, 38), (150, 132, 46))),
    # 色づき始め (緑が残った黄緑・黄土色)。紅葉の林のまわりで、緑の森との間をつなぐ
    "FD_Leaf_Turning": ("broad", ((120, 132, 46), (160, 146, 52), (184, 140, 50), (96, 118, 42))),
}
AUTUMN_TEXTURES = {k: f"T_{k}.png" for k in AUTUMN_LEAVES}

# 木の種類: (形 (foliage.BROADLEAF_KINDS と同じ書き方), 高さ m, {季節のビット: 葉の絵 (None は枝だけ)})
DECIDUOUS = {
    "Momiji": (dict(trunk=0.3, width=0.62, depth=0.36, subs=(5, 7)), 7.0,
               {SPRING | SUMMER: "FD_Leaf_MapleGreen", AUTUMN: "FD_Leaf_MapleRed", WINTER: None}),
    "Haze": (dict(trunk=0.32, width=0.5, depth=0.36, subs=(4, 6)), 6.5,
             {SPRING | SUMMER: "FD_Leaf_Broad", AUTUMN: "FD_Leaf_HazeRed", WINTER: None}),
    "Yamazakura": (dict(trunk=0.3, width=0.55, depth=0.38, subs=(6, 8)), 10.0,
                   {SPRING: "FD_Flower_Sakura", SUMMER: "FD_Leaf_Broad", AUTUMN: "FD_Leaf_AutumnOrange", WINTER: None}),
    # ケヤキ: 紅葉の林のまわりに。秋は黄土色に色づき始めた姿 (林の赤・橙と、まわりの緑の森の間)
    "Keyaki": (dict(trunk=0.32, width=0.6, depth=0.4, subs=(6, 8)), 11.0,
               {SPRING | SUMMER: "FD_Leaf_Kusu", AUTUMN: "FD_Leaf_Turning", WINTER: None}),
}
SEASON_LABELS = {SPRING: "Spring", SUMMER: "Summer", AUTUMN: "Autumn", WINTER: "Winter", SPRING | SUMMER: "Green"}
# 落葉樹は林 (まとまり) ごとに生える。なめらかなノイズ (だいたい -1.5..1.5) が STAND_CORE より高い所は全部が紅葉する木、
# STAND_EDGE から STAND_CORE の間は、林に近いほど多くケヤキ (色づき始め) にして、緑の森へなだらかにつなぐ
STAND_CORE = 0.8
STAND_EDGE = 0.4
STAND_WAVELENGTH_SCALE = 1.3   # field_noise の波長 (300-700m) をこれで割る -> 林の大きさ 230-540m


def _maple_leaf(c, ang, size, lobes=7):
    """手のひらの形のモミジの葉 (付け根 c、向き ang、大きさ size)。"""
    pts = []
    for k in range(lobes * 2):
        t = k / (lobes * 2 - 1)
        a = ang + (t - 0.5) * math.radians(250)
        tip = k % 2 == 0
        rad = size * (1.0 - 0.35 * abs(t - 0.5) * 2) if tip else size * 0.38
        pts.append((c[0] + math.cos(a) * rad, c[1] + math.sin(a) * rad))
    return [c] + pts


def autumn_leaf_texture(kind, path, size=fo.TEXTURE_SIZE, seed=13):
    """落葉樹の葉の絵 (2x2 の小枝、透過 PNG)。"""
    style, colors = AUTUMN_LEAVES[kind]
    r = random.Random(f"{kind}{seed}")
    big = size * 2
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cell = big // fo.CELLS
    for j in range(fo.CELLS):
        for i in range(fo.CELLS):
            ox, oy = i * cell, j * cell
            s_ = cell

            def P(p, ox=ox, oy=oy):
                return (ox + p[0], oy + p[1])

            twigs = fo._twigs(r, s_, s_ * 0.5, 10, spread=0.46)
            for tw in twigs:
                draw.line([P(p) for p in tw], fill=fo.TWIG_COLOR, width=max(2, s_ // 120))
            count = {"maple": 170, "narrow": 320, "broad": 300}[style]
            for (p, a) in fo._points_along(twigs, r, count):
                ang = a + r.choice((1, -1)) * r.uniform(0.4, 1.4)
                k = 1.12 - 0.3 * (p[1] / s_)   # 上の葉ほど明るい
                col = tuple(int(min(255, c * k)) for c in fo._jitter(r.choice(colors), r))
                if style == "maple":
                    leaf = _maple_leaf(p, ang, r.uniform(22, 32) * s_ / 512)
                    draw.polygon([P(q) for q in leaf], fill=col)
                else:
                    length = r.uniform(*((34, 50) if style == "narrow" else (36, 54))) * s_ / 512
                    base = (p[0] + math.cos(ang) * 3, p[1] + math.sin(ang) * 3)
                    _leaf(draw, P, base, ang, length, 0.28 if style == "narrow" else 0.42, col)
    img = img.resize((size, size), Image.LANCZOS)
    Image.fromarray(fo._bleed(img)).save(path)


def deciduous_meshes():
    """{メッシュ名: Mesh} と {メッシュ名: 季節のビット}。同じ種類の木はどの季節も同じ枝の形 (葉の絵だけが変わる)。"""
    meshes, seasons = {}, {}
    for i, (species, (shape, height, variants)) in enumerate(DECIDUOUS.items()):
        for season, leaf in variants.items():
            key = f"_fd_{species}"
            fo.BROADLEAF_KINDS[key] = dict(shape, leaf=leaf or "FD_Leaf_Broad")
            name = f"SM_FD_{species}_{SEASON_LABELS[season]}"
            m = fo.broadleaf(name, 400 + i, height, key)
            del fo.BROADLEAF_KINDS[key]
            if leaf is None:   # 冬は葉を落とした枝だけ
                m.cards = [c for c in m.cards if not c[0].startswith(("FD_Leaf_", "FD_Flower_"))]
            meshes[name], seasons[name] = m, season
    return meshes, seasons


def place_deciduous(instances, grid, broadleaf_names):
    """森の広葉樹 (broadleaf_names) の一部を落葉樹に置き換える。林ごとにまとまって生えるよう、なめらかなノイズの高い所を選ぶ
    (林の中は全部、林のまわりは色づき始めのケヤキを混ぜて緑の森へつなぐ)。
    置き換えた木は、その種類のどの季節のメッシュにも同じ位置で入れる。{メッシュ名: [...]} を返す。"""
    rng = Rng(SEED + 41)
    out = {f"SM_FD_{sp}_{SEASON_LABELS[se]}": [] for sp, (_, _, v) in DECIDUOUS.items() for se in v}
    moved = 0
    for name in broadleaf_names:
        items = instances.get(name) or []
        keep = []
        for it in items:
            x_m, y_m = it[0] / 100, it[1] / 100
            v = field_noise(SEED + 42, x_m * STAND_WAVELENGTH_SCALE, y_m * STAND_WAVELENGTH_SCALE)
            if v < STAND_EDGE:
                keep.append(it)
                continue
            if v < STAND_CORE:   # 林のまわり: 林に近いほどケヤキが多い
                if rng.random() > (v - STAND_EDGE) / (STAND_CORE - STAND_EDGE):
                    keep.append(it)
                    continue
                for se in DECIDUOUS["Keyaki"][2]:
                    out[f"SM_FD_Keyaki_{SEASON_LABELS[se]}"].append(list(it))
                moved += 1
                continue
            z_m = it[2] / 100
            u = rng.random()
            if z_m > 60:      # 山の上の方はヤマザクラが多い
                species = "Yamazakura" if u < 0.5 else "Momiji" if u < 0.75 else "Haze"
            elif z_m < 25:    # 里に近い低い所はハゼノキが多い
                species = "Haze" if u < 0.5 else "Momiji" if u < 0.8 else "Yamazakura"
            else:
                species = "Momiji" if u < 0.45 else "Haze" if u < 0.75 else "Yamazakura"
            for se in DECIDUOUS[species][2]:
                out[f"SM_FD_{species}_{SEASON_LABELS[se]}"].append(list(it))
            moved += 1
        instances[name] = keep
    return out, moved
