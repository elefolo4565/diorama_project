"""バイクを降りて歩く人 (AFDWalkerCharacter) の形を作り、glTF で書き出す。

    py -3 tools/vehicle/build_walker.py

出力 (tools/vehicle/out/walker/) は tools/ue/setup_project.py が /Game/FukuokaDrive/Vehicle に取り込み、
C++ の AFDWalkerCharacter が関節ごとに組み立てて、歩く速さに合わせて振る。

| メッシュ | 中身 | 原点 (C++ の関節) |
| --- | --- | --- |
| SM_FD_WalkerBody | 腰・胴・首・頭・髪 | 足の裏の高さの真ん中 |
| SM_FD_WalkerUpperArm | 上腕 (右腕。左は C++ で Y を反転して使う) | 肩 |
| SM_FD_WalkerForearm | 前腕と手 (右手) | 肘 |
| SM_FD_WalkerThigh | 太もも | 股関節 |
| SM_FD_WalkerShin | すねと靴 | 膝 |

関節の位置は C++ (FDWalkerCharacter.cpp の HipZCm・ShoulderZCm・KneeDropCm・ElbowDropCm など) と同じ値にする。
マテリアルは FD_WK_Skin / Hair / Jacket / Pants / Shoe。C++ がスロット名を見て、それぞれの色に塗り替える。
"""

import os

import numpy as np

import figure as fg
from figure import sm

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "walker")

# ---------------------------------------------------------------- 関節 (m、足の裏が 0)。C++ と合わせる
HIP_Z = 0.90
HIP_Y = 0.10
SHOULDER_Z = 1.46
SHOULDER_Y = 0.22
KNEE_DROP = 0.43       # 股関節から膝まで
SHIN_DROP = 0.47       # 膝から足の裏まで
ELBOW_DROP = 0.29      # 肩から肘まで
NECK_Z = 1.47          # 首の付け根

# 色はリニア。C++ の既定の色 (SkinColor など) と同じ。UE では C++ が塗り替える
sm.MATERIALS.update({
    "FD_WK_Skin": dict(color=(0.55, 0.36, 0.25), roughness=0.6),
    "FD_WK_Hair": dict(color=(0.02, 0.015, 0.01), roughness=0.7),
    "FD_WK_Jacket": dict(color=(0.22, 0.20, 0.11), roughness=0.8),
    "FD_WK_Pants": dict(color=(0.04, 0.06, 0.13), roughness=0.85),
    "FD_WK_Shoe": dict(color=(0.03, 0.03, 0.03), roughness=0.6),
})


def body():
    m = sm.Mesh("SM_FD_WalkerBody")
    fg.torso(m, (0.0, 0.0, HIP_Z + 0.05), (0.0, 0.0, NECK_Z))
    fg.head(m, (0.004, 0.0, NECK_Z))
    return m


def upper_arm():
    """右の上腕。原点が肩で、下 (-Z) へ伸びる。"""
    m = sm.Mesh("SM_FD_WalkerUpperArm")
    elbow = np.array([0.0, 0.0, -ELBOW_DROP])
    m.add("FD_WK_Jacket", *fg.ellipsoid((0.0, -0.008, -0.04), (0.056, 0.055, 0.05)))   # 肩の付け根 (胴の肩の線より上に出さない)
    fg.limb(m, (0.0, 0.0, -0.04), elbow + [0, 0, 0.01], 0.052, 0.044, "FD_WK_Jacket")
    return m


def forearm():
    """右の前腕と手。原点が肘で、下 (-Z) へ伸びる。手のひらは内側 (-Y)。"""
    m = sm.Mesh("SM_FD_WalkerForearm")
    wrist = np.array([0.0, 0.0, -0.245])
    fg.limb(m, (0.0, 0.0, 0.0), wrist + [0, 0, 0.012], 0.044, 0.036, "FD_WK_Jacket", joint=0.045)
    m.add("FD_WK_Jacket", *sm.cylinder(wrist + [0, 0, 0.02], wrist - [0, 0, 0.004], 0.039, 0.039, n=16))   # 袖口
    fg.hand(m, wrist, (0.0, 0.0, -1.0), (0.0, -1.0, 0.0), skin="FD_WK_Skin")
    return m


def thigh():
    """太もも。原点が股関節で、下 (-Z) へ伸びる。"""
    m = sm.Mesh("SM_FD_WalkerThigh")
    m.add("FD_WK_Pants", *fg.ellipsoid((0.0, 0.0, 0.0), (0.088, 0.084, 0.085)))
    fg.limb(m, (0.0, 0.0, 0.0), (0.0, 0.0, -KNEE_DROP + 0.01), 0.084, 0.06, "FD_WK_Pants", n=18)
    return m


def shin():
    """すねと靴。原点が膝で、足の裏は -SHIN_DROP。"""
    m = sm.Mesh("SM_FD_WalkerShin")
    sole = -SHIN_DROP
    ankle = np.array([0.0, 0.0, sole + 0.085])
    fg.limb(m, (0.0, 0.0, 0.0), ankle + [0, 0, 0.02], 0.058, 0.049, "FD_WK_Pants", n=18, joint=0.06)
    # 靴: かかとからつま先へ。底は足の裏の高さで平ら
    m.add("FD_WK_Shoe", *sm.cylinder(ankle + [0, 0, 0.03], ankle - [0, 0, 0.04], 0.05, 0.052, n=16))
    xs = [-0.065, -0.02, 0.05, 0.12, 0.155]
    hs = [0.095, 0.10, 0.08, 0.065, 0.05]
    path = [(x, 0.0, sole + h / 2) for x, h in zip(xs, hs)]
    m.add("FD_WK_Shoe", *fg.loft(path, [0.09, 0.10, 0.105, 0.095, 0.07], hs, n=18, exponent=2.6))
    return m


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for mesh in (body(), upper_arm(), forearm(), thigh(), shin()):
        tris = sm.write_gltf(mesh, os.path.join(OUT_DIR, f"{mesh.name}.gltf"))
        lo, hi = mesh.bounds()
        print(f"  {mesh.name}.gltf: 三角形 {tris}、大きさ {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f} x {hi[2] - lo[2]:.2f} m"
              f" (Z {lo[2]:.2f}..{hi[2]:.2f})")


if __name__ == "__main__":
    main()
