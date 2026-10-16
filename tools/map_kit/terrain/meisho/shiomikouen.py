"""潮見公園の展望台 (志賀島のいちばん高い所、標高 170m ほど)。見た目の基準は notes/shiomikouen.md。

並べ方 (展望台の点 = OSM の viewpoint を原点に、道路の座標の向き (a: 道路から奥へ、b: 道路に沿って) でそろえる)
- 山頂の広場: 砂利の平らな地面 (terraces で平らにする)。縁に木の柵、外灯 1 本、大きな石の歌碑
- 展望台: コンクリートの塔。4 本の脚 (下の方が薄い水色、上は白)、脚をつなぐ 2 段の梁、真ん中にジグザグに上る
  階段 (水色)、上に四角い展望の床 (脚より外へ張り出す)。床の縁は胸の高さの壁と手すり、長い 2 辺の上に門形の飾り梁
"""

import math

import numpy as np

import scenery_meshes as sm

NAME_JA = "潮見公園展望台"
LATLON = (33.67453, 130.30717)

PLAZA_R = 11.0          # 山頂の広場の半径
LEG_BASE = 2.9          # 脚の付け根 (地面) の位置 (中心から)
LEG_TOP = 2.4           # 脚の上 (床の下) の位置
DECK_Z = 7.6            # 展望の床の下面の高さ (地面から)
DECK = (7.2, 5.6, 0.45)  # 床の大きさ (奥行き, 幅, 厚さ)
PARAPET_H = 1.05
BEAM_Z = (2.6, 5.2)     # 脚をつなぐ梁の高さ
MINT_TOP = 2.8          # 脚の水色の所の高さ

MATERIALS = {
    "FD_MeishoTowerWhite": dict(color=(0.68, 0.68, 0.66), roughness=0.8, surface="Concrete"),    # 塔の白いコンクリート
    "FD_MeishoTowerMint": dict(color=(0.42, 0.63, 0.52), roughness=0.75, surface="Concrete"),    # 脚の下と階段の薄い水色
    "FD_MeishoGravel": dict(color=(0.42, 0.36, 0.27), roughness=0.95),       # 広場の砂利
    "FD_MeishoWood": dict(color=(0.20, 0.13, 0.075), roughness=0.85, surface="WoodGrain"),        # 木の柵
    "FD_MeishoLamp": dict(color=(0.20, 0.20, 0.20), roughness=0.4),          # 外灯の柱
    "FD_MeishoLampGlobe": dict(color=(0.85, 0.85, 0.82), roughness=0.3),     # 外灯の丸い笠
    "FD_MeishoRock": dict(color=(0.15, 0.135, 0.115), roughness=0.9, surface="StoneRough"),        # 歌碑の石 (金印公園と同じ)
    "FD_MeishoRail": dict(color=(0.58, 0.59, 0.59), roughness=0.35),         # 手すり (金印公園と同じ)
}


def spot_s(ctx):
    return ctx.road["dist"] if ctx.road else 0.0


def clear(ctx):
    return [(spot_s(ctx), 0.0, PLAZA_R + 2.0)]


def terraces(ctx):
    return [dict(kind="circle", s=spot_s(ctx), u=0.0, r=PLAZA_R, z="ground", dz=0.0, feather=4.0)]


