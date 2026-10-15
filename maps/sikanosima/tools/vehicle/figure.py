"""人の形の部品 (胴・頭・腕・脚)。歩く人 (build_walker.py) とライダー (build_crosscub.py) が使う。

座標はメートル、+X が前、+Y が右、+Z が上 (tools/terrain/scenery_meshes.py と同じ)。
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "terrain"))
import scenery_meshes as sm  # noqa: E402


# ---------------------------------------------------------------- 形の道具
def frames_along(path, up_hint):
    """path の各点での (接線, 横, 上)。横は up_hint と接線から決める。"""
    path = np.asarray(path, float)
    out = []
    for i in range(len(path)):
        t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        side = np.cross(up_hint, t)
        side /= np.linalg.norm(side)
        out.append((t, side, np.cross(t, side)))
    return out


def loft(path, widths, heights, n=16, exponent=3.0, up_hint=(0, 0, 1)):
    """path に沿って、角の丸い四角 (超楕円) の断面を流した形。幅は横、高さは上の向き。"""
    path = np.asarray(path, float)
    widths = np.broadcast_to(np.asarray(widths, float), len(path))
    heights = np.broadcast_to(np.asarray(heights, float), len(path))
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    cs, sn = np.cos(a), np.sin(a)
    e = 2.0 / exponent
    sx = np.sign(cs) * np.abs(cs) ** e
    sy = np.sign(sn) * np.abs(sn) ** e
    rings = []
    for p, (t, side, up), w, h in zip(path, frames_along(path, np.asarray(up_hint, float)), widths, heights):
        rings.append(p + (sx * w / 2)[:, None] * side + (sy * h / 2)[:, None] * up)
    return sm.sweep(rings)


def ellipsoid(center, radii, subdiv=2):
    v, f = sm.icosphere(subdiv)
    return v * np.asarray(radii, float) + np.asarray(center, float), f


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------- 体の部品
def torso(m, hip, neck, lean_axis=(-1, 0, 0), top="FD_WK_Jacket", bottom="FD_WK_Pants", shoulder_half=0.195):
    """腰 (hip) から首の付け根 (neck) までの胴。腰まわりはズボン、上は上着。肩は丸く膨らませる。

    胴の幅 (左右) と厚み (前後) は、腰・胴のくびれ・胸・肩の高さで変える。lean_axis は胴の「前」と逆の向き
    (loft の up_hint)。立っている人は (-1, 0, 0)。
    """
    hip, neck = np.asarray(hip, float), np.asarray(neck, float)
    spine = neck - hip

    def at(t, forward=0.0):
        return hip + spine * t + np.array([forward, 0.0, 0.0])

    # 腰まわり (ズボン)。上着の裾が少し重なる
    m.add(bottom, *loft([at(-0.11), at(0.0), at(0.10), at(0.20)],
                        [0.30, 0.345, 0.34, 0.31], [0.19, 0.215, 0.21, 0.19], n=20, exponent=2.3, up_hint=lean_axis))
    # 上着: 裾 → くびれ → みぞおち → 胸 → 肩
    ts = [0.12, 0.30, 0.50, 0.70, 0.86, 0.97, 1.0]
    widths = [0.355, 0.320, 0.335, 0.375, 0.405, 0.350, 0.20]
    depths = [0.225, 0.200, 0.215, 0.235, 0.215, 0.165, 0.11]
    fwd = [0.0, 0.0, 0.006, 0.012, 0.006, -0.005, -0.008]
    m.add(top, *loft([at(t, f) for t, f in zip(ts, fwd)], widths, depths, n=24, exponent=2.2, up_hint=lean_axis))
    # 肩の丸み
    for y in (-1, 1):
        m.add(top, *ellipsoid(at(0.93) + [-0.005, y * shoulder_half, 0.0], (0.058, 0.056, 0.052), subdiv=2))
    # 襟
    m.add(top, *sm.cylinder(at(0.96), neck + spine * 0.04, 0.072, 0.064, n=18))


def head(m, neck, up=(0, 0, 1), skin="FD_WK_Skin", hair="FD_WK_Hair", hair_cap=True):
    """首の付け根 (neck) から上: 首、頭 (あご・耳・鼻・目・眉)、髪。up は首の向き。"""
    neck, up = np.asarray(neck, float), _unit(up)
    fwd = _unit(np.cross([0, 1, 0], up))          # 前 (+X 寄り)
    right = np.cross(up, fwd)
    c = neck + up * 0.165 + fwd * 0.01             # 頭の中心

    def p(x, y, z):
        return c + fwd * x + right * y + up * z

    def ell(x, y, z, rx, ry, rz, mat, subdiv=2):
        v, f = sm.icosphere(subdiv)
        v = v * [rx, ry, rz]
        v = v[:, 0:1] * fwd + v[:, 1:2] * right + v[:, 2:3] * up
        m.add(mat, v + p(x, y, z), f)

    m.add(skin, *sm.cylinder(neck - up * 0.02, neck + up * 0.10 + fwd * 0.006, 0.052, 0.049, n=16))
    ell(0.0, 0, 0.0, 0.098, 0.083, 0.112, skin, subdiv=3)          # 頭
    ell(0.025, 0, -0.05, 0.072, 0.064, 0.058, skin, subdiv=2)       # あご・頬
    ell(0.097, 0, -0.012, 0.022, 0.014, 0.028, skin, subdiv=1)      # 鼻
    for y in (-1, 1):
        ell(-0.008, y * 0.083, -0.005, 0.02, 0.013, 0.032, skin, subdiv=1)   # 耳
        ell(0.087, y * 0.032, 0.017, 0.007, 0.011, 0.007, hair, subdiv=1)    # 目
        ell(0.088, y * 0.033, 0.036, 0.006, 0.018, 0.004, hair, subdiv=1)    # 眉
    if hair_cap:
        ell(-0.018, 0, 0.033, 0.104, 0.089, 0.098, hair, subdiv=3)  # 髪 (額の上から後ろ)
        ell(-0.058, 0, -0.012, 0.058, 0.080, 0.075, hair, subdiv=2)  # 襟足


def limb(m, p0, p1, r0, r1, material, n=16, joint=None):
    """関節 p0 から p1 までの手足の一節 (先細りの円柱)。joint を渡すと p0 に丸い関節を付ける。"""
    m.add(material, *sm.cylinder(p0, p1, r0, r1, n=n))
    if joint is not None:
        m.add(material, *ellipsoid(p0, (joint, joint, joint), subdiv=2))


def hand(m, wrist, down, inward, skin="FD_WK_Skin", fist=False):
    """手首 (wrist) から先の手。down は指先の向き、inward は手のひらの向き (体の内側)。親指は手のひら側の前に付く。"""
    wrist, down, inward = np.asarray(wrist, float), _unit(down), _unit(inward)
    fwd = _unit(np.cross(inward, down))
    if fwd @ np.array([1.0, 0.0, 0.0]) < 0:
        fwd = -fwd
    length = 0.075 if fist else 0.095
    c = wrist + down * length * 0.55

    def ell(center, rx, ry, rz):
        v, f = sm.icosphere(2)
        v = v * [rx, ry, rz]
        v = v[:, 0:1] * fwd + v[:, 1:2] * inward + v[:, 2:3] * down
        m.add(skin, v + center, f)

    m.add(skin, *sm.cylinder(wrist - down * 0.01, wrist + down * 0.02, 0.026, 0.028, n=12))
    ell(c, 0.044, 0.019, length * 0.5)                                    # 手のひらと指
    ell(wrist + down * 0.035 + fwd * 0.03 + inward * 0.012, 0.012, 0.013, 0.03)   # 親指
