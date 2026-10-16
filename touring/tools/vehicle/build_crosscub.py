"""ホンダ クロスカブ110 (JA60) とライダーの形を作り、glTF で書き出す。

    py -3 tools/vehicle/build_crosscub.py

出力 (tools/vehicle/out/crosscub/) は tools/ue/setup_project.py が /Game/FukuokaDrive/Vehicle に取り込み、
C++ の AFDBikePawn が組み立てる。

| メッシュ | 中身 | 原点と向き |
| --- | --- | --- |
| SM_CC_Body | フレームのカバー、エンジン、マフラー、シート、リアキャリア、後ろのフェンダー・ライト | 前後輪の接地点の中点。+X が前、+Y が右 |
| SM_CC_Steering | フロントフォーク、前のフェンダー、ハンドル、ヘッドライトとガード、メーター、ミラー | ステアリングの軸の上端。+Z が軸 (上が後ろへ 27° 傾く) |
| SM_CC_Wheel | タイヤ (ブロックパターン)、リム、スポーク、ハブ。前後で共用 | 車軸の中心。+Y が車軸 |
| SM_CC_Rider | ヘルメット・ジャケット・ジーンズのライダー (乗車姿勢) | SM_CC_Body と同じ |

寸法はクロスカブ110 の公称値に合わせる (ホイールベース 1230mm、キャスター 27°、トレール 78mm、シート高 784mm、
タイヤ 80/90-17)。ステアリングの軸の位置は C++ (FDBikePawn.cpp) も同じ式で求めるので、変えるときは両方を変える。

色はリニア。車体色 (FD_CC_Paint) とライトのレンズ (FD_CC_HeadLens / FD_CC_TailLens) は、取り込み後に
setup_project.py が専用のマテリアルに差し替える (色やブレーキランプの明るさを C++ から変えるため)。
"""

import math
import os
import sys

import numpy as np

import figure as fg
from figure import ellipsoid, loft, sm

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "crosscub")

# ---------------------------------------------------------------- 寸法 (m)
WHEELBASE = 1.23
WHEEL_R = 0.29          # 80/90-17 の外径 576mm
RAKE_DEG = 27.0         # キャスター角
TRAIL = 0.078
HEAD_TOP_Z = 0.95       # ステアリングの軸の上端 (ハンドルの付け根) の高さ

FRONT_AXLE = np.array([WHEELBASE / 2, 0.0, WHEEL_R])
REAR_AXLE = np.array([-WHEELBASE / 2, 0.0, WHEEL_R])
_S, _C = math.sin(math.radians(RAKE_DEG)), math.cos(math.radians(RAKE_DEG))
AXIS_UP = np.array([-_S, 0.0, _C])                                   # 軸の上向き (上ほど後ろ)
AXIS_GROUND = np.array([WHEELBASE / 2 + TRAIL, 0.0, 0.0])            # 軸の延長が地面と交わる点
HEAD_TOP = AXIS_GROUND + AXIS_UP * (HEAD_TOP_Z / _C)

GRIP = np.array([0.15, 0.37, 1.06])  # 右のグリップの端 (左は Y を反転)

sm.MATERIALS.update({
    "FD_CC_Paint": dict(color=(0.80, 0.50, 0.02), roughness=0.3),        # 黄色。UE で差し替える
    "FD_CC_Black": dict(color=(0.018, 0.018, 0.02), roughness=0.45),     # 黒い樹脂・塗装
    "FD_CC_Frame": dict(color=(0.03, 0.03, 0.032), roughness=0.35),      # 黒い鉄パイプ
    "FD_CC_Metal": dict(color=(0.62, 0.62, 0.62), roughness=0.3, metallic=1.0),
    "FD_CC_Chrome": dict(color=(0.85, 0.85, 0.85), roughness=0.12, metallic=1.0),
    "FD_CC_Engine": dict(color=(0.20, 0.20, 0.21), roughness=0.45, metallic=0.6),
    "FD_CC_Rubber": dict(color=(0.012, 0.012, 0.012), roughness=0.9),
    "FD_CC_Seat": dict(color=(0.025, 0.020, 0.017), roughness=0.6),
    "FD_CC_HeadLens": dict(color=(0.9, 0.9, 0.85), roughness=0.1),       # UE で光るマテリアルに差し替える
    "FD_CC_TailLens": dict(color=(0.5, 0.01, 0.01), roughness=0.15),     # 同上
    "FD_CC_Amber": dict(color=(0.8, 0.30, 0.01), roughness=0.15),
    "FD_CC_Meter": dict(color=(0.75, 0.75, 0.72), roughness=0.3),
    "FD_CC_Plate": dict(color=(0.85, 0.45, 0.55), roughness=0.4),        # 原付二種 (90cc 超) のピンクのナンバー
    "FD_CC_Helmet": dict(color=(0.80, 0.80, 0.78), roughness=0.25),
    "FD_CC_Visor": dict(color=(0.02, 0.025, 0.03), roughness=0.05),
    "FD_CC_Jacket": dict(color=(0.10, 0.12, 0.07), roughness=0.8),       # オリーブのジャケット
    "FD_CC_Jeans": dict(color=(0.035, 0.05, 0.10), roughness=0.85),
    "FD_CC_Glove": dict(color=(0.045, 0.03, 0.02), roughness=0.7),
    "FD_CC_Skin": dict(color=(0.55, 0.36, 0.25), roughness=0.6),
    "FD_CC_Boot": dict(color=(0.07, 0.04, 0.02), roughness=0.6),
})


