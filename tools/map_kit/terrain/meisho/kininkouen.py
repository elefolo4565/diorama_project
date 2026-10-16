"""金印公園 (志賀島の南西の海ぎわ、県道 542 号ぞい)。見た目の基準は notes/kininkouen.md。

並べ方 (道路の座標: s は道路の中心から山の方への奥行き、u は道路に沿った位置。m)
- 道路ぎわの前庭 (道路と同じ高さの石畳) に「漢委奴国王金印発光之処」の碑: 自然石の台に、細長い花崗岩の角柱
- 前庭の奥は石積みの土留め。その切れ目から山の斜面を上る石段 (両側に手すり)
- 石段を上りきった所が丸い広場 (OSM の点)。中央に金印の形の石 (台の上の四角い石)、山側に説明板と石積み、
  海側の半周に手すり
- 前庭と広場の地面は terraces が平らにする (apply_roads.py が地形に焼く)。石段は地面に合わせて上る
"""

import math

import numpy as np

import scenery_meshes as sm

NAME_JA = "金印公園"
LATLON = (33.66039, 130.30113)

FORECOURT_S = (4.2, 9.0)        # 前庭の奥行き (道路の中心から)
FORECOURT_U = (-7.5, 6.0)       # 前庭の幅 (道路に沿って)
MONUMENT_SU = (6.2, -3.6)       # 碑の位置
STAIR_U = 2.6                   # 石段の中心の位置 (道路に沿って)
STAIR_W = 2.8                   # 石段の幅
TREAD = 0.32                    # 段の奥行き
MAX_RISE = 0.22                 # 1 段で上がる高さの上限 (公園の急な石段)
PLAZA_R = 5.5                   # 広場の半径
PLAZA_DZ = -1.0                 # 広場の高さ: OSM の点の地面からの差 (石段を上りやすくする)
MIN_PLAZA_S = 20.0              # 広場の中心の奥行きの最小 (OSM の点が道路に近すぎるとき)
RAIL_H = 1.1                    # 手すりの高さ

CLEAR = [(6.5, -1.0, 8.0), (12.0, STAIR_U, 3.0), (17.0, STAIR_U, 3.0), (22.0, STAIR_U, 3.0), (27.0, 0.0, 9.0)]

MATERIALS = {
    "FD_MeishoGranite": dict(color=(0.42, 0.41, 0.38), roughness=0.7),       # 碑と金印の石 (明るい灰色の花崗岩)
    "FD_MeishoInscription": dict(color=(0.07, 0.07, 0.07), roughness=0.6),   # 彫った文字の帯 (遠目には暗い帯)
    "FD_MeishoRock": dict(color=(0.15, 0.135, 0.115), roughness=0.9),        # 台の自然石・石積み
    "FD_MeishoStep": dict(color=(0.32, 0.31, 0.29), roughness=0.85),         # 石段
    "FD_MeishoPaving": dict(color=(0.27, 0.26, 0.24), roughness=0.85),       # 前庭と広場の石畳
    "FD_MeishoPavingLight": dict(color=(0.46, 0.43, 0.38), roughness=0.85),  # 広場の内側の明るい円
    "FD_MeishoRail": dict(color=(0.58, 0.59, 0.59), roughness=0.35),         # 手すり (亜鉛めっきの鋼)
    "FD_MeishoPanel": dict(color=(0.78, 0.78, 0.76), roughness=0.5),         # 説明板
    "FD_MeishoPanelBand": dict(color=(0.06, 0.13, 0.32), roughness=0.5),     # 説明板の上の紺の帯
}


def plaza_s(ctx):
    return max(ctx.road["dist"] if ctx.road else 25.0, MIN_PLAZA_S)


def terraces(ctx):
    """地形を平らにする所: 前庭は道路の高さ、広場は OSM の点の地面の高さ + PLAZA_DZ。"""
    return [
        dict(kind="rect", s=FORECOURT_S, u=FORECOURT_U, z="road", dz=0.12, feather=2.5),
        dict(kind="circle", s=plaza_s(ctx), u=0.0, r=PLAZA_R + 0.6, z="ground", dz=PLAZA_DZ, feather=3.0),
    ]


