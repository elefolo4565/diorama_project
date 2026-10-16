"""志賀海神社 (志賀島の東の山の中腹。海の神 綿津見三神をまつる)。見た目の基準は notes/shikaumijinja.md。

建物の場所と大きさは OSM の輪郭 (拝殿・本殿・鹿角堂など) と道 (石段・参道) に合わせる (© OpenStreetMap contributors, ODbL)。
- 海ぎわの道路から石の鳥居をくぐり、76 段の石段を上る。上は木々の中の石畳の参道 (石灯籠が並ぶ)
- 参道の奥の広い石段を上ると楼門 (2 階建ての門。白木と緑青の銅板の屋根)
- 楼門の先の境内: 拝殿 (白木、緑青の屋根、向拝)、その奥の本殿、西の今宮神社、東の鹿角堂 (白壁と格子、鹿の角を納める)
- 色は白木の古びた茶色と緑青の緑。朱塗りはしない
- 境内と楼門の前は terraces で平らにする。石段は地面に合わせて上る
shrines.py の一般の神社 (朱の鳥居など) はこの神社には置かない (REPLACES_SHRINES)。
"""

import math

import numpy as np

import scenery_meshes as sm
import shrines
from buildings import min_rect

NAME_JA = "志賀海神社"
LATLON = (33.66808, 130.31316)
REPLACES_SHRINES = ("志賀海神社",)

# OSM の輪郭と道 (緯度, 経度)
HAIDEN = [(33.668019, 130.31313), (33.667998, 130.313137), (33.667905, 130.31317), (33.667927, 130.313261),
          (33.668021, 130.313228), (33.668041, 130.313222)]
HONDEN = [(33.668019, 130.31313), (33.668016, 130.313118), (33.668111, 130.313085), (33.668138, 130.313197),
          (33.668043, 130.31323), (33.668041, 130.313222)]
IMAMIYA_HAIDEN = [(33.668074, 130.312829), (33.668029, 130.312843), (33.668021, 130.312846), (33.668036, 130.312913),
                  (33.668098, 130.312893), (33.668084, 130.312826)]
IMAMIYA_HONDEN = [(33.668029, 130.312843), (33.668074, 130.312829), (33.668057, 130.31275), (33.668012, 130.312764)]
KAGURADEN = [(33.668014, 130.312994), (33.667938, 130.313017), (33.667954, 130.313096), (33.66803, 130.313074)]
ROKKAKUDO = [(33.667873, 130.313272), (33.667847, 130.313278), (33.667857, 130.313332), (33.667883, 130.313325)]
STEPS_76 = [(33.66644, 130.31345), (33.666952, 130.313317)]         # 鳥居から上る 76 段
SANDO = [(33.666952, 130.313317), (33.667484, 130.313181)]          # 木々の中の参道
STEPS_ROMON = [(33.667484, 130.313181), (33.667616, 130.313145)]    # 楼門の前の広い石段
ROMON = (33.66765, 130.313136)                                       # 楼門 (石段を上りきった所)
COURT_PATH = [(33.667717, 130.313121), (33.66776, 130.313108), (33.667787, 130.313259), (33.667853, 130.313241)]
STEPS_HAIDEN = [(33.667853, 130.313241), (33.667904, 130.313223)]   # 拝殿の前の石段

MATERIALS = {}   # shrines.py / scenery_meshes.py の FD_Shrine* (白木・緑青・石) を使う


def _xy(ctx, pts):
    return np.array([ctx.latlon(*p) for p in pts], float)


def clear(ctx):
    out = []
    for path in (STEPS_76, SANDO, STEPS_ROMON):
        p = _xy(ctx, path)
        for t in np.linspace(0, 1, 8):
            x, y = p[0] + (p[1] - p[0]) * t
            out.append((*ctx.to_frame(x, y), 4.0))
    cx, cy = _xy(ctx, HAIDEN).mean(0)
    out.append((*ctx.to_frame(cx, cy), 26.0))
    return out


def terraces(ctx):
    """境内 (拝殿・本殿・今宮神社・鹿角堂) と楼門の前後を平らにする。"""
    court = _xy(ctx, HAIDEN + HONDEN + IMAMIYA_HAIDEN + ROKKAKUDO + KAGURADEN + COURT_PATH[1:])
    cs, cu = ctx.to_frame(court[:, 0], court[:, 1])
    rx, ry = _xy(ctx, [ROMON])[0]
    rs, ru = ctx.to_frame(rx, ry)
    return [
        dict(kind="rect", s=(float(cs.min()) - 3, float(cs.max()) + 3), u=(float(cu.min()) - 3, float(cu.max()) + 3),
             z="ground", dz=0.0, feather=5.0),
        dict(kind="circle", s=float(rs), u=float(ru), r=6.0, z="ground", dz=0.0, feather=3.0),
    ]