# ---------------------------------------------------------------- 形の部品
def pipe(path, r, n=10):
    """曲がったパイプ。path の向きによらず断面がねじれないよう、前の輪の向きを引き継ぐ。"""
    path = np.asarray(path, float)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rings, u = [], None
    for i, p in enumerate(path):
        t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        if u is None:
            u = np.cross(t, [0, 0, 1] if abs(t[2]) < 0.9 else [1, 0, 0])
        u = u - t * (u @ t)
        u /= np.linalg.norm(u)
        w = np.cross(t, u)
        rings.append(p + r * (np.cos(a)[:, None] * u + np.sin(a)[:, None] * w))
    return sm.sweep(rings)


def lathe(profile, n=48, radius_fn=None):
    """Y 軸のまわりに (半径, Y) の閉じた輪郭を回した形 (タイヤ・リムなど)。radius_fn(角度, 輪郭の番号) で半径を足せる。"""
    profile = np.asarray(profile, float)
    m = len(profile)
    verts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        for j, (r, y) in enumerate(profile):
            rr = r + (radius_fn(th, j) if radius_fn else 0.0)
            verts.append((rr * math.cos(th), y, rr * math.sin(th)))
    tris = []
    for i in range(n):
        i2 = (i + 1) % n
        for j in range(m):
            j2 = (j + 1) % m
            a, b, c, d = i * m + j, i * m + j2, i2 * m + j2, i2 * m + j
            tris += [(a, b, c), (a, c, d)]
    return np.array(verts), np.array(tris)


def arc(center, radius, deg0, deg1, n=16, y=0.0):
    """XZ 平面の円弧 (角度は +X から +Z へ)。"""
    t = np.radians(np.linspace(deg0, deg1, n))
    c = np.asarray(center, float)
    return np.stack([c[0] + radius * np.cos(t), np.full(n, c[1] + y), c[2] + radius * np.sin(t)], 1)


def disc(center, axis, r, thickness, n=24):
    c, ax = np.asarray(center, float), np.asarray(axis, float)
    ax = ax / np.linalg.norm(ax)
    return sm.cylinder(c - ax * thickness / 2, c + ax * thickness / 2, r, n=n)


