"""植物の追加の受け口。このフォルダの <種類>.py (1 種類 1 ファイル) を集めて、build_scenery.py と check.py に渡す。

各ファイルが定義するもの (書き方は AGENTS.md と yamamomo.py を参照):
    PLANTS     {メッシュ名: dict(make=..., height_m=..., habitat=(...), share=..., seasons=...)}
    MATERIALS  {マテリアル名: scenery_meshes.MATERIALS と同じ書き方}            (省略可)
    LEAVES     {マテリアル名: (PNG の名前, draw(path))}  葉・花の絵                (省略可)
    BARKS      {マテリアル名: (色の PNG, 法線の PNG, draw(color_path, normal_path))} 樹皮の絵 (省略可)

habitat (置く所):
    木を入れ替える: "coast" 海岸 (海から 100m 以内の低い所)、"forest" 森、"ridge" 標高 60m 以上の森、
                    "farm" 田畑のあぜ、"grassland" 草原
                    -> その所の木のうち share の割合をこの種類にする
    木に足す:       "understory" 森の木の足もと -> 森の木 1 本ごとに share の確率で 1 株足す
"""

import importlib
import os
import re

import scenery_meshes as sm

HERE = os.path.dirname(os.path.abspath(__file__))
REPLACE_HABITATS = ("coast", "forest", "ridge", "farm", "grassland")
ADD_HABITATS = ("understory",)
HABITATS = REPLACE_HABITATS + ADD_HABITATS
ALL_SEASONS = 15

MESH_NAME = re.compile(r"SM_FD_[A-Z][A-Za-z0-9]*(_[A-Z0-9][A-Za-z0-9]*)*")
LEAF_NAME = re.compile(r"FD_(Leaf|Flower)_[A-Z][A-Za-z0-9]*")
BARK_NAME = re.compile(r"FD_Bark[A-Z][A-Za-z0-9]*")


def module_names():
    return sorted(f[:-3] for f in os.listdir(HERE)
                  if f.endswith(".py") and not f.startswith("_") and f != "check.py")


def load(names=None):
    """植物のファイルを読み込み、マテリアルを scenery_meshes.MATERIALS に足して、
    (PLANTS をまとめた dict, LEAVES, BARKS, {メッシュ名: ファイル名}) を返す。"""
    plants, leaves, barks, owner = {}, {}, {}, {}
    for name in names or module_names():
        mod = importlib.import_module(f"plants.{name}")
        for mat, spec in getattr(mod, "MATERIALS", {}).items():
            if mat in sm.MATERIALS and sm.MATERIALS[mat] != spec:
                raise ValueError(f"plants/{name}.py: マテリアル {mat} は別の値ですでにあります")
            sm.MATERIALS[mat] = spec
        leaves.update(getattr(mod, "LEAVES", {}))
        barks.update(getattr(mod, "BARKS", {}))
        for mesh, spec in mod.PLANTS.items():
            if mesh in plants:
                raise ValueError(f"plants/{name}.py: {mesh} は plants/{owner[mesh]}.py にもあります")
            plants[mesh] = spec
            owner[mesh] = name
    return plants, leaves, barks, owner