def build(ctx):
    m = sm.Mesh("SM_FD_Meisho_Shiomikouen", flat=True)
    yaw = ctx.yaw_deg
    s0 = spot_s(ctx)
    z0 = ctx.ground(*ctx.frame(s0, 0.0))

    def at(a, b, z):
        x, y = ctx.frame(s0 + a, b)
        return (x, y, z0 + z)

    def bar(p, q, w, h, mat):
        """2 点を結ぶ角材 (幅 w、高さ h)。真上に立つ柱は箱にする (swept_rect は真上向きの棒を作れない)。"""
        if math.hypot(q[0] - p[0], q[1] - p[1]) < 1e-3:
            m.add(mat, *sm.box(at(p[0], p[1], (p[2] + q[2]) / 2), (w, w, abs(q[2] - p[2])), yaw))
            return
        m.add(mat, *sm.swept_rect(np.array([at(*p), at(*q)]), w, h))

    def block(a, b, z, size, mat, turn=0.0):
        m.add(mat, *sm.box(at(a, b, z), size, yaw + turn))

    # ---- 広場の地面 (砂利の円盤。地形は terraces で平らにしてある)
    ang = np.linspace(0, 2 * math.pi, 48, endpoint=False)
    top = [at(PLAZA_R * math.cos(t), PLAZA_R * math.sin(t), 0.04) for t in ang]
    bot = [at(PLAZA_R * math.cos(t), PLAZA_R * math.sin(t), -0.5) for t in ang]
    m.add("FD_MeishoGravel", *sm.sweep([bot, top]))

    # ---- 展望台の脚 (少し内に傾く)。下の方は水色
    for sa in (-1, 1):
        for sb in (-1, 1):
            p0 = (sa * LEG_BASE, sb * LEG_BASE, -0.3)
            p1 = (sa * LEG_TOP, sb * LEG_TOP, DECK_Z)
            k = (MINT_TOP + 0.3) / (DECK_Z + 0.3)
            pm = tuple(p0[i] + (p1[i] - p0[i]) * k for i in range(3))
            bar(p0, pm, 0.55, 0.55, "FD_MeishoTowerMint")
            bar(pm, p1, 0.55, 0.55, "FD_MeishoTowerWhite")
    # 脚をつなぐ梁 (4 辺 x 2 段)
    for bz in BEAM_Z:
        f = bz / DECK_Z
        c = LEG_BASE + (LEG_TOP - LEG_BASE) * f
        corners = [(c, c), (-c, c), (-c, -c), (c, -c)]
        for i in range(4):
            (a0, b0), (a1, b1) = corners[i], corners[(i + 1) % 4]
            bar((a0, b0, bz), (a1, b1, bz), 0.3, 0.42, "FD_MeishoTowerWhite")

    # ---- 真ん中の階段 (ジグザグ。1 段の流れごとに 90 度向きを変えて上る)
    block(0, 0, DECK_Z / 2 - 0.15, (0.7, 0.7, DECK_Z + 0.3), "FD_MeishoTowerMint")
    flights = 5
    rise = DECK_Z / flights
    for i in range(flights):
        turn = 90.0 * i
        t = math.radians(turn)
        # 柱の周りを回る傾いた板 (長さ 2.6m、幅 1.0m)
        ca, sb = math.cos(t), math.sin(t)
        za, zb = i * rise, (i + 1) * rise
        off = 0.95
        pa = (off * -sb - 1.3 * ca, off * ca - 1.3 * sb, za)
        pb = (off * -sb + 1.3 * ca, off * ca + 1.3 * sb, zb)
        bar(pa, pb, 1.0, 0.22, "FD_MeishoTowerMint")
        # 踊り場
        block(pb[0], pb[1], zb - 0.11, (1.1, 1.1, 0.22), "FD_MeishoTowerMint", turn)
        # 階段の外側の低い壁 (白)
        pa2 = (pa[0] + -sb * 0.5, pa[1] + ca * 0.5, pa[2] + 0.5)
        pb2 = (pb[0] + -sb * 0.5, pb[1] + ca * 0.5, pb[2] + 0.5)
        bar(pa2, pb2, 0.12, 0.9, "FD_MeishoTowerWhite")

    # ---- 展望の床と縁の壁
    da, db, dt = DECK
    block(0, 0, DECK_Z + dt / 2, (da, db, dt), "FD_MeishoTowerWhite")
    # 床の下の張り出しの斜めの面 (脚から床の縁へ)
    for sa in (-1, 1):
        bar((sa * LEG_TOP, 0, DECK_Z - 0.5), (sa * da / 2, 0, DECK_Z), 0.3, 0.3, "FD_MeishoTowerWhite")
    zt = DECK_Z + dt
    for sa in (-1, 1):
        block(sa * (da / 2 - 0.1), 0, zt + PARAPET_H / 2, (0.2, db, PARAPET_H), "FD_MeishoTowerWhite")
    for sb in (-1, 1):
        block(0, sb * (db / 2 - 0.1), zt + PARAPET_H / 2, (da, 0.2, PARAPET_H), "FD_MeishoTowerWhite")
    # 壁の上の金属の手すり
    rz = zt + PARAPET_H + 0.25
    ring = [(da / 2 - 0.1, db / 2 - 0.1), (-da / 2 + 0.1, db / 2 - 0.1), (-da / 2 + 0.1, -db / 2 + 0.1),
            (da / 2 - 0.1, -db / 2 + 0.1)]
    for i in range(4):
        (a0, b0), (a1, b1) = ring[i], ring[(i + 1) % 4]
        bar((a0, b0, rz), (a1, b1, rz), 0.05, 0.05, "FD_MeishoRail")
        n = max(int(math.hypot(a1 - a0, b1 - b0) / 1.2), 1)
        for k in range(n):
            a, b = a0 + (a1 - a0) * k / n, b0 + (b1 - b0) * k / n
            bar((a, b, zt + PARAPET_H), (a, b, rz), 0.04, 0.04, "FD_MeishoRail")
    # 長い 2 辺の上の門形の飾り梁 (端の柱が壁より高く立ち、上を梁が結ぶ)
    for sb in (-1, 1):
        b = sb * (db / 2 - 0.1)
        for sa in (-1, 1):
            bar((sa * (da / 2 - 0.2), b, zt), (sa * (da / 2 - 0.2), b, zt + PARAPET_H + 1.0), 0.3, 0.3, "FD_MeishoTowerWhite")
        bar((-(da / 2 - 0.2), b, zt + PARAPET_H + 1.0), (da / 2 - 0.2, b, zt + PARAPET_H + 1.0), 0.32, 0.36,
            "FD_MeishoTowerWhite")

    # ---- 広場の縁の木の柵 (道路の方はあける)、外灯、歌碑
    fence = [t for t in np.radians(np.arange(0, 360, 7.5)) if abs((t - math.pi + math.pi) % (2 * math.pi) - math.pi) > 0.5]
    runs, cur = [], []
    for t in fence:
        if cur and t - cur[-1] > math.radians(8):
            runs.append(cur)
            cur = []
        cur.append(t)
    if cur:
        runs.append(cur)
    rr = PLAZA_R - 0.4
    for run in runs:
        for h in (0.45, 0.85):
            pts = np.array([at(rr * math.cos(t), rr * math.sin(t), h) for t in run])
            if len(pts) >= 2:
                m.add("FD_MeishoWood", *sm.swept_rect(pts, 0.08, 0.1))
        for t in run[::2]:
            block(rr * math.cos(t), rr * math.sin(t), 0.45, (0.12, 0.12, 1.0), "FD_MeishoWood")
    la, lb = -7.5, -4.0
    m.add("FD_MeishoLamp", *sm.cylinder(at(la, lb, 0.0), at(la, lb, 4.2), 0.07, 0.05, 10))
    m.add("FD_MeishoLampGlobe", *sm.blob(at(la, lb, 4.45), (0.28, 0.28, 0.28), sm.Rng(1), 1, 0.0))
    rng = sm.Rng(4417)
    m.add("FD_MeishoRock", *sm.blob(at(-3.0, 7.0, 0.9), (1.5, 0.75, 1.2), rng, 2, 0.15))
    return m