# ---------------------------------------------------------------- 車体
def body():
    m = sm.Mesh("SM_CC_Body")
    head_low = AXIS_GROUND + AXIS_UP * (0.74 / _C)
    # ヘッドパイプとフロントカバー (クロスカブはレッグシールドがなく、前のカバーとフレームのカバーが車体色)
    m.add("FD_CC_Frame", *sm.cylinder(head_low, HEAD_TOP - AXIS_UP * 0.02, 0.032, n=14))
    m.add("FD_CC_Paint", *loft([head_low + [0.02, 0, 0.12], head_low + [-0.06, 0, -0.02], [0.12, 0, 0.56], [0.02, 0, 0.50]],
                               [0.20, 0.24, 0.22, 0.19], [0.15, 0.17, 0.15, 0.13], exponent=3.5))
    # 足元の低いフレームカバー (ステップスルー) から、シートの下の車体へ
    m.add("FD_CC_Paint", *loft([[0.06, 0, 0.51], [-0.08, 0, 0.50], [-0.20, 0, 0.55], [-0.34, 0, 0.62], [-0.52, 0, 0.64]],
                               [0.19, 0.20, 0.26, 0.29, 0.25], [0.13, 0.14, 0.20, 0.18, 0.14], exponent=3.0))
    # シート (前が低く、後ろがやや高い一人乗り)
    m.add("FD_CC_Seat", *loft([[0.0, 0, 0.735], [-0.12, 0, 0.75], [-0.32, 0, 0.755], [-0.52, 0, 0.76]],
                              [0.22, 0.28, 0.28, 0.24], [0.06, 0.085, 0.09, 0.07], exponent=2.6))
    # リアキャリア (大きな黒い荷台)
    rack_z = 0.80
    for y in (-0.15, 0.15):
        m.add("FD_CC_Frame", *pipe([[-0.50, y, rack_z], [-0.96, y, rack_z]], 0.011))
        m.add("FD_CC_Frame", *pipe([[-0.56, y, rack_z], [-0.62, y * 0.9, 0.66]], 0.011))
        m.add("FD_CC_Frame", *pipe([[-0.90, y, rack_z], [-0.86, y * 0.9, 0.68]], 0.011))
    for x in np.linspace(-0.52, -0.96, 6):
        m.add("FD_CC_Frame", *pipe([[x, -0.15, rack_z], [x, 0.15, rack_z]], 0.009))
    # 後ろのフェンダー、テールランプ、ナンバー、ウインカー
    m.add("FD_CC_Black", *loft(arc(REAR_AXLE, 0.355, 55, 168, n=14), 0.12, 0.012, up_hint=(0, 1, 0), exponent=2.5))
    m.add("FD_CC_Black", *sm.box((-0.93, 0, 0.70), (0.08, 0.13, 0.07)))
    m.add("FD_CC_TailLens", *sm.box((-0.972, 0, 0.70), (0.012, 0.11, 0.05)))
    m.add("FD_CC_Plate", *sm.box((-0.985, 0, 0.58), (0.008, 0.20, 0.10)))
    for y in (-1, 1):
        m.add("FD_CC_Frame", *sm.cylinder((-0.86, y * 0.08, 0.70), (-0.86, y * 0.15, 0.71), 0.008, n=6))
        m.add("FD_CC_Amber", *sm.cylinder((-0.88, y * 0.155, 0.71), (-0.83, y * 0.155, 0.71), 0.02, n=12))
    # エンジン (横向きの単気筒。シリンダーはほぼ水平に前を向く) とクランクケース
    m.add("FD_CC_Engine", *loft([[0.12, 0, 0.32], [-0.02, 0, 0.32], [-0.14, 0, 0.36]], [0.20, 0.26, 0.22], [0.20, 0.22, 0.18], exponent=2.4))
    m.add("FD_CC_Engine", *ellipsoid((-0.04, -0.12, 0.33), (0.11, 0.04, 0.10)))   # 左のクランクケースカバー
    m.add("FD_CC_Engine", *ellipsoid((0.0, 0.12, 0.31), (0.09, 0.035, 0.08)))     # 右のクラッチカバー
    m.add("FD_CC_Engine", *sm.cylinder((0.10, 0, 0.36), (0.26, 0, 0.385), 0.055, n=16))
    for x in np.linspace(0.13, 0.25, 7):
        m.add("FD_CC_Metal", *disc((x, 0, 0.36 + (x - 0.10) * 0.16), (1, 0, 0.16), 0.075, 0.008, n=20))  # 冷却フィン
    m.add("FD_CC_Engine", *sm.box((0.29, 0, 0.39), (0.06, 0.13, 0.11)))           # シリンダーヘッド
    # マフラー (右側)。排気管はシリンダーヘッドの下から車体の下をくぐって右へ
    m.add("FD_CC_Chrome", *pipe([[0.29, 0.02, 0.33], [0.31, 0.04, 0.24], [0.22, 0.10, 0.19], [0.02, 0.15, 0.21],
                                 [-0.14, 0.18, 0.30]], 0.019))
    m.add("FD_CC_Black", *sm.cylinder((-0.14, 0.18, 0.31), (-0.62, 0.18, 0.43), 0.052, 0.045, n=18))
    m.add("FD_CC_Metal", *loft([[-0.16, 0.235, 0.32], [-0.40, 0.235, 0.38], [-0.58, 0.23, 0.425]], 0.012, [0.07, 0.09, 0.07],
                               exponent=4))  # ヒートガード
    m.add("FD_CC_Chrome", *sm.cylinder((-0.62, 0.18, 0.43), (-0.66, 0.18, 0.44), 0.02, n=10))
    # スイングアーム、チェーンケース (左)、リアサスペンション
    for y in (-0.09, 0.09):
        m.add("FD_CC_Frame", *sm.cylinder((-0.12, y, 0.35), REAR_AXLE + [0, y, 0], 0.018, n=10))
    m.add("FD_CC_Black", *loft([[-0.08, -0.115, 0.34], [-0.60, -0.115, 0.29]], 0.03, [0.13, 0.10], exponent=4))
    for y in (-0.125, 0.125):
        m.add("FD_CC_Frame", *sm.cylinder(REAR_AXLE + [0.03, y, 0.02], (-0.44, y, 0.66), 0.018, n=10))
        m.add("FD_CC_Chrome", *sm.cylinder(REAR_AXLE + [0.07, y, 0.12], (-0.47, y, 0.58), 0.026, n=12))  # ばね
    # ステップ (ゴム) とチェンジペダル
    for y in (-1, 1):
        m.add("FD_CC_Frame", *sm.cylinder((0.02, y * 0.10, 0.30), (0.02, y * 0.17, 0.30), 0.012, n=8))
        m.add("FD_CC_Rubber", *sm.cylinder((0.02, y * 0.17, 0.30), (0.02, y * 0.27, 0.30), 0.02, n=10))
    m.add("FD_CC_Frame", *pipe([[-0.02, -0.14, 0.33], [0.08, -0.17, 0.31], [0.12, -0.19, 0.33]], 0.009))
    return m