class Builder:
    def __init__(self, ctx):
        self.ctx = ctx
        self.m = sm.Mesh("SM_FD_Meisho_Shikaumijinja", flat=True)

    def g(self, x, y):
        return self.ctx.ground(x, y)

    def put(self, sub, x, y, z, yaw_deg, scale=1.0, recolor=None):
        """部品の形 (原点が正面の真ん中の地面、奥が +X) を回して置く。"""
        t = math.radians(yaw_deg)
        rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
        for mat, v, f in sub.parts:
            v = v * scale
            v[:, :2] = v[:, :2] @ rot.T
            v += (x, y, z)
            self.m.add((recolor or {}).get(mat, mat), v, f)

    def box(self, mat, c, size, yaw):
        self.m.add(mat, *sm.box(c, size, yaw))

    # ---------------------------------------------------------------- 石段と参道
    def stairs(self, p0, p1, width, rails=2, max_rise=0.24, tread=0.32):
        """p0 -> p1 (UE m) の石段。下から上へ地面に合わせて上る。"""
        if self.g(*p0) > self.g(*p1):
            p0, p1 = p1, p0
        d = p1 - p0
        L = float(np.hypot(*d))
        t, n = d / L, np.array([-d[1], d[0]]) / L
        yaw = math.degrees(math.atan2(t[1], t[0]))
        z0, z1 = self.g(*p0) + 0.08, self.g(*p1) + 0.12
        z, s, steps = z0, 0.0, []
        while s < L:
            c = p0 + t * (s + tread / 2)
            gmax = max(self.g(*(c + n * k)) for k in (-width / 2, 0.0, width / 2))
            line = z0 + (z1 - z0) * min((s + tread) / L, 1.0)
            z = min(max(z, line, gmax + 0.1), z + max_rise)
            gmin = min(self.g(*(c + n * k)) for k in (-width / 2, width / 2))
            self.box("FD_ShrineStone", (c[0], c[1], (z + gmin - 0.5) / 2), (tread + 0.02, width, z - gmin + 0.5), yaw)
            steps.append((c, z))
            s += tread
        for k in np.linspace(-width / 2 + 0.15, width / 2 - 0.15, rails) if rails else ():
            path = np.array([(c[0] + n[0] * k, c[1] + n[1] * k, zz + 0.85) for c, zz in steps])
            self.m.add("FD_GuardrailPost", *sm.swept_rect(path, 0.05, 0.05))
            for c, zz in steps[::6]:
                self.box("FD_GuardrailPost", (c[0] + n[0] * k, c[1] + n[1] * k, zz + 0.42), (0.05, 0.05, 0.85), yaw)
        return steps, yaw

    def sando(self, p0, p1, width, lantern_every=12.0):
        """石畳の参道 (地面に沿って 1.5m ごとの石の板) と両側の石灯籠。"""
        d = p1 - p0
        L = float(np.hypot(*d))
        t, n = d / L, np.array([-d[1], d[0]]) / L
        yaw = math.degrees(math.atan2(t[1], t[0]))
        lantern = shrines.lantern()
        for s in np.arange(0.75, L, 1.5):
            c = p0 + t * s
            gz = self.g(*c)
            self.box("FD_ShrineStone", (c[0], c[1], gz - 0.15), (1.5, width, 0.42), yaw)
        for s in np.arange(lantern_every / 2, L - 2.0, lantern_every):
            for side in (-1, 1):
                q = p0 + t * s + n * side * (width / 2 + 1.2)
                self.put(lantern, q[0], q[1], self.g(*q), yaw + 90 * side)

    # ---------------------------------------------------------------- 建物
    def hall_on(self, poly, sub, default_wd, toward, recolor=None, flat_entry=True):
        """OSM の輪郭に、部品の建物 (正面の幅 x 奥行き = default_wd) を合わせて置く。正面は toward (UE m) の方。"""
        c, a, la, lb = min_rect(poly)
        b = np.array([-a[1], a[0]])
        to = np.asarray(toward, float) - c
        # 正面 (外向き f) は、輪郭の 4 辺のうち toward の方を向く辺。長い辺が正面なら平入り
        f = max((a, -a, b, -b), key=lambda k: float(np.dot(k, to)))
        width, depth = (lb, la) if abs(float(np.dot(f, a))) > 0.5 else (la, lb)
        scale = float(np.clip(((width / default_wd[0]) + (depth / default_wd[1])) / 2, 0.55, 1.8))
        front = c + f * depth / 2
        back_dir = -f
        yaw = math.degrees(math.atan2(back_dir[1], back_dir[0]))
        z = self.g(*front) if flat_entry else self.g(*c)
        self.put(sub, front[0], front[1], z, yaw, scale, recolor)
        return front, yaw

    def romon(self, x, y, yaw):
        """楼門: 2 階建ての門。原点は真ん中の地面、通り抜ける向きが +X。"""
        sub = sm.Mesh("romon")
        W, D = 7.6, 4.2
        sub.add("FD_ShrineStone", *sm.box((0, 0, -0.35), (D + 1.2, W + 1.2, 1.1)))
        for xx in (-D / 2, D / 2):
            for yy in np.linspace(-W / 2, W / 2, 4):
                sub.add("FD_ShrineWood", *sm.cylinder((xx, yy, 0.2), (xx, yy, 4.3), 0.2, n=12))
        # 下の屋根 (腰屋根: 四方に下がる)
        sub.add("FD_ShrineCopper", *sm.sweep([_rect(D + 3.0, W + 3.2, 4.25),
                                              _rect(D + 0.6, W + 0.8, 4.95)]))
        # 2 階の床と縁の欄干
        sub.add("FD_ShrineWoodDark", *sm.box((0, 0, 5.05), (D + 1.0, W + 1.0, 0.25)))
        for yy in (-(W / 2 + 0.45), W / 2 + 0.45):
            sub.add("FD_ShrineWoodDark", *sm.box((0, yy, 5.5), (D + 1.0, 0.08, 0.08)))
        for xx in (-(D / 2 + 0.45), D / 2 + 0.45):
            sub.add("FD_ShrineWoodDark", *sm.box((xx, 0, 5.5), (0.08, W + 1.0, 0.08)))
        # 2 階の胴 (白木の壁と柱)
        sub.add("FD_ShrineWood", *sm.box((0, 0, 6.35), (D - 0.6, W - 1.0, 2.4)))
        for xx in (-(D - 0.6) / 2, (D - 0.6) / 2):
            for yy in np.linspace(-(W - 1.0) / 2, (W - 1.0) / 2, 4):
                sub.add("FD_ShrineWoodDark", *sm.cylinder((xx, yy, 5.15), (xx, yy, 7.6), 0.13, n=10))
        sub.add("FD_ShrineGold", *sm.box((-(D - 0.6) / 2 - 0.08, 0, 6.6), (0.08, 1.0, 1.3)))   # 扁額
        # 上の屋根 (入母屋に近い形: 四方に下がる屋根の上に切妻の棟)
        sub.add("FD_ShrineCopper", *sm.sweep([_rect(D + 3.6, W + 3.8, 7.55), _rect(D * 0.45, W + 1.2, 9.2)]))
        shrines.gable(sub, "FD_ShrineCopper", -D * 0.35, D * 0.35, 0.0, 9.1, 10.1, -(W + 1.2) / 2, (W + 1.2) / 2,
                      t=0.18, sori=0.1)
        sub.add("FD_ShrineCopper", *sm.box((0, 0, 10.12), (0.45, W + 1.6, 0.35)))
        self.put(sub, x, y, self.g(x, y), yaw)

    def rokkakudo(self, poly, toward):
        """鹿角堂: 白壁と格子の小さな堂。石の高い基礎、正面に石段。"""
        sub = sm.Mesh("rokkakudo")
        W, D = 3.0, 5.0
        fz = 1.1
        sub.add("FD_ShrineStone", *sm.box((D / 2, 0, (fz - 1.5) / 2), (D + 0.8, W + 0.8, fz + 1.5)))
        sub.add("FD_ShrineWhite", *sm.box((D / 2, 0, fz + 1.3), (D - 0.2, W - 0.2, 2.6)))
        for yy in np.linspace(-W / 2 + 0.4, W / 2 - 0.4, 8):          # 正面の格子
            sub.add("FD_ShrineWoodDark", *sm.box((0.0, yy, fz + 1.3), (0.06, 0.06, 1.6)))
        for zz in (fz + 0.5, fz + 2.1):
            sub.add("FD_ShrineWoodDark", *sm.box((0.0, 0, zz), (0.07, W - 0.6, 0.08)))
        for xx in (0.05, D - 0.05):
            for yy in (-W / 2 + 0.05, W / 2 - 0.05):
                sub.add("FD_ShrineWoodDark", *sm.box((xx, yy, fz + 1.3), (0.18, 0.18, 2.7)))
        shrines.gable(sub, "FD_ShrineCopper", -1.0, D + 0.6, D / 2, fz + 2.65, fz + 4.1, -W / 2 - 0.7, W / 2 + 0.7,
                      t=0.15, sori=0.12)
        shrines.front_steps(sub, fz, 1.6, material="FD_ShrineStone")
        self.hall_on(poly, sub, (W, D), toward)


