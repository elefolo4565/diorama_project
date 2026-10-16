"""植物の追加の受け口。このフォルダの植物を集めて、build_scenery.py と check.py に渡す。植物の置き方は 2 通り:

1. コード: <種類>.py (1 種類 1 ファイル)。形と絵を Python で作る (見本 yamamomo.py)
2. ファイル: <種類>/plant.json と、Blender などで作った .glb、葉と樹皮の PNG (書き方はリポジトリ直下の AGENTS.md)。
   .glb は読み込んで、コードで作った形と同じ扱いにする (書き出し・配置・UE への取り込みは同じ道を通る)

コードの各ファイルが定義するもの (書き方は AGENTS.md と yamamomo.py を参照):
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
import json
import os
import re
import struct

import numpy as np

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
    """コードの植物 (<種類>.py)。"""
    return sorted(f[:-3] for f in os.listdir(HERE)
                  if f.endswith(".py") and not f.startswith("_") and f != "check.py")


def folder_names():
    """ファイルの植物 (<種類>/plant.json)。"""
    return sorted(d for d in os.listdir(HERE) if os.path.isfile(os.path.join(HERE, d, "plant.json")))


def all_names():
    return module_names() + folder_names()


# ---------------------------------------------------------------- .glb の読み込み
GLB_MAGIC = 0x46546C67
COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path):
    """(glTF の JSON, バイナリ) を返す。"""
    data = open(path, "rb").read()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError(f"{os.path.basename(path)} は glTF 2.0 の .glb ではありません")
    doc, binary, pos = None, b"", 12
    while pos < length:
        n, kind = struct.unpack_from("<II", data, pos)
        chunk = data[pos + 8:pos + 8 + n]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        pos += 8 + n
    if doc is None:
        raise ValueError(f"{os.path.basename(path)} に JSON がありません")
    return doc, binary


def accessor(doc, binary, i):
    a = doc["accessors"][i]
    view = doc["bufferViews"][a["bufferView"]]
    dtype, k = np.dtype(COMPONENT[a["componentType"]]), COUNT[a["type"]]
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * k)
    raw = np.frombuffer(binary, np.uint8, count=stride * (a["count"] - 1) + dtype.itemsize * k, offset=start)
    out = np.lib.stride_tricks.as_strided(raw, (a["count"], dtype.itemsize * k), (stride, 1)).copy()
    arr = out.view(dtype).reshape(a["count"], k).astype(np.float64)
    if a.get("normalized"):
        arr /= np.iinfo(dtype).max
    return arr


def glb_mesh(path, name):
    """.glb を scenery_meshes.Mesh にする (glTF の Y 上を UE の Z 上へ)。プリミティブごとにマテリアル名で分ける。"""
    doc, binary = read_glb(path)
    mesh = sm.Mesh(name)
    mats = doc.get("materials", [])
    for gm in doc.get("meshes", []):
        for prim in gm["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            att = prim["attributes"]
            v = accessor(doc, binary, att["POSITION"])
            n = accessor(doc, binary, att["NORMAL"]) if "NORMAL" in att else np.tile([0.0, 1.0, 0.0], (len(v), 1))
            uv = accessor(doc, binary, att["TEXCOORD_0"]) if "TEXCOORD_0" in att else np.zeros((len(v), 2))
            col = accessor(doc, binary, att["COLOR_0"])[:, :3] if "COLOR_0" in att else np.ones((len(v), 3))
            f = (accessor(doc, binary, prim["indices"]).astype(int).reshape(-1, 3) if "indices" in prim
                 else np.arange(len(v)).reshape(-1, 3))
            mat = mats[prim["material"]]["name"] if "material" in prim else "(マテリアルなし)"
            mesh.add_cards(mat, sm.to_gltf_space(v), f, sm.to_gltf_space(n), uv, col)
    return mesh


def glb_material(doc_mat):
    """glTF のマテリアルを scenery_meshes.MATERIALS の書き方にする (色と粗さだけ。絵は plant.json の leaves / barks)。"""
    pbr = doc_mat.get("pbrMetallicRoughness", {})
    rgba = pbr.get("baseColorFactor", [1, 1, 1, 1])
    return dict(color=tuple(rgba[:3]), roughness=pbr.get("roughnessFactor", 0.8), metallic=pbr.get("metallicFactor", 0.0))


def load_folder(name):
    """<種類>/plant.json を、コードの植物と同じ (MATERIALS, LEAVES, BARKS, PLANTS) の形にする。"""
    folder = os.path.join(HERE, name)
    with open(os.path.join(folder, "plant.json"), encoding="utf-8") as f:
        spec = json.load(f)
    leaves = {m: (png, _copier(os.path.join(folder, png))) for m, png in spec.get("leaves", {}).items()}
    barks = {m: (c, nrm, _copier2(os.path.join(folder, c), os.path.join(folder, nrm)))
             for m, (c, nrm) in spec.get("barks", {}).items()}
    materials, plants = {}, {}
    for mesh_name, m in spec["meshes"].items():
        path = os.path.join(folder, m["file"])
        doc, _ = read_glb(path)
        for dm in doc.get("materials", []):
            mat = dm.get("name", "")
            if mat in leaves:
                materials[mat] = dict(color=(1, 1, 1), roughness=0.6, texture=leaves[mat][0], alpha=True)
            elif mat in barks:
                materials[mat] = dict(color=(1, 1, 1), roughness=0.9, texture=barks[mat][0], normal=barks[mat][1])
            elif mat not in sm.MATERIALS:  # 既存のマテリアル (FD_Bark など) はそのまま使う
                materials[mat] = glb_material(dm)
        plants[mesh_name] = dict(make=(lambda p=path, n=mesh_name: glb_mesh(p, n)), file=path,
                                 **{k: m[k] for k in ("height_m", "habitat", "share", "seasons") if k in m})
        if "habitat" in plants[mesh_name]:
            plants[mesh_name]["habitat"] = tuple(plants[mesh_name]["habitat"])
    return materials, leaves, barks, plants, spec


def _copier(src):
    def draw(path):
        with open(src, "rb") as f, open(path, "wb") as g:
            g.write(f.read())
    return draw


def _copier2(src_c, src_n):
    def draw(path_c, path_n):
        _copier(src_c)(path_c)
        _copier(src_n)(path_n)
    return draw


def load(names=None):
    """植物のファイルを読み込み、マテリアルを scenery_meshes.MATERIALS に足して、
    (PLANTS をまとめた dict, LEAVES, BARKS, {メッシュ名: ファイル名}) を返す。"""
    plants, leaves, barks, owner = {}, {}, {}, {}
    for name in names or all_names():
        if name in folder_names():
            mats, lv, bk, pl, _ = load_folder(name)
        else:
            mod = importlib.import_module(f"plants.{name}")
            mats, lv, bk, pl = (getattr(mod, "MATERIALS", {}), getattr(mod, "LEAVES", {}), getattr(mod, "BARKS", {}),
                                mod.PLANTS)
        for mat, spec in mats.items():
            if mat in sm.MATERIALS and sm.MATERIALS[mat] != spec:
                raise ValueError(f"plants/{name}: マテリアル {mat} は別の値ですでにあります")
            sm.MATERIALS[mat] = spec
        leaves.update(lv)
        barks.update(bk)
        for mesh, spec in pl.items():
            if mesh in plants:
                raise ValueError(f"plants/{name}: {mesh} は plants/{owner[mesh]} にもあります")
            plants[mesh] = spec
            owner[mesh] = name
    return plants, leaves, barks, owner