# ---------------------------------------------------------------- ハンドルまわり (ステアリングの軸と一緒に回る)
def steering():
    m = sm.Mesh("SM_CC_Steering")
    # フロントフォーク (軸と平行に、トレールが 78mm になるだけ前へずらす)
    for y in (-0.085, 0.085):
        bottom = FRONT_AXLE + [0, y, 0]
        top = bottom + AXIS_UP * 0.62
        m.add("FD_CC_Black", *sm.cylinder(bottom - AXIS_UP * 0.03, bottom + AXIS_UP * 0.30, 0.03, n=14))
        m.add("FD_CC_Frame", *sm.cylinder(bottom + AXIS_UP * 0.30, top, 0.022, n=14))
    m.add("FD_CC_Frame", *sm.box(HEAD_TOP - AXIS_UP * 0.18 + [0.03, 0, 0], (0.06, 0.22, 0.04)))  # 下のブラケット
    # 前のフェンダー (短い、車体色)
    m.add("FD_CC_Paint", *loft(arc(FRONT_AXLE, 0.335, 35, 122, n=12), 0.11, 0.012, up_hint=(0, 1, 0), exponent=2.5))
    for y in (-0.06, 0.06):
        m.add("FD_CC_Frame", *sm.cylinder(FRONT_AXLE + [0.02, y, 0.15], FRONT_AXLE + [0.08, y, 0.30], 0.008, n=6))
    # ハンドル (アップハンドル、補強のバー付き)
    gl, gr = GRIP * [1, -1, 1], GRIP
    bar = [gl, gl + [0.04, 0.10, -0.01], [0.25, -0.17, 1.00], [0.26, 0.0, 0.99], [0.25, 0.17, 1.00], gr + [0.04, -0.10, -0.01], gr]
    m.add("FD_CC_Frame", *pipe(bar, 0.011))
    m.add("FD_CC_Frame", *pipe([[0.24, -0.17, 1.04], [0.25, 0.17, 1.04]], 0.009))
    m.add("FD_CC_Black", *ellipsoid(HEAD_TOP + [0.04, 0, 0.04], (0.08, 0.09, 0.05)))  # ハンドルの付け根のカバー
    for y in (-1, 1):
        g = GRIP * [1, y, 1]
        inner = g + [0.04, -y * 0.10, -0.01]
        m.add("FD_CC_Rubber", *sm.cylinder(g, g + (inner - g) * 0.85, 0.017, n=12))
        m.add("FD_CC_Metal", *pipe([inner + [0.015, 0, 0.0], inner + [0.07, y * 0.02, 0.0], g + [0.07, -y * 0.0, 0.0]], 0.006))  # レバー
        # ミラー
        base = inner + [0.0, -y * 0.03, 0.01]
        m.add("FD_CC_Frame", *pipe([base, base + [-0.02, y * 0.04, 0.12], base + [-0.03, y * 0.07, 0.20]], 0.006))
        m.add("FD_CC_Black", *ellipsoid(base + [-0.035, y * 0.08, 0.23], (0.015, 0.055, 0.04)))
    # ヘッドライト (丸型) とライトガード
    lc = np.array([0.36, 0.0, 0.985])
    m.add("FD_CC_Paint", *sm.cylinder(lc - [0.09, 0, 0], lc, 0.085, 0.09, n=28))
    m.add("FD_CC_Chrome", *sm.cylinder(lc - [0.005, 0, 0], lc + [0.012, 0, 0], 0.092, n=28))
    m.add("FD_CC_HeadLens", *sm.cylinder(lc, lc + [0.016, 0, 0], 0.078, n=28))
    for y in (-1, 1):
        m.add("FD_CC_Frame", *pipe([[0.24, y * 0.08, 0.90], [0.36, y * 0.115, 0.88], [0.43, y * 0.115, 0.92],
                                    [0.45, y * 0.11, 1.00], [0.43, y * 0.10, 1.08], [0.35, y * 0.09, 1.10], [0.27, y * 0.06, 1.06]], 0.011))
        m.add("FD_CC_Amber", *sm.cylinder((0.30, y * 0.16, 0.97), (0.36, y * 0.16, 0.97), 0.02, n=12))
        m.add("FD_CC_Frame", *sm.cylinder((0.30, y * 0.09, 0.97), (0.31, y * 0.155, 0.97), 0.007, n=6))
    m.add("FD_CC_Frame", *pipe([[0.455, -0.11, 1.0], [0.465, 0, 1.0], [0.455, 0.11, 1.0]], 0.010))
    # メーター (丸型、ライダーの方を向く)
    mc = np.array([0.245, 0.0, 1.095])
    tilt = np.array([-0.55, 0, 0.84])
    m.add("FD_CC_Black", *disc(mc, tilt, 0.06, 0.05))
    m.add("FD_CC_Meter", *disc(mc + tilt * 0.026, tilt, 0.05, 0.004))
    return to_steering_space(m)


