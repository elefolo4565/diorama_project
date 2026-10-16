"""plants/ の植物を作って調べ、確認用の画像を描く (UE は使わない)。PR を出す前に必ず実行する。

使い方 (tools/map_kit/terrain で):
    python plants/check.py              plants/ のすべての種類
    python plants/check.py yamamomo     plants/yamamomo.py (コード) か plants/yamamomo/plant.json (ファイル) だけ

出力 (out/plants/):
    <メッシュ名>.gltf, 葉と樹皮の絵 (.png)   UE に取り込むものと同じ
    <種類>_preview.png                        各メッシュの正面・横・真上と、葉の絵 (PR の説明に貼る)
調べること: (ファイルの植物は) plant.json と .glb の中身、名前の決まり、マテリアルと絵がそろっているか、三角形の数、大きさと原点、葉の絵の透過、
            同じ乱数で同じ形になるか。だめな所があれば一覧を出して終わりの値 1 で終わる。
"""

import hashlib
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bark  # noqa: E402
import foliage as fo  # noqa: E402
import scenery_meshes as sm  # noqa: E402

BUILTIN_MATERIALS = set(sm.MATERIALS)
BUILTIN_LEAF_TEXTURES = {k: v["texture"] for k, v in fo.LEAF_KINDS.items()}

import plants  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "plants")
TRIS_TREE = (2000, 25000)     # 高さ 3m 以上
TRIS_SMALL = (100, 4000)      # 低木・草花・シダ
HEIGHT_TOLERANCE = 0.3        # 形の高さと height_m の差 (割合)
TEXTURE_SIZE = 1024
ALPHA_CLIP = 0.4              # UE の葉のマテリアルと同じ (FOLIAGE_CLIP)
VIEW_PX = 360
SUN = np.array([0.45, -0.35, 0.82]) / np.linalg.norm([0.45, -0.35, 0.82])
SKY = (208, 222, 236)


# ---------------------------------------------------------------- 描画 (簡単なソフトウェアのラスタライザ)
def _srgb(linear):
    return tuple(int(255 * min(1.0, max(0.0, c)) ** (1 / 2.2)) for c in linear)


def _triangles(mesh, textures):
    """(頂点 (T,3,3), 法線 (T,3,3), UV (T,3,2), 明るさ (T,3), 絵 or None, 色 (3,)) のリストを返す。"""
    out = []
    for mat, v, f in mesh.parts:
        f = np.asarray(f)
        tv = v[f]
        n = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        out.append((tv, np.repeat(n[:, None], 3, 1), np.zeros((len(f), 3, 2)), np.ones((len(f), 3)), None,
                    np.array(_srgb(sm.MATERIALS[mat]["color"]), float)))
    for mat, v, f, nrm, uv, shade, *_ in mesh.cards:
        f = np.unique(np.sort(np.asarray(f), 1), axis=0)  # 表裏 2 枚の板は 1 枚だけ描く
        sh = shade if shade.ndim == 1 else shade.mean(1)
        spec = sm.MATERIALS[mat]
        tex = textures.get(spec.get("texture"))
        out.append((v[f], nrm[f], uv[f], sh[f], tex, np.array(_srgb(spec["color"]), float)))
    return out