def build(ctx):
    m = sm.Mesh("SM_FD_Meisho_Kininkouen", flat=True)
    yaw = ctx.yaw_deg
    road_z = ctx.road["z"] if ctx.road else ctx.z

    def at(s, u, z):
        x, y = ctx.frame(s, u)
        return (x, y, z)

    def ground_at(s, u):
        return ctx.ground(*ctx.frame(s, u))

    def ground_range(s0, s1, u0, u1):
        ss, uu = np.meshgrid(np.linspace(s0, s1, 5), np.linspace(u0, u1, 5))
        g = ctx.ground(*ctx.frame(ss, uu))
        return float(np.min(g)), float(np.max(g))

    def slab(mat, s0, s1, u0, u1, top, bottom=None):
        """道路の座標の四角 (s0..s1, u0..u1) を、bottom (無ければ地面より下) から top までの塊にする。"""
        if bottom is None:
            bottom = ground_range(s0, s1, u0, u1)[0] - 0.6
        h = max(top - bottom, 0.05)
        m.add(mat, *sm.box(at((s0 + s1) / 2, (u0 + u1) / 2, (top + bottom) / 2), (s1 - s0, u1 - u0, h), yaw))

    # ---- 前庭と碑
    zf = max(ground_range(*FORECOURT_S, *FORECOURT_U)[0], road_z) + 0.05
    slab("FD_MeishoPaving", *FORECOURT_S, *FORECOURT_U, zf)
    # 奥の土留め (石積み)。石段の所は開ける
    s_back = FORECOURT_S[1]
    for u0, u1 in ((FORECOURT_U[0], STAIR_U - STAIR_W / 2 - 0.3), (STAIR_U + STAIR_W / 2 + 0.3, FORECOURT_U[1])):
        top = max(ground_range(s_back, s_back + 1.5, u0, u1)[1] + 0.3, zf + 0.6)
        slab("FD_MeishoRock", s_back - 0.25, s_back + 0.5, u0, u1, top, zf - 0.5)
    ms, mu = MONUMENT_SU
    rng = sm.Rng(7351)
    m.add("FD_MeishoRock", *sm.blob(at(ms, mu, zf + 0.55), (1.35, 1.05, 0.85), rng, subdiv=2, roughness=0.18))
    base = zf + 1.15
    pillar_h = 4.6
    m.add("FD_MeishoGranite", *sm.box(at(ms, mu, base + pillar_h / 2), (0.78, 0.78, pillar_h), yaw))
    # 頭は浅い四角すい
    tip = np.array(at(ms, mu, base + pillar_h + 0.22))
    sq = [np.array(at(ms + a, mu + b, base + pillar_h)) for a, b in ((-0.39, -0.39), (0.39, -0.39), (0.39, 0.39), (-0.39, 0.39))]
    m.add("FD_MeishoGranite", np.array(sq + [tip]), np.array([(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]))
    # 道路の方の面に彫った文字の帯
    m.add("FD_MeishoInscription", *sm.box(at(ms - 0.40, mu, base + pillar_h * 0.52), (0.03, 0.30, pillar_h * 0.82), yaw))
    for ds, du, r in ((0.6, 1.9, 0.55), (-0.2, -1.8, 0.45), (1.4, -0.9, 0.4), (0.9, 2.8, 0.35)):
        m.add("FD_MeishoRock", *sm.blob(at(ms + ds, mu + du, zf + r * 0.35), (r * 1.3, r, r * 0.8), rng, 1, 0.2))

    # ---- 広場の高さ (terraces で平らにした地面)。石段は前庭からそこまで上る
    sp = plaza_s(ctx)
    zp = ground_at(sp, 0.0) + 0.05
    s_end = sp - math.sqrt(max(PLAZA_R ** 2 - STAIR_U ** 2, 1.0)) + 0.3
    u0, u1 = STAIR_U - STAIR_W / 2, STAIR_U + STAIR_W / 2
    s0 = s_back - 0.25
    z, s = zf, s0
    steps = []
    while s < s_end or z < zp - 0.02:
        line = zf + (zp - zf) * min((s + TREAD - s0) / max(s_end - s0, 1.0), 1.0)
        want = max(line, ground_range(s, s + TREAD, u0, u1)[1] + 0.12)
        z = min(max(z, min(want, zp)), z + MAX_RISE)
        slab("FD_MeishoStep", s, s + TREAD, u0, u1, z)
        steps.append((s + TREAD / 2, z))
        s += TREAD
        if s > s_end + 3.0:
            break
    # 手すり (両側。柱は 1.8m おき) と、段の脇の低い石の縁
    for side in (-1, 1):
        u = STAIR_U + side * (STAIR_W / 2 - 0.12)
        path = np.array([at(ps, u, pz + 0.9) for ps, pz in steps])
        m.add("FD_MeishoRail", *sm.swept_rect(path, 0.05, 0.05))
        last = -99.0
        for ps, pz in steps:
            if ps - last >= 1.8:
                m.add("FD_MeishoRail", *sm.box(at(ps, u, pz + 0.45), (0.05, 0.05, 0.9), yaw))
                last = ps
        for ps, pz in steps[::3]:
            slab("FD_MeishoRock", ps - 0.5, ps + 0.5, u + side * 0.12, u + side * 0.42, pz + 0.12)

    # ---- 丸い広場
    ang = np.linspace(0, 2 * math.pi, 40, endpoint=False)

    def disc(radius, top, bottom, mat):
        ring_top = [at(sp + radius * math.cos(a), radius * math.sin(a), top) for a in ang]
        ring_bot = [at(sp + radius * math.cos(a), radius * math.sin(a), bottom) for a in ang]
        m.add(mat, *sm.sweep([ring_bot, ring_top]))

    disc(PLAZA_R + 0.3, zp - 0.02, zp - 0.9, "FD_MeishoRock")      # 縁石
    disc(PLAZA_R, zp, zp - 0.4, "FD_MeishoPaving")
    disc(3.2, zp + 0.015, zp - 0.2, "FD_MeishoPavingLight")
    disc(3.0, zp + 0.02, zp - 0.2, "FD_MeishoPaving")
    # 山側の石積み (平らにした所の縁の斜面を受ける)
    back = np.radians(np.arange(-80, 81, 8.0))
    rr = PLAZA_R + 0.45
    for h_top, mat in ((1.4, "FD_MeishoRock"),):
        inner = [at(sp + rr * math.cos(a), rr * math.sin(a), zp - 0.4) for a in back]
        upper = [at(sp + rr * math.cos(a), rr * math.sin(a), zp + h_top) for a in back]
        outer_up = [at(sp + (rr + 0.6) * math.cos(a), (rr + 0.6) * math.sin(a), zp + h_top) for a in back]
        outer_lo = [at(sp + (rr + 0.6) * math.cos(a), (rr + 0.6) * math.sin(a), zp - 0.4) for a in back]
        rings = np.stack([inner, upper, outer_up, outer_lo], 1)    # 弧に沿って断面 (4 点) を流す
        m.add(mat, *sm.sweep(rings))
    # 中央の金印の形の石 (暗い台の上に四角い石、上に小さな印面)
    m.add("FD_MeishoInscription", *sm.box(at(sp, 0, zp + 0.2), (1.7, 1.7, 0.4), yaw))
    m.add("FD_MeishoGranite", *sm.box(at(sp, 0, zp + 0.68), (1.15, 1.15, 0.56), yaw))
    m.add("FD_MeishoInscription", *sm.box(at(sp, 0, zp + 0.97), (0.42, 0.42, 0.03), yaw))
    # 説明板 (山側の内側の円の縁。広場の中心の方を向く。角度 0 が山側 (+s)、180 が海側)
    for a_deg in (-55, -22, 22, 55):
        a = math.radians(a_deg)
        ps, pu = sp + 3.4 * math.cos(a), 3.4 * math.sin(a)
        face_yaw = yaw + a_deg + 90.0
        m.add("FD_MeishoPanel", *sm.box(at(ps, pu, zp + 0.95), (0.95, 0.07, 1.6), face_yaw))
        m.add("FD_MeishoPanelBand", *sm.box(at(ps, pu, zp + 1.66), (0.97, 0.08, 0.18), face_yaw))
        m.add("FD_MeishoRail", *sm.box(at(ps, pu, zp + 0.08), (1.0, 0.25, 0.16), face_yaw))
    # 海側の半周の手すり (石段の入口はあける)
    stair_a = math.atan2(STAIR_U, -(sp - s_end))
    arc = [a for a in np.radians(np.arange(95, 266, 6.0))
           if abs((a - stair_a + math.pi) % (2 * math.pi) - math.pi) > math.radians(16)]
    runs, cur = [], []
    for a in arc:
        if cur and a - cur[-1] > math.radians(7):
            runs.append(cur)
            cur = []
        cur.append(a)
    if cur:
        runs.append(cur)
    rr = PLAZA_R - 0.2
    for run in runs:
        for h in (RAIL_H, RAIL_H * 0.55):
            path = np.array([at(sp + rr * math.cos(a), rr * math.sin(a), zp + h) for a in run])
            if len(path) >= 2:
                m.add("FD_MeishoRail", *sm.swept_rect(path, 0.05, 0.05))
        for a in run[::2]:
            m.add("FD_MeishoRail", *sm.box(at(sp + rr * math.cos(a), rr * math.sin(a), zp + RAIL_H / 2),
                                           (0.06, 0.06, RAIL_H), yaw))
    return m