def to_steering_space(mesh):
    """車体の座標で作った形を、ステアリングの軸の上端を原点、軸を +Z とする座標へ移す。"""
    out = sm.Mesh(mesh.name)
    for mat, v, f in mesh.parts:
        d = v - HEAD_TOP
        x = _C * d[:, 0] + _S * d[:, 2]
        z = -_S * d[:, 0] + _C * d[:, 2]
        out.add(mat, np.stack([x, d[:, 1], z], 1), f)
    return out


# ---------------------------------------------------------------- ホイール (前後共用)
def wheel():
    m = sm.Mesh("SM_CC_Wheel")
    half_w, tire_h = 0.040, 0.072
    rc = WHEEL_R - tire_h / 2
    prof = [(rc + tire_h / 2 * math.cos(a), half_w * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)]

    def tread(th, j):
        r, y = prof[j]
        if r < rc + tire_h * 0.3:
            return 0.0
        # ブロックパターン: 周方向に 36 個のブロック、左右で半分ずらす
        k = (th / (2 * math.pi) * 36 + (0.5 if y > 0 else 0.0)) % 1.0
        return 0.004 if k < 0.6 else -0.002

    m.add("FD_CC_Rubber", *lathe(prof, n=108, radius_fn=tread))
    rim_in, rim_out = 0.198, rc - tire_h / 2 + 0.006
    m.add("FD_CC_Metal", *lathe([(rim_in, -0.028), (rim_out, -0.03), (rim_out, 0.03), (rim_in, 0.028)], n=72))
    # ハブ (ドラムブレーキ) と車軸
    m.add("FD_CC_Metal", *sm.cylinder((0, -0.065, 0), (0, 0.055, 0), 0.06, n=24))
    m.add("FD_CC_Engine", *sm.cylinder((0, -0.075, 0), (0, -0.06, 0), 0.075, n=24))
    m.add("FD_CC_Chrome", *sm.cylinder((0, -0.10, 0), (0, 0.10, 0), 0.008, n=8))
    # スポーク 36 本 (左右 18 本ずつ、ハブから接線方向へ)
    for i in range(36):
        side = 1 if i % 2 else -1
        th = 2 * math.pi * i / 36
        th_hub = th + side * 0.35
        hub = (0.05 * math.cos(th_hub), side * 0.045, 0.05 * math.sin(th_hub))
        rim = (rim_in * math.cos(th), side * 0.012, rim_in * math.sin(th))
        m.add("FD_CC_Chrome", *sm.cylinder(hub, rim, 0.0022, n=4))
    return m