def render(mesh, textures, view):
    """view = "front" (南から), "side" (東から), "top" (真上から)。"""
    lo, hi = mesh.bounds()
    axes = {"front": (0, 2, 1), "side": (1, 2, 0), "top": (0, 1, 2)}[view]
    sign_depth = {"front": 1.0, "side": -1.0, "top": -1.0}[view]
    a, b, d = axes
    span = max(hi[a] - lo[a], hi[b] - lo[b]) * 1.08
    ca, cb = (hi[a] + lo[a]) / 2, (hi[b] + lo[b]) / 2
    W = VIEW_PX
    k = W / span
    img = np.zeros((W, W, 3)) + SKY
    depth = np.full((W, W), np.inf)
    for tv, tn, tuv, tsh, tex, col in _triangles(mesh, textures):
        px = (tv[:, :, a] - ca) * k + W / 2
        py = W / 2 - (tv[:, :, b] - cb) * k
        pz = tv[:, :, d] * sign_depth
        for i in range(len(tv)):
            x, y = px[i], py[i]
            x0, x1 = max(int(x.min()), 0), min(int(x.max()) + 1, W - 1)
            y0, y1 = max(int(y.min()), 0), min(int(y.max()) + 1, W - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
            if abs(den) < 1e-9:
                continue
            w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
            w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            z = w0 * pz[i, 0] + w1 * pz[i, 1] + w2 * pz[i, 2]
            region = depth[y0:y1 + 1, x0:x1 + 1]
            inside &= z < region
            if tex is not None:
                u = w0 * tuv[i, 0, 0] + w1 * tuv[i, 1, 0] + w2 * tuv[i, 2, 0]
                v = w0 * tuv[i, 0, 1] + w1 * tuv[i, 1, 1] + w2 * tuv[i, 2, 1]
                th, tw = tex.shape[:2]
                tu = np.clip((u % 1.0) * tw, 0, tw - 1).astype(int)
                tvv = np.clip((v % 1.0) * th, 0, th - 1).astype(int)
                texel = tex[tvv, tu]
                if texel.shape[-1] == 4:
                    inside &= texel[..., 3] >= ALPHA_CLIP * 255
                rgb = texel[..., :3].astype(float) * (col / 255)
            else:
                rgb = np.broadcast_to(col, inside.shape + (3,))
            if not inside.any():
                continue
            n = tn[i].mean(0)
            lit = 0.35 + 0.75 * max(float(n @ SUN), 0.0)
            sh = w0 * tsh[i, 0] + w1 * tsh[i, 1] + w2 * tsh[i, 2]
            shade = (lit * (0.35 + 0.65 * sh))[..., None]
            region[inside] = z[inside]
            img[y0:y1 + 1, x0:x1 + 1][inside] = np.clip(rgb * shade, 0, 255)[inside]
    im = Image.fromarray(img.astype(np.uint8))
    ImageDraw.Draw(im).text((6, 4), f"{view}  {span:.1f} m", fill=(40, 40, 40))
    return im


# ---------------------------------------------------------------- 調べる
GLB_MAX_MB = 8.0
PLAIN_NAME = plants.re.compile(r"FD_[A-Z][A-Za-z0-9]*")


def check_folder(name):
    """ファイルの植物: plant.json と .glb の決まり。"""
    errs = []
    folder = os.path.join(plants.HERE, name)
    try:
        mats, leaves, barks, specs, spec = plants.load_folder(name)
    except Exception as e:  # noqa: BLE001
        return [f"{name}/plant.json: 読み込めません: {e}"]
    for key in ("name_ja", "latin", "meshes"):
        if key not in spec:
            errs.append(f"{name}/plant.json: {key} がありません")
    for mat, (png, _) in leaves.items():
        if not plants.LEAF_NAME.fullmatch(mat):
            errs.append(f"{mat}: 葉・花のマテリアル名は FD_Leaf_<種類> / FD_Flower_<種類> にする")
        if not os.path.isfile(os.path.join(folder, png)):
            errs.append(f"{name}/{png} がありません")
    for mat, (c, n, _) in barks.items():
        if not plants.BARK_NAME.fullmatch(mat):
            errs.append(f"{mat}: 樹皮のマテリアル名は FD_Bark<種類> にする")
        if (c, n) != (f"T_{mat}_D.png", f"T_{mat}_N.png"):
            errs.append(f"{mat}: 樹皮の絵の名前は T_{mat}_D.png と T_{mat}_N.png にする")
        for f in (c, n):
            if not os.path.isfile(os.path.join(folder, f)):
                errs.append(f"{name}/{f} がありません")
    for mat in mats:
        if mat in BUILTIN_MATERIALS and mat not in leaves and mat not in barks:
            continue
        if mat in BUILTIN_MATERIALS:
            errs.append(f"{mat}: 既存のマテリアルと同じ名前です (既存のものを使うなら leaves / barks に書かない)")
        elif mat not in leaves and mat not in barks and not PLAIN_NAME.fullmatch(mat):
            errs.append(f"{mat}: マテリアル名は FD_<名前> にする (Blender の Material.001 などのままにしない)")
    for mesh_name, m in spec.get("meshes", {}).items():
        path = os.path.join(folder, m.get("file", ""))
        if m.get("file") != f"{mesh_name}.glb":
            errs.append(f"{mesh_name}: ファイル名は {mesh_name}.glb にする")
        if not os.path.isfile(path):
            continue
        if os.path.getsize(path) > GLB_MAX_MB * 1e6:
            errs.append(f"{m['file']}: {os.path.getsize(path) / 1e6:.1f} MB (上限 {GLB_MAX_MB:.0f} MB)")
        doc, _ = plants.read_glb(path)
        meshes = doc.get("meshes", [])
        if len(meshes) != 1 or meshes[0].get("name") != mesh_name:
            errs.append(f"{m['file']}: メッシュは 1 つにまとめ、名前を {mesh_name} にする ({[x.get('name') for x in meshes]})")
        if doc.get("images"):
            errs.append(f"{m['file']}: 絵を .glb に入れない (Blender の書き出しで画像を「なし」にし、PNG は別に置く)")
        if doc.get("animations") or doc.get("skins"):
            errs.append(f"{m['file']}: アニメーションと骨は入れない")
        for gm in meshes:
            for prim in gm.get("primitives", []):
                if "material" not in prim:
                    errs.append(f"{m['file']}: マテリアルの無い面があります")
                if "NORMAL" not in prim.get("attributes", {}):
                    errs.append(f"{m['file']}: 法線がありません")
                if "TEXCOORD_0" not in prim.get("attributes", {}):
                    mat = doc["materials"][prim["material"]]["name"] if "material" in prim else ""
                    if mat in leaves or mat in barks:
                        errs.append(f"{m['file']}: {mat} に UV がありません")
        nodes = doc.get("nodes", [])
        for nd in nodes:
            if any(k in nd for k in ("rotation", "scale", "matrix")) or any(abs(t) > 1e-4 for t in nd.get("translation", [])):
                errs.append(f"{m['file']}: ノード {nd.get('name')} に移動・回転・拡大が残っています (Blender で Apply してから書き出す)")
                break
    return errs


def check_module(name):
    errors, rows = [], []
    is_folder = name in plants.folder_names()
    if is_folder:
        errors += check_folder(name)
        if errors:
            return errors, []
    try:
        specs, leaves, barks, _ = plants.load([name])
    except Exception as e:  # noqa: BLE001
        return [f"{name}: 読み込めません: {e}"], []
    mod = None if is_folder else sys.modules[f"plants.{name}"]
    for mat in getattr(mod, "MATERIALS", {}):
        if mat in BUILTIN_MATERIALS:
            errors.append(f"{mat}: 既存のマテリアルと同じ名前です (新しい名前にする)")
        elif not (plants.LEAF_NAME.fullmatch(mat) or plants.BARK_NAME.fullmatch(mat)):
            errors.append(f"{mat}: マテリアル名は FD_Leaf_<種類> / FD_Flower_<種類> / FD_Bark<種類> にする")
    os.makedirs(OUT, exist_ok=True)
    textures = {}
    for mat, (fname, draw) in leaves.items():
        if fname != f"T_{mat}.png":
            errors.append(f"{mat}: 絵の名前は T_{mat}.png にする ({fname})")
        path = os.path.join(OUT, fname)
        draw(path)
        errors += check_leaf_png(path)
        textures[fname] = np.asarray(Image.open(path).convert("RGBA"))
    for mat, (color, normal, draw) in barks.items():
        draw(os.path.join(OUT, color), os.path.join(OUT, normal))
        textures[color] = np.asarray(Image.open(os.path.join(OUT, color)).convert("RGBA"))
    for mesh_name, spec in specs.items():
        e, row = check_plant(mesh_name, spec, leaves, barks, textures)
        errors += e
        if row:
            rows.append(row)
    return errors, rows


def check_leaf_png(path):
    errs = []
    im = Image.open(path)
    if im.size != (TEXTURE_SIZE, TEXTURE_SIZE) or im.mode != "RGBA":
        errs.append(f"{os.path.basename(path)}: {TEXTURE_SIZE}x{TEXTURE_SIZE} の RGBA にする ({im.size}, {im.mode})")
        return errs
    a = np.asarray(im)[:, :, 3]
    cover = float((a >= ALPHA_CLIP * 255).mean())
    if not 0.1 <= cover <= 0.9:
        errs.append(f"{os.path.basename(path)}: 葉の所の割合 {cover:.0%} (10〜90% にする)")
    if (a == 0).mean() < 0.05:
        errs.append(f"{os.path.basename(path)}: 透明 (アルファ 0) の所がほとんどありません")
    return errs


def check_plant(name, spec, leaves, barks, textures):
    errs = []
    if not plants.MESH_NAME.fullmatch(name):
        errs.append(f"{name}: メッシュ名は SM_FD_<種類>_<A/B/C> にする")
    for key in ("make", "height_m", "habitat", "share"):
        if key not in spec:
            errs.append(f"{name}: PLANTS に {key} がありません")
    if errs:
        return errs, None
    bad = [h for h in spec["habitat"] if h not in plants.HABITATS]
    if bad or not spec["habitat"]:
        errs.append(f"{name}: habitat は {plants.HABITATS} から選ぶ ({bad})")
    if not 0 < spec["share"] <= 1:
        errs.append(f"{name}: share は 0 より大きく 1 以下")
    if not 1 <= spec.get("seasons", plants.ALL_SEASONS) <= 15:
        errs.append(f"{name}: seasons は 1〜15 (1 春, 2 夏, 4 秋, 8 冬)")
    mesh = spec["make"]()
    if not mesh.parts and not mesh.cards:
        return errs + [f"{name}: 形が空です"], None
    used = {p[0] for p in mesh.parts} | {c[0] for c in mesh.cards}
    for mat in sorted(used):
        if mat not in sm.MATERIALS:
            errs.append(f"{name}: マテリアル {mat} が MATERIALS にありません")
            continue
        tex = sm.MATERIALS[mat].get("texture")
        if mat.startswith(("FD_Leaf_", "FD_Flower_")) and mat not in leaves and mat not in BUILTIN_LEAF_TEXTURES:
            errs.append(f"{name}: {mat} の絵が LEAVES にありません")
        if mat in bark.BARK_KINDS and tex not in textures:  # 既存の樹皮 (FD_Bark など) は確認用に描く
            c, n = bark.texture_names(mat)
            bark.bark_textures(mat, os.path.join(OUT, c), os.path.join(OUT, n))
            textures[c] = np.asarray(Image.open(os.path.join(OUT, c)).convert("RGBA"))
        elif mat in BUILTIN_LEAF_TEXTURES and tex not in textures:
            fo.leaf_texture(mat, os.path.join(OUT, tex))
            textures[tex] = np.asarray(Image.open(os.path.join(OUT, tex)).convert("RGBA"))
        elif tex and tex not in textures and mat not in barks:
            errs.append(f"{name}: {mat} の絵 {tex} を作る所がありません")
    if errs:
        return errs, None
    path = os.path.join(OUT, f"{name}.gltf")
    tris = sm.write_gltf(mesh, path)
    digest = hashlib.sha1(open(path, "rb").read()).hexdigest()
    sm.write_gltf(spec["make"](), path)
    if hashlib.sha1(open(path, "rb").read()).hexdigest() != digest:
        errs.append(f"{name}: 2 回作ると形が変わります (乱数は scenery_meshes.Rng(seed) を使う)")
    lo, hi = mesh.bounds()
    h = spec["height_m"]
    lo_t, hi_t = TRIS_TREE if h >= 3 else TRIS_SMALL
    if not lo_t <= tris <= hi_t:
        errs.append(f"{name}: 三角形 {tris} (高さ {h}m なら {lo_t}〜{hi_t})")
    if not -0.5 <= lo[2] <= 0.3:
        errs.append(f"{name}: いちばん下が {lo[2]:.2f}m (原点は根元の地面。-0.5〜0.3m にする)")
    if abs(hi[2] - h) > h * HEIGHT_TOLERANCE:
        errs.append(f"{name}: 高さ {hi[2]:.1f}m が height_m {h}m と合いません")
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    if math.hypot(cx, cy) > max(0.25 * h, 0.3):
        errs.append(f"{name}: 形の中心が原点から {math.hypot(cx, cy):.1f}m ずれています")
    size = f"{hi[0] - lo[0]:.1f} x {hi[1] - lo[1]:.1f} x {hi[2] - lo[2]:.1f} m"
    print(f"  {name}: 三角形 {tris}、大きさ {size}、habitat {','.join(spec['habitat'])}、share {spec['share']}")
    views = [render(mesh, textures, v) for v in ("front", "side", "top")]
    return errs, (name, f"{name}  tris {tris}  {size}", views)


def write_preview(name, rows, leaf_pngs):
    W = VIEW_PX
    leaf_w = W if leaf_pngs else 0
    sheet = Image.new("RGB", (W * 3 + leaf_w, max(1, len(rows)) * (W + 20)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (_, label, views) in enumerate(rows):
        y = i * (W + 20)
        d.text((6, y + 4), label, fill=(0, 0, 0))
        for j, im in enumerate(views):
            sheet.paste(im, (j * W, y + 20))
    for i, p in enumerate(leaf_pngs[:len(rows) or 1]):
        leaf = Image.open(p).convert("RGBA").resize((W, W))
        bg = Image.new("RGBA", (W, W), (240, 240, 240, 255))
        sheet.paste(Image.alpha_composite(bg, leaf).convert("RGB"), (W * 3, i * (W + 20) + 20))
    path = os.path.join(OUT, f"{name}_preview.png")
    sheet.save(path)
    return path


def main():
    names = sys.argv[1:] or plants.all_names()
    unknown = [n for n in names if n not in plants.all_names()]
    if unknown:
        sys.exit(f"plants/ に {unknown} がありません")
    all_errors = []
    for name in names:
        print(f"{name}:")
        errors, rows = check_module(name)
        if name in plants.folder_names():
            leaf_pngs = [os.path.join(OUT, f) for f in plants.load_folder(name)[4].get("leaves", {}).values()]
        else:
            mod = sys.modules.get(f"plants.{name}")
            leaf_pngs = [os.path.join(OUT, f) for f, _ in getattr(mod, "LEAVES", {}).values()] if mod else []
        if rows:
            print(f"  確認用の画像: {write_preview(name, rows, leaf_pngs)}")
        all_errors += errors
    if all_errors:
        print("\nだめな所:")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()