def _rect(dx, dy, z):
    return np.array([(dx / 2, dy / 2, z), (-dx / 2, dy / 2, z), (-dx / 2, -dy / 2, z), (dx / 2, -dy / 2, z)])


def build(ctx):
    b = Builder(ctx)
    P = lambda pts: _xy(ctx, pts)
    # ---- 鳥居と 76 段、参道、楼門の前の石段
    st = P(STEPS_76)
    low, high = (st[0], st[1]) if b.g(*st[0]) < b.g(*st[1]) else (st[1], st[0])
    d = (high - low) / np.linalg.norm(high - low)
    torii_at = low - d * 2.0
    b.put(sm.torii(name="torii", material="FD_ShrineStone"), torii_at[0], torii_at[1], b.g(*torii_at),
          math.degrees(math.atan2(d[1], d[0])), 0.9)
    b.stairs(st[0], st[1], 2.6)
    sd = P(SANDO)
    b.sando(sd[0], sd[1], 2.6)
    sr = P(STEPS_ROMON)
    b.stairs(sr[0], sr[1], 6.0, rails=3)
    # ---- 楼門 (通り抜ける向き = 石段の上る向き)
    rx, ry = P([ROMON])[0]
    up = sr[1] - sr[0]
    b.romon(rx, ry, math.degrees(math.atan2(up[1], up[0])))
    # ---- 境内の道 (石畳) と拝殿の前の石段
    cp = P(COURT_PATH)
    for p0, p1 in zip(cp[:-1], cp[1:]):
        b.sando(p0, p1, 2.4, lantern_every=1e9)
    sh = P(STEPS_HAIDEN)
    b.stairs(sh[0], sh[1], 3.0)
    # ---- 拝殿・本殿 (白木、緑青の屋根)
    haiden_c = P(HAIDEN).mean(0)
    plain = {"FD_ShrineVermilion": "FD_ShrineWoodDark"}
    b.hall_on(P(HAIDEN), shrines.haiden(), (shrines.HAIDEN["width"], shrines.HAIDEN["depth"]), sh.mean(0), plain)
    b.hall_on(P(HONDEN), shrines.honden(), (shrines.HONDEN["width"], shrines.HONDEN["depth"]), haiden_c,
              {"FD_ShrineVermilion": "FD_ShrineWoodDark", "FD_ShrineWhite": "FD_ShrineWood"})
    # ---- 今宮神社 (西の小さな拝殿と本殿) と神楽殿
    im_c = P(IMAMIYA_HAIDEN).mean(0)
    b.hall_on(P(IMAMIYA_HAIDEN), shrines.haiden(), (shrines.HAIDEN["width"], shrines.HAIDEN["depth"]), haiden_c, plain)
    b.hall_on(P(IMAMIYA_HONDEN), shrines.honden(), (shrines.HONDEN["width"], shrines.HONDEN["depth"]), im_c,
              {"FD_ShrineVermilion": "FD_ShrineWoodDark", "FD_ShrineWhite": "FD_ShrineWood"})
    kg = sm.Mesh("kagura")
    shrines.raised_hall(kg, 7.0, 7.0, 0.9, 0.1, "FD_ShrineWood", "FD_ShrineWoodDark")
    for xx in (0.0, 7.0):
        for yy in (-3.5, 3.5):
            kg.add("FD_ShrineWoodDark", *sm.cylinder((xx, yy, 0.9), (xx, yy, 3.6), 0.16, n=10))
    shrines.gable(kg, "FD_ShrineCopper", -1.2, 8.2, 3.5, 3.6, 5.6, -4.6, 4.6, t=0.2)
    b.hall_on(P(KAGURADEN), kg, (7.0, 7.0), cp[0])
    # ---- 鹿角堂
    b.rokkakudo(P(ROKKAKUDO), cp[2])
    return b.m