# ---------------------------------------------------------------- ライダー (乗車姿勢)
def rider():
    m = sm.Mesh("SM_CC_Rider")
    hip, neck = np.array([-0.22, 0.0, 0.90]), np.array([-0.13, 0.0, 1.40])
    # 胴 (少し前かがみ): 腰まわりはジーンズ、上はジャケット。肩は丸く
    fg.torso(m, hip, neck, lean_axis=(-1, 0, 0.15), top="FD_CC_Jacket", bottom="FD_CC_Jeans", shoulder_half=0.19)
    # 首 (ヘルメットの下に少し見える)
    m.add("FD_CC_Skin", *sm.cylinder(neck - [0, 0, 0.02], neck + [0.025, 0, 0.09], 0.05, 0.047, n=14))
    for y in (-1, 1):
        # 脚: 太もも → 膝 → すね → ブーツ
        hip_j, knee, ankle = np.array([-0.17, y * 0.10, 0.87]), np.array([0.10, y * 0.17, 0.76]), np.array([0.03, y * 0.20, 0.38])
        fg.limb(m, hip_j, knee, 0.082, 0.062, "FD_CC_Jeans", n=16, joint=0.085)
        fg.limb(m, knee, ankle + [0, 0, 0.1], 0.06, 0.048, "FD_CC_Jeans", n=16, joint=0.062)
        m.add("FD_CC_Boot", *sm.cylinder(ankle + [0, 0, 0.13], ankle - [0, 0, 0.05], 0.054, 0.052, n=14))
        m.add("FD_CC_Boot", *loft([[-0.06, y * 0.20, 0.34], [-0.01, y * 0.20, 0.335], [0.06, y * 0.20, 0.325], [0.14, y * 0.20, 0.315]],
                                  [0.09, 0.10, 0.10, 0.08], [0.10, 0.10, 0.075, 0.055], n=18, exponent=2.6))
        # 腕: 肩 → 肘 → 手首 → グローブ (グリップを握る)
        shoulder, elbow = np.array([-0.135, y * 0.215, 1.36]), np.array([-0.03, y * 0.29, 1.13])
        grip = GRIP * [1, y, 1] + [0.0, -y * 0.03, 0.0]
        down = (grip - elbow) / np.linalg.norm(grip - elbow)
        wrist = grip - down * 0.06
        m.add("FD_CC_Jacket", *ellipsoid(shoulder + [0, -y * 0.01, 0], (0.06, 0.06, 0.065)))
        fg.limb(m, shoulder, elbow, 0.055, 0.046, "FD_CC_Jacket", n=14)
        fg.limb(m, elbow, wrist + down * 0.01, 0.046, 0.039, "FD_CC_Jacket", n=14, joint=0.047)
        m.add("FD_CC_Jacket", *sm.cylinder(wrist - down * 0.03, wrist + down * 0.005, 0.042, 0.042, n=14))   # 袖口
        fg.hand(m, wrist, down, (0.0, -y * 0.35, -1.0), skin="FD_CC_Glove", fist=True)
    # ヘルメット (フルフェイス) とシールド
    m.add("FD_CC_Helmet", *ellipsoid((-0.10, 0, 1.55), (0.145, 0.125, 0.14), subdiv=3))
    m.add("FD_CC_Visor", *ellipsoid((-0.025, 0, 1.545), (0.08, 0.105, 0.065), subdiv=2))
    return m


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for mesh in (body(), steering(), wheel(), rider()):
        tris = sm.write_gltf(mesh, os.path.join(OUT_DIR, f"{mesh.name}.gltf"))
        lo, hi = mesh.bounds()
        print(f"  {mesh.name}.gltf: 三角形 {tris}、大きさ {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f} x {hi[2] - lo[2]:.2f} m")
    print(f"ステアリングの軸の上端: X {HEAD_TOP[0] * 100:.1f} cm, Z {HEAD_TOP[2] * 100:.1f} cm (FDBikePawn.cpp と同じ値になること)")


if __name__ == "__main__":
    main()
