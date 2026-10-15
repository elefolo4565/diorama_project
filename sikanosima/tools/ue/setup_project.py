"""UE プロジェクトの初期アセットとレベルを作る (Unreal Editor の Python で実行)。

作るもの
- /Game/FukuokaDrive/Materials/M_Landscape   Road レイヤーを持つ仮のランドスケープマテリアル (道路以外は草)。草地にはカメラの近くだけ立体の草が生える
- /Game/FukuokaDrive/Grass                    草の株のメッシュ、草のマテリアル、ランドスケープグラス (LGT_FD_Grass)、地面の模様の絵
                                              (tools/terrain/build_grass.py の出力を取り込む)
- /Game/FukuokaDrive/Materials/M_Sea         遠景 (WaterZone の外) の海面と、Water プラグインが使えないときの仮の海面
- /Game/FukuokaDrive/Water/FD_OceanWaves      穏やかな夏の玄界灘の波 (Water プラグインの既定の波を複製して小さくしたもの)
- /Game/FukuokaDrive/Water/MI_FD_Ocean        海の色 (浅瀬はエメラルド、沖は深い青) を変えた Ocean のマテリアル
- /Game/FukuokaDrive/Scenery                  夫婦岩・しめ縄・鳥居・ガードレール・木・道路の付属物 (区画線・側溝・電柱・標識) のメッシュ (tools/terrain/build_scenery.py の glTF を取り込む)
- /Game/FukuokaDrive/FarTerrain               ランドスケープの外 (110km 四方) の遠景の地形 (tools/terrain/build_far_terrain.py の glTF を取り込む)
- /Game/FukuokaDrive/Materials/M_FarTerrain  遠景の地形の色 (頂点カラー)
- /Game/FukuokaDrive/Vehicle                  クロスカブ110 とライダーのメッシュ (tools/vehicle/build_crosscub.py の glTF を取り込む)、
                                              車体色とライトのレンズのマテリアル
- /Game/FukuokaDrive/UI/T_FD_Minimap         ミニマップの地図 (tools/terrain/build_minimap.py の minimap.png を取り込む)
- /Game/FukuokaDrive/Maps/Futamigaura         太陽 (糸島の緯度経度・夏至の真昼)、霧、雲、空気のかすみ、露出と画づくり、
                                              時刻の切り替え (FDTimeOfDay)、海 (Water プラグインの Ocean、海面 Z=0)、遠景の地形、
                                              夫婦岩と鳥居、ガードレール、木 (FDInstances)、目印、PlayerStart、
                                              ファストトラベルの行き先 (FDTravelPoint)、星空の空の球、防犯灯の光 (FDNightLights)
- /Game/FukuokaDrive/Materials/MPC_FD_Night  夜の値 (星空の回転と明るさ、防犯灯の点き具合)。プレイ中は FDTimeOfDay が書き換える
- /Game/FukuokaDrive/Materials/M_FD_Sky      空の球のマテリアル (大気・太陽と月の円盤・星・天の川・街明かり)
- /Game/FukuokaDrive/Materials/M_FD_LampGlow 防犯灯の光る面 (夜だけ光る)
- /Game/FukuokaDrive/Materials/M_FD_BuildingWall / M_FD_BuildingRoof  建物の壁 (窓を描き、夜は時刻に合わせて窓が灯る) と屋根

プレイ中の太陽・露出・霧・色は FDTimeOfDay が時刻に合わせて上書きする (T/G で時間を進める・戻す、1-4 で朝・昼・夕・夜、Y で季節)。
ここでの値はエディタで見たときの (SOLAR_TIME の) 見た目と、FDTimeOfDay が使う霧の濃さの基準になる。

ランドスケープ本体は Python から作れないため、このスクリプトの後にエディタで取り込む
(手順は tools/ue/README.md)。

実行方法 (どちらでも可):
- エディタ: ツール → Python スクリプトを実行 → このファイル
- コマンドライン:
  UnrealEditor-Cmd.exe <path>/Sikanosima.uproject -run=pythonscript -script="<path>/tools/ue/setup_project.py"

何度実行してもよい。作り方 (このファイルのコードと定数、入力の glTF / JSON) が前回から変わったものだけを作り直して保存し、
変わっていないアセットとレベルには触らない (前回の作り方は Content/FukuokaDrive/SetupState.json に残る)。
マテリアルは同じアセットのまま中身を組み直し、レベルは自動配置物だけ置き直す。すべて作り直したいときは FORCE_ALL = True。
"""

import hashlib
import importlib
import json
import os
import re
import sys
import types

import unreal

PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# 作るコース (tools/terrain/course.txt、無ければ糸島一周)。名前・レベル・タイルの決め方は tools/terrain/course.py
sys.path.insert(0, os.path.join(PROJECT_DIR, "tools", "terrain"))
import course as course_config  # noqa: E402
importlib.reload(course_config)   # エディタの Python は前回の読み込みを覚えているので、読み直す
COURSE = course_config.Course()

# コースごとのアセット (遠景・ミニマップ) を分けるフォルダ。汎用化の前からある糸島は分けない (これまでと同じ場所)
COURSE_SUBDIR = "" if COURSE.name in course_config.LEGACY else f"/{COURSE.name}"

# 共通のアセット (木・草・花など) を作るタイル。コースのタイルがまだ無ければ最初の区間 (二見ヶ浦)
AREA = COURSE.base_tile() if COURSE.tiles_doc() else "futamigaura"
ROOT = "/Game/FukuokaDrive"
MAP_PATH = f"{ROOT}/Maps/Futamigaura"
MATERIAL_DIR = f"{ROOT}/Materials"
AUTO_TAG = "fd_auto"  # このスクリプトが置いたアクターの印

# 太陽と星の計算に使う緯度経度。糸島一周 (と最初の区間) は桜井二見ヶ浦 (夏至のころは夫婦岩の間に夕日が沈む)
LATITUDE, LONGITUDE = COURSE.sun if COURSE.tiles_doc() and COURSE.sun else (33.641, 130.196)
TIME_ZONE = 9.0
# SunSky の Year はインスタンスで変更できない (BP の既定値のまま)。太陽の位置への影響はほぼない
MONTH, DAY = 6, 21
# 日本時間 (夏時間なし)。プレイ開始時の時刻にもなる (FDTimeOfDay がここから時間を進める)。
# 12.0 なら太陽は南の高度約80°。夕日 (方位約296°、高度約3°) から始めたいときは 19.2
SOLAR_TIME = 12.0
# SunSky の北の向き (度)。UE の -Y を北にするには 270 (90 だと太陽が東南東に来る)
NORTH_OFFSET = 270.0
# True なら既存の M_Landscape の式を消して組み直す (アセットはそのままなので、ランドスケープの参照は切れない)
REBUILD_MATERIAL = True
# 海。海面は Z=0。WaterZone はエリア (約4km) を余裕をもって覆う広さにする (cm)
SEA_ZONE_EXTENT_CM = 800000.0
SEA_ZONE_RESOLUTION = 2048       # 海岸の判定に使うテクスチャの解像度 (8km / 2048 = 約4m)
# Ocean の水は「スプラインの外側」から Ocean Extents の端までに張られる (スプラインは島・陸の輪郭)。
# 以前はスプラインをエリア全体を囲む大きな四角にしていたため、水が外周のすき間にしか張られず、海が消えていた。
# 地形は削らないので、スプラインはエリア中心の陸地 (標高 6.8m 以上) に小さく置くだけにする
SEA_SPLINE_HALF_CM = 5000.0
# Ocean Extents の外は水が描かれないため、遠景用の板を WaterZone の外側に額縁状に並べる (水平線まで)。
# 水と重なっても水が上に見えるよう、海面より少し下に置く
SEA_FAR_HALF_CM = 3000000.0
SEA_FAR_Z_CM = -50.0
SEA_FALLBACK_SIZE_M = 20000.0    # Water プラグインが無いときに置く板の大きさ
WATER_DIR = f"{ROOT}/Water"
DEFAULT_WAVES_ASSET = "/Water/Waves/GerstnerWaves_Ocean"  # Ocean に既定で付く波 (見つからないときの予備)
# 波。海岸の道路は海面 +0.5m 以上なので、波の高さ (山の高さの合計) はそれより十分低くする
WAVE_MAX_HEIGHT_CM = 35.0
# 海が描かれない問題の切り分け用。False にすると、波なし / エンジン既定のマテリアルのまま (0775b80 と同じ状態) になる
OCEAN_USE_CUSTOM_WAVES = True
OCEAN_USE_CUSTOM_MATERIAL = False
WAVES = dict(NumWaves=16, MinWavelength=120.0, MaxWavelength=2400.0, MinAmplitude=1.0, MaxAmplitude=18.0,
             # 波の進む向き (UE の +X から +Y へ回した角度)。北西の沖から南東の浜へ寄せる = 45°
             WindAngleDeg=45.0, DirectionAngularSpreadDeg=70.0,
             SmallWaveSteepness=0.3, LargeWaveSteepness=0.15)
# 海の色 (Water_Material_Ocean の Absorption / Scattering) の上書き。None ならエンジン既定のまま。
# 既定は Absorption (10, 150, 350, a=8)、Scattering (1, 1, 1, a=0.5) で、単位は 1/m の係数ではない。
# 係数のつもりで小さな値 (0.42, 0.05, 0.035) を入れたら海が見えなくなったので、調整は既定値を基準に少しずつ行う
OCEAN_ABSORPTION = None
OCEAN_SCATTERING = None
# 砂浜。海面からの高さで色を決める (海底と波打ち際は濡れた砂、その上の浜は乾いた白っぽい砂)。
# 標高データでは海面 +2m より低い陸地はほぼすべて海から 150m 以内なので、高さだけで浜とみなせる。道路は砂より上に塗る
SAND_DRY_TOP_CM = 220.0     # これより低い所が砂浜
SAND_DRY_BLEND_CM = 60.0    # 草から砂へ変わる幅
SAND_WET_TOP_CM = 30.0      # これより低い所 (波が届く所と海底) は濡れた砂
SAND_WET_BLEND_CM = 50.0
SAND_DRY_COLOR = (0.62, 0.52, 0.36)   # 糸島の白っぽい砂 (リニア)
SAND_WET_COLOR = (0.30, 0.25, 0.18)
# 草地。黄緑の一色だと夕日や昼の強い光で一面黄色っぽく見えたので、暗めの緑を 2 色、大きなむらで混ぜる。
# さらに小さなむらで明るさを揺らし、急な斜面 (林の下の土や岩肌) は暗い土色にする
GRASS_COLOR = (0.040, 0.068, 0.024)        # 草地 (リニア)
GRASS_DARK_COLOR = (0.024, 0.044, 0.018)   # 林の縁や湿った草地
GRASS_MACRO_SCALE = 0.00015                # 大きなむら (Noise の Scale。値が小さいほど模様が大きい)
GRASS_DETAIL_SCALE = 0.003                 # 小さなむら
# 中くらい (十数 m) のむら。少し黄色がかった所 (乾いた草) と、みずみずしい緑の所をまだらに混ぜる。
# 黄色を強くすると夕日で草地全体が黄ばむので、混ぜる量は控えめにする
GRASS_PATCH_SCALE = 0.0006
GRASS_PATCH_DRY_COLOR = (0.058, 0.066, 0.026)
GRASS_PATCH_FRESH_COLOR = (0.034, 0.076, 0.022)
GRASS_PATCH_AMOUNT = 0.6
# 地面の細かい模様 (上から見た草の葉の絵と凹凸) を貼る大きさ (cm)。2 つの大きさで重ねて、繰り返しを目立たなくする
GROUND_TILE_CM = 250.0
GROUND_TILE_LARGE_CM = 1130.0
GROUND_NORMAL_STRENGTH = 0.7     # 地面の凹凸の強さ (0 で平ら)
SOIL_COLOR = (0.07, 0.052, 0.034)          # 急な斜面の土 (花こう岩が風化した真砂土の黄土色)
# 土と道路の細かい模様 (tools/terrain/build_grass.py の絵) を貼る大きさ (cm) と凹凸の強さ。
# 土は斜面に貼るので、横から (X と Y の 2 方向) と上からの 3 方向から投影して混ぜる (斜面で絵が伸びないように)
SOIL_TILE_CM = 300.0
SOIL_NORMAL_STRENGTH = 0.9
SOIL_PATCH_SCALE = 0.0008                  # 土の明るさの大きなむら
ROAD_COLOR = (0.05, 0.05, 0.055)
ASPHALT_TILE_CM = 150.0
ASPHALT_NORMAL_STRENGTH = 0.6
ASPHALT_PATCH_SCALE = 0.0012               # 道路の明るさの大きなむら (補修のあと・汚れ)
ASPHALT_ROUGHNESS = (0.85, 0.55)           # 黒い地と、砕石の明るい所の粗さ
SOIL_SLOPE_NZ = 0.82                       # 法線の上向き成分がこれより小さい (約 35° より急) と土になる
SOIL_SLOPE_BLEND = 0.10
# 空と画づくり
SKY_MIE_SCATTERING_SCALE = 0.004   # UE 既定。0.006 だと全体が白くかすみ、夕日の色が抜けた
SKY_AERIAL_PERSPECTIVE_SCALE = 1.5 # 遠くの山や島ほど青白くかすませる
# VolumetricFogScatteringDistribution は前方散乱の強さ。0.6 だと太陽のまわりが白く光り、夕日の橙が抜けた
FOG = dict(FogDensity=0.003, FogHeightFalloff=0.15, DirectionalInscatteringExponent=6.0,
           DirectionalInscatteringStartDistance=3000.0, EnableVolumetricFog=True,
           VolumetricFogScatteringDistribution=0.25, VolumetricFogExtinctionScale=0.4)
FOG_SUN_GLOW = (0.45, 0.18, 0.06)   # 太陽の方向の霧の色 (夕日の橙)。強すぎると画面全体が白っぽく黄ばむ
# 自動露出の範囲 (EV100)。太陽を見ても景色が真っ暗にならず、山陰でも白飛びしないように絞る
EXPOSURE_MIN_EV100 = 10.0
EXPOSURE_MAX_EV100 = 15.0  # 13.5 だと明るい景色で露出が頭打ちになり、白っぽく昼のように見えた

# 景観物 (tools/terrain/build_scenery.py の出力)
SCENERY_DIR = f"{ROOT}/Scenery"
REIMPORT_SCENERY = True   # False なら取り込み済みのメッシュをそのまま使う (置き直しだけ速く済ませたいとき)
SCENERY_NANITE = True     # 木は数万本並ぶので Nanite にする
# 木の葉 (tools/terrain/foliage.py の葉の板と葉の絵)。glTF の葉のマテリアル (名前が FD_Leaf_ で始まる) を、
# 葉用のマテリアル (絵の透明な所を切り抜き、薄い葉を光が透ける Two Sided Foliage) のインスタンスに差し替える
FOLIAGE_DIR = f"{SCENERY_DIR}/Foliage"
FOLIAGE_CLIP = 0.4               # 葉の絵の不透明度がこれより低い所を切り抜く
FOLIAGE_AO_MIN = 0.3             # 樹冠のいちばん奥の葉の明るさ (頂点の色 R が 0 の所)
FOLIAGE_INSTANCE_VARIATION = (0.8, 1.15)   # 木ごとの葉の明るさのばらつき
FOLIAGE_TRANSMISSION = 0.6       # 葉の裏へ透ける光の強さ (葉の色に対する倍率)
# 葉のつや。粗さ 0.55・スペキュラ 0.3 だと、日の当たる葉が白っぽくてかって見えたので、つやを抑える
FOLIAGE_ROUGHNESS = 0.85
FOLIAGE_SPECULAR = 0.12

# 草地の草 (tools/terrain/build_grass.py の出力)。ランドスケープグラスで、M_Landscape の草地 (道路・砂浜・急な斜面以外) に、
# カメラの近くだけ自動で生やす。density = 100 m2 あたりの株の数、cull = 消え始める距離と消える距離 (cm)、scale = 大きさのばらつき。
# 草は影を落とさない (数万株の影は重い。根元を暗くしてなじませる)。重いときは density を下げるか cull を縮める
GRASS_DIR = f"{ROOT}/Grass"
GRASS_TYPE_NAME = "LGT_FD_Grass"
GRASS_VARIETIES = (
    dict(mesh="SM_FD_GrassTuft", density=500.0, cull=(3500, 5000), scale=(0.75, 1.3)),
    dict(mesh="SM_FD_GrassTall", density=40.0, cull=(4000, 6000), scale=(0.8, 1.25)),
)
GRASS_ROOT_AO = 0.35          # 根元の明るさ (頂点の色 R が 0 の所)
GRASS_TIP_BRIGHT = 1.2        # 葉先の明るさ
GRASS_DRY_BLADES = 0.12       # 枯れた葉の割合
GRASS_DRY_BLADE_COLOR = (0.10, 0.085, 0.035)
GRASS_INSTANCE_VARIATION = (0.85, 1.15)
GRASS_TRANSMISSION = 0.5      # 葉の裏へ透ける光 (夕日の逆光で草が光る)
# 風。WIND_DIR の向き (北西の海から南東へ) に、葉先が WIND_CM ほどゆれる。ゆっくりした強弱 (突風) が草地を波のように渡る
WIND_DIR = (0.7, 0.7)
WIND_CM = 6.0
WIND_SPEED = 0.7              # 細かいゆれ (回/秒)
WIND_WAVE = 0.0006            # 細かいゆれの場所によるずれ (回/cm)
GUST_SPEED = 0.12             # 突風 (回/秒)
GUST_WAVE = 0.00008
GRASS_SINK_CM = 120.0         # 消える距離の手前で、草を地面に沈めて消す (ぱっと消えないように)

# 遠景の地形 (tools/terrain/build_far_terrain.py の出力)。取り込みに少し時間がかかるので、glTF が変わったときだけ取り込み直す
FAR_TERRAIN_DIR = f"{ROOT}/FarTerrain{COURSE_SUBDIR}"
FAR_TERRAIN_MESH = "SM_FD_FarTerrain"
FAR_TERRAIN_ROUGHNESS = 0.9
FAR_TERRAIN_SPECULAR = 0.3

# クロスカブ (tools/vehicle/build_crosscub.py の出力)。メッシュの名前は C++ の AFDBikePawn の既定値と同じ
VEHICLE_DIR = f"{ROOT}/Vehicle"
VEHICLE_MESHES = ("SM_CC_Body", "SM_CC_Steering", "SM_CC_Wheel", "SM_CC_Rider")
# 歩く人 (tools/vehicle/build_walker.py の出力)。名前は C++ の AFDWalkerCharacter の既定値と同じ。色は C++ が塗る
WALKER_MESHES = ("SM_FD_WalkerBody", "SM_FD_WalkerUpperArm", "SM_FD_WalkerForearm", "SM_FD_WalkerThigh", "SM_FD_WalkerShin")
VEHICLE_PAINT_DEFAULT = (0.80, 0.50, 0.02)   # 車体色の既定 (C++ の BodyColor が上書きする)
HEADLIGHT_LENS = dict(color=(1.0, 0.95, 0.85), intensity=60.0)
TAIL_LENS = dict(color=(1.0, 0.02, 0.01), intensity=8.0)   # ブレーキをかけると C++ が BrakeLightBoost 倍にする

DATA_DIR = os.path.join(PROJECT_DIR, "tools", "terrain", "out", AREA)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary


def log(msg):
    unreal.log(f"[setup_project] {msg}")


def set_props(obj, **props):
    """BP 変数は Python 名が環境で揺れるので、snake_case と元の名前の両方を試す。"""
    for name, value in props.items():
        for cand in (name, name[0].lower() + name[1:], "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")):
            try:
                obj.set_editor_property(cand, value)
                break
            except Exception:
                continue
        else:
            unreal.log_warning(f"[setup_project] {obj.get_name()} にプロパティ {name} を設定できませんでした")


# ---------------------------------------------------------------- 変わったものだけ作り直す
# アセットは中身が同じでも保存し直すとファイルが変わる (式や配置物の GUID が毎回変わる) ので、
# 「作り方」(関数のコードとそれが使う定数・引数・入力ファイルの中身) のハッシュを STATE_PATH に残し、
# 前回と同じならそのアセットには触らない。STATE_PATH は Content と一緒にコミットする
STATE_PATH = os.path.join(PROJECT_DIR, "Content", "FukuokaDrive", "SetupState.json")
FORCE_ALL = False   # True なら前回の記録を無視してすべて作り直す
_PLAIN = (bool, int, float, str, bytes, type(None), tuple, list, dict)


def _code_digest(h, code, skip, seen):
    h.update(code.co_code)
    h.update(repr(code.co_names).encode())
    for c in code.co_consts:
        if hasattr(c, "co_code"):
            _code_digest(h, c, skip, seen)
        elif isinstance(c, frozenset):
            h.update(repr(sorted(map(repr, c))).encode())  # 集合の順番は実行ごとに変わる
        else:
            h.update(repr(c).encode())
    g = globals()
    for name in code.co_names:
        if name in seen or name in skip or name not in g:
            continue
        seen.add(name)
        v = g[name]
        if callable(v) and getattr(v, "__globals__", None) is g:   # このファイルの関数はたどる
            h.update(name.encode())
            h.update(repr(v.__defaults__).encode())
            _code_digest(h, v.__code__, skip, seen)
        elif isinstance(v, str) and v.startswith(PROJECT_DIR):      # PC ごとに違うパスは相対にする
            h.update(f"{name}={os.path.relpath(v, PROJECT_DIR)!r}".encode())
        elif isinstance(v, _PLAIN):                                  # 定数
            h.update(f"{name}={v!r}".encode())


def _file_digest(h, path):
    h.update(os.path.basename(path).encode())
    if not os.path.exists(path):
        h.update(b"<none>")
        return
    with open(path, "rb") as f:
        h.update(f.read())
    root, ext = os.path.splitext(path)
    if ext == ".gltf" and os.path.exists(root + ".bin"):   # 外部バッファ
        _file_digest(h, root + ".bin")


def recipe(*parts, files=(), skip=()):
    """関数 (中で呼ぶこのファイルの関数と定数もたどる)・値・ファイルの中身から、作り方のハッシュを作る。"""
    h = hashlib.sha1()
    seen = set()
    for p in parts:
        if callable(p) and hasattr(p, "__code__"):
            h.update(p.__name__.encode())
            _code_digest(h, p.__code__, set(skip), seen)
        else:
            h.update(repr(p).encode())
    for path in files:
        _file_digest(h, path)
    return h.hexdigest()


class SetupState:
    def __init__(self):
        self.data = {}
        if os.path.exists(STATE_PATH):
            try:
                with open(STATE_PATH, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                unreal.log_warning(f"[setup_project] {STATE_PATH} を読めませんでした ({e})。すべて作り直します")
        self.changed = []

    def fresh(self, key, digest, *asset_paths):
        """前回と同じ作り方で、アセットもあるなら True (作り直さなくてよい)。"""
        return (not FORCE_ALL and self.data.get(key) == digest
                and all(eal.does_asset_exist(p) for p in asset_paths))

    def done(self, key, digest):
        self.data[key] = digest
        self.changed.append(key)

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(dict(sorted(self.data.items())), f, indent=1, ensure_ascii=False)
            f.write("\n")


state = None  # main() で作る


# ---------------------------------------------------------------- マテリアル
def color(material, rgb, x, y):
    e = mel.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, x, y)
    e.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    return e


def scalar(material, v, x, y):
    e = mel.create_material_expression(material, unreal.MaterialExpressionConstant, x, y)
    e.set_editor_property("r", v)
    return e


def below_ratio(mat, top_cm, blend_cm, y):
    """saturate((top_cm - ワールド Z) / blend_cm)。top_cm より低いほど 1 になる。"""
    wpos = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, -1500, y)
    z = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, -1300, y)
    for ch, on in (("r", False), ("g", False), ("b", True), ("a", False)):
        z.set_editor_property(ch, on)
    mel.connect_material_expressions(wpos, "", z, "")
    below = mel.create_material_expression(mat, unreal.MaterialExpressionSubtract, -1100, y)
    mel.connect_material_expressions(scalar(mat, top_cm, -1300, y + 100), "", below, "A")
    mel.connect_material_expressions(z, "", below, "B")
    ratio = mel.create_material_expression(mat, unreal.MaterialExpressionDivide, -950, y)
    mel.connect_material_expressions(below, "", ratio, "A")
    mel.connect_material_expressions(scalar(mat, blend_cm, -1100, y + 100), "", ratio, "B")
    sat = mel.create_material_expression(mat, unreal.MaterialExpressionSaturate, -800, y)
    mel.connect_material_expressions(ratio, "", sat, "")
    return sat


def noise(mat, scale, levels, x, y):
    """ワールド座標のむら (0..1)。"""
    e = mel.create_material_expression(mat, unreal.MaterialExpressionNoise, x, y)
    e.set_editor_property("scale", scale)
    e.set_editor_property("levels", levels)
    e.set_editor_property("output_min", 0.0)
    e.set_editor_property("output_max", 1.0)
    return e


def steep_ratio(mat, x, y):
    """saturate((SOIL_SLOPE_NZ - 法線の Z) / SOIL_SLOPE_BLEND)。急な斜面ほど 1 になる。"""
    nrm = mel.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS, x - 500, y)
    z = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, x - 350, y)
    for ch, on in (("r", False), ("g", False), ("b", True), ("a", False)):
        z.set_editor_property(ch, on)
    mel.connect_material_expressions(nrm, "", z, "")
    below = mel.create_material_expression(mat, unreal.MaterialExpressionSubtract, x - 200, y)
    mel.connect_material_expressions(scalar(mat, SOIL_SLOPE_NZ, x - 350, y + 100), "", below, "A")
    mel.connect_material_expressions(z, "", below, "B")
    ratio = mel.create_material_expression(mat, unreal.MaterialExpressionDivide, x - 100, y)
    mel.connect_material_expressions(below, "", ratio, "A")
    mel.connect_material_expressions(scalar(mat, SOIL_SLOPE_BLEND, x - 200, y + 100), "", ratio, "B")
    sat = mel.create_material_expression(mat, unreal.MaterialExpressionSaturate, x, y)
    mel.connect_material_expressions(ratio, "", sat, "")
    return sat


def multiply(mat, a, b, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, x, y)
    mel.connect_material_expressions(a, "", e, "A")
    mel.connect_material_expressions(b, "", e, "B")
    return e


def lerp(mat, a, b, alpha, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, x, y)
    mel.connect_material_expressions(a, "", e, "A")
    mel.connect_material_expressions(b, "", e, "B")
    mel.connect_material_expressions(alpha, "", e, "Alpha")
    return e


def add(mat, a, b, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionAdd, x, y)
    mel.connect_material_expressions(a, "", e, "A")
    mel.connect_material_expressions(b, "", e, "B")
    return e


def ramp(mat, v, lo, hi, x, y):
    """saturate((v - lo) / (hi - lo))。v が lo で 0、hi で 1 (hi < lo なら逆向き)。"""
    sub = mel.create_material_expression(mat, unreal.MaterialExpressionSubtract, x - 200, y)
    mel.connect_material_expressions(v, "", sub, "A")
    mel.connect_material_expressions(scalar(mat, lo, x - 350, y + 60), "", sub, "B")
    div = mel.create_material_expression(mat, unreal.MaterialExpressionDivide, x - 100, y)
    mel.connect_material_expressions(sub, "", div, "A")
    mel.connect_material_expressions(scalar(mat, hi - lo, x - 250, y + 100), "", div, "B")
    sat = mel.create_material_expression(mat, unreal.MaterialExpressionSaturate, x, y)
    mel.connect_material_expressions(div, "", sat, "")
    return sat


def grass_ground_color(mat, x, y, vertex=False):
    """草地の色 (ランドスケープと草の葉で同じ)。大きなむら (2 色の暗い緑)、中くらいのむら (乾いた所とみずみずしい所)、
    小さなむら (明るさ) をワールド座標で重ねる。vertex=True なら頂点で計算する (草の葉は細いのでそれで足り、軽い)。"""
    def world_noise(scale, levels, yy):
        e = noise(mat, scale, levels, x - 400, yy)
        if not vertex:
            return e
        vi = mel.create_material_expression(mat, unreal.MaterialExpressionVertexInterpolator, x - 250, yy)
        mel.connect_material_expressions(e, "", vi, "")
        return vi

    c = lerp(mat, color(mat, GRASS_COLOR, x - 250, y - 100), color(mat, GRASS_DARK_COLOR, x - 250, y),
             world_noise(GRASS_MACRO_SCALE, 4, y + 100), x - 100, y)
    patch = world_noise(GRASS_PATCH_SCALE, 3, y + 250)
    dry = multiply(mat, ramp(mat, patch, 0.55, 0.8, x - 250, y + 350), scalar(mat, GRASS_PATCH_AMOUNT, x - 250, y + 420), x - 100, y + 350)
    fresh = multiply(mat, ramp(mat, patch, 0.45, 0.2, x - 250, y + 500), scalar(mat, GRASS_PATCH_AMOUNT, x - 250, y + 570), x - 100, y + 500)
    c = lerp(mat, c, color(mat, GRASS_PATCH_DRY_COLOR, x - 100, y + 200), dry, x, y + 100)
    c = lerp(mat, c, color(mat, GRASS_PATCH_FRESH_COLOR, x - 100, y + 450), fresh, x + 100, y + 200)
    # 小さなむらで明るさを 0.8..1.2 倍に揺らす
    detail = lerp(mat, scalar(mat, 0.8, x - 100, y + 650), scalar(mat, 1.2, x - 100, y + 700),
                  world_noise(GRASS_DETAIL_SCALE, 2, y + 750), x, y + 700)
    return multiply(mat, c, detail, x + 200, y + 300)


def world_uv(mat, tile_cm, x, y, axes="rg"):
    """ワールドの 2 軸 (axes: "rg" = XY、"rb" = XZ、"gb" = YZ) を tile_cm ごとに 1 周する UV。"""
    wpos = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, x - 450, y)
    xy = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, x - 300, y)
    for ch in "rgba":
        xy.set_editor_property(ch, ch in axes)
    mel.connect_material_expressions(wpos, "", xy, "")
    div = mel.create_material_expression(mat, unreal.MaterialExpressionDivide, x - 150, y)
    mel.connect_material_expressions(xy, "", div, "A")
    mel.connect_material_expressions(scalar(mat, tile_cm, x - 300, y + 80), "", div, "B")
    return div


def texture_sample(mat, texture, uv, sampler, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, x, y)
    e.set_editor_property("texture", texture)
    e.set_editor_property("sampler_type", sampler)
    # 共有のサンプラーを使う (ランドスケープは絵が多く、1 つのマテリアルで使えるサンプラーの数 (16) を超えるため)
    e.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
    mel.connect_material_expressions(uv, "", e, "UVs")
    return e


def channel(mat, e, ch, x, y):
    """e の 1 成分 (ch = "r" / "g" / "b" / "a")。"""
    m = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, x, y)
    for c in "rgba":
        m.set_editor_property(c, c == ch)
    mel.connect_material_expressions(e, "", m, "")
    return m


def normal_axis(mat, ch, x, y, absolute=True):
    """頂点の法線 (ワールド) の 1 成分 (ch = "r" / "g" / "b")。absolute なら絶対値。"""
    nrm = mel.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS, x - 300, y)
    m = channel(mat, nrm, ch, x - 150, y)
    if not absolute:
        return m
    a = mel.create_material_expression(mat, unreal.MaterialExpressionAbs, x, y)
    mel.connect_material_expressions(m, "", a, "")
    return a


def triplanar(mat, texture, tile_cm, sampler, x, y):
    """3 方向 (上と、横の X・Y) から投影した絵を、面の向きで混ぜる。斜面でも絵が伸びない。"""
    top = texture_sample(mat, texture, world_uv(mat, tile_cm, x - 300, y, "rg"), sampler, x - 200, y)
    side_x = texture_sample(mat, texture, world_uv(mat, tile_cm, x - 300, y + 200, "gb"), sampler, x - 200, y + 200)
    side_y = texture_sample(mat, texture, world_uv(mat, tile_cm, x - 300, y + 400, "rb"), sampler, x - 200, y + 400)
    # 東西を向いた面 (法線の X が大きい) は YZ、南北を向いた面は XZ
    diff = mel.create_material_expression(mat, unreal.MaterialExpressionSubtract, x - 200, y + 600)
    mel.connect_material_expressions(normal_axis(mat, "r", x - 300, y + 600), "", diff, "A")
    mel.connect_material_expressions(normal_axis(mat, "g", x - 300, y + 700), "", diff, "B")
    side = lerp(mat, side_y, side_x, ramp(mat, diff, -0.25, 0.25, x - 50, y + 600), x, y + 300)
    up = ramp(mat, normal_axis(mat, "b", x - 300, y + 800, absolute=False), 0.75, 0.92, x - 50, y + 800)
    return lerp(mat, side, top, up, x + 150, y + 200)


# setup_grass() が取り込んだ草のアセット (ランドスケープマテリアルが使う)。
# 作り方のハッシュに入らないよう (アセットの repr はアドレスを含む)、dict ではなく SimpleNamespace にする
grass_assets = types.SimpleNamespace(grass_type=None, ground_color=None, ground_normal=None,
                                     soil_color=None, soil_normal=None, asphalt_color=None, asphalt_normal=None)
GROUND_TEXTURE_KEYS = ("ground_color", "ground_normal", "soil_color", "soil_normal", "asphalt_color", "asphalt_normal")


def coast_mask(mat, x, y):
    """海岸の絵 (テクスチャパラメータ CoastMask の赤、1 = 砂浜にしてよい)。一周コースのタイルのマテリアルインスタンス
    (tile_landscape_material) が、絵と範囲 (TileCorner = 北西の角、TileSize = 一辺、どちらも cm) を決める。
    既定は白い絵なので、絵の無いランドスケープ (二見ヶ浦だけのレベル) はこれまでどおり低い所がすべて砂浜。"""
    wpos = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, x - 600, y)
    xy = channel(mat, wpos, "r", x - 450, y)
    for ch in "rgba":
        xy.set_editor_property(ch, ch in "rg")
    corner = channel(mat, vector_param(mat, "TileCorner", (0.0, 0.0, 0.0), x - 600, y + 120), "r", x - 450, y + 120)
    for ch in "rgba":
        corner.set_editor_property(ch, ch in "rg")
    rel = mel.create_material_expression(mat, unreal.MaterialExpressionSubtract, x - 300, y)
    mel.connect_material_expressions(xy, "", rel, "A")
    mel.connect_material_expressions(corner, "", rel, "B")
    uv = mel.create_material_expression(mat, unreal.MaterialExpressionDivide, x - 150, y)
    mel.connect_material_expressions(rel, "", uv, "A")
    mel.connect_material_expressions(scalar_param(mat, "TileSize", 403200.0, x - 300, y + 120), "", uv, "B")
    tex = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    tex.set_editor_property("parameter_name", "CoastMask")
    tex.set_editor_property("texture", eal.load_asset(COAST_MASK_DEFAULT))
    tex.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    tex.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS)
    mel.connect_material_expressions(uv, "", tex, "UVs")
    return channel(mat, tex, "r", x + 200, y)


def build_landscape_graph(mat):
    """草 (むらのある緑と地面の細かい模様、急な斜面は小石と雨の筋のある土) -> 砂浜 (乾いた砂、波打ち際は濡れた砂) を高さで塗り、
    その上に道路の重みで道路 (砕石とひび割れのあるアスファルト) を塗る。重みを塗っていない所は草。
    草地にはランドスケープグラスで立体の草を生やす。"""
    road = mel.create_material_expression(mat, unreal.MaterialExpressionLandscapeLayerSample, -900, 150)
    road.set_editor_property("parameter_name", "Road")
    road.set_editor_property("preview_weight", 0.0)
    # 低い所を砂浜にする。ただし海岸の絵 (CoastMask) が 0 の所 (海から遠い田んぼや埋立地) は草地のまま
    coast = coast_mask(mat, -1200, 4200)
    dry = multiply(mat, below_ratio(mat, SAND_DRY_TOP_CM, SAND_DRY_BLEND_CM, 500), coast, -650, 500)
    wet = multiply(mat, below_ratio(mat, SAND_WET_TOP_CM, SAND_WET_BLEND_CM, 800), coast, -650, 800)
    steep = steep_ratio(mat, -700, -900)

    sand = lerp(mat, color(mat, SAND_DRY_COLOR, -800, -300), color(mat, SAND_WET_COLOR, -800, -200), wet, -600, -250)
    grass = grass_ground_color(mat, -1100, -1800)
    ground_color, ground_normal = grass_assets.ground_color, grass_assets.ground_normal
    if ground_color:
        # 上から見た草の葉の模様 (0.5 で 1 倍) を 2 つの大きさで重ねて掛ける
        small = texture_sample(mat, ground_color, world_uv(mat, GROUND_TILE_CM, -1100, -2200),
                               unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR, -1000, -2200)
        large = texture_sample(mat, ground_color, world_uv(mat, GROUND_TILE_LARGE_CM, -1100, -2400),
                               unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR, -1000, -2400)
        pattern = multiply(mat, multiply(mat, small, large, -800, -2300), scalar(mat, 4.0, -800, -2200), -700, -2300)
        grass = multiply(mat, grass, pattern, -650, -1500)
    linear = unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
    normal = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
    # 土: 黄土色 x 大きなむら x 小石と雨の筋の模様 (0.5 で 1 倍、3 方向から投影)
    soil = multiply(mat, color(mat, SOIL_COLOR, -900, -650),
                    lerp(mat, scalar(mat, 0.8, -1000, -600), scalar(mat, 1.2, -1000, -560),
                         noise(mat, SOIL_PATCH_SCALE, 3, -1000, -520), -850, -580), -700, -620)
    if grass_assets.soil_color:
        soil_tex = triplanar(mat, grass_assets.soil_color, SOIL_TILE_CM, linear, -1100, -3600)
        soil = multiply(mat, soil, multiply(mat, soil_tex, scalar(mat, 2.0, -800, -3300), -700, -3400), -600, -650)
    grass = lerp(mat, grass, soil, steep, -600, -550)
    ground = lerp(mat, grass, sand, dry, -400, -100)
    # 道路: アスファルト x 大きなむら x 砕石とひび割れの模様
    asphalt = multiply(mat, color(mat, ROAD_COLOR, -700, 50),
                       lerp(mat, scalar(mat, 0.8, -800, 100), scalar(mat, 1.15, -800, 140),
                            noise(mat, ASPHALT_PATCH_SCALE, 2, -800, 180), -650, 120), -550, 60)
    asphalt_tex = None
    if grass_assets.asphalt_color:
        asphalt_tex = texture_sample(mat, grass_assets.asphalt_color, world_uv(mat, ASPHALT_TILE_CM, -1100, 2200),
                                     linear, -1000, 2200)
        asphalt = multiply(mat, asphalt, multiply(mat, asphalt_tex, scalar(mat, 2.0, -800, 2300), -700, 2250), -450, 80)
    base = lerp(mat, ground, asphalt, road, -200, 0)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # 草が生えるのは道路・砂浜・急な斜面 (土) 以外。道路の縁は早めに草を減らす
    one_minus = lambda e, x, y: ramp(mat, e, 1.0, 0.0, x, y)
    grassy = multiply(mat, multiply(mat, ramp(mat, road, 0.5, 0.0, -100, 1100), one_minus(dry, -100, 1250), 50, 1150),
                      one_minus(steep, -100, 1400), 200, 1200)
    # 凹凸: 草地 -> 土 (急な斜面) -> 砂浜 (平ら) -> 道路 の順に、色と同じ重みで重ねる
    flat = lambda x, y: color(mat, (0.0, 0.0, 1.0), x, y)
    toward = lambda bumps, k, x, y: lerp(mat, flat(x - 150, y), bumps, scalar(mat, k, x - 150, y + 60), x, y)
    nrm = flat(-600, 1500)
    if ground_normal:
        bumps = texture_sample(mat, ground_normal, world_uv(mat, GROUND_TILE_CM, -1100, 1600), normal, -1000, 1600)
        nrm = toward(bumps, GROUND_NORMAL_STRENGTH, -600, 1600)
    if grass_assets.soil_normal:
        bumps = triplanar(mat, grass_assets.soil_normal, SOIL_TILE_CM, normal, -1100, 2600)
        nrm = lerp(mat, nrm, toward(bumps, SOIL_NORMAL_STRENGTH, -600, 2700), steep, -400, 1700)
    nrm = lerp(mat, nrm, flat(-400, 1900), dry, -250, 1800)
    if grass_assets.asphalt_normal:
        bumps = texture_sample(mat, grass_assets.asphalt_normal, world_uv(mat, ASPHALT_TILE_CM, -1100, 3600), normal, -1000, 3600)
        nrm = lerp(mat, nrm, toward(bumps, ASPHALT_NORMAL_STRENGTH, -600, 3600), road, -100, 1900)
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    if grass_assets.grass_type:
        connect_grass_output(mat, grassy, grass_assets.grass_type, 400, 1200)

    sand_rough = lerp(mat, scalar(mat, 0.85, -800, 300), scalar(mat, 0.4, -800, 380), wet, -600, 320)
    ground_rough = lerp(mat, scalar(mat, 0.9, -600, 250), sand_rough, dry, -400, 300)
    road_rough = scalar(mat, 0.6, -400, 400)
    if asphalt_tex:   # 砕石の明るい所は少しつるっとしている
        road_rough = lerp(mat, scalar(mat, ASPHALT_ROUGHNESS[0], -500, 420), scalar(mat, ASPHALT_ROUGHNESS[1], -500, 460),
                          ramp(mat, channel(mat, asphalt_tex, "r", -650, 500), 0.3, 0.8, -500, 500), -350, 440)
    rough = lerp(mat, ground_rough, road_rough, road, -200, 300)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)


def connect_grass_output(mat, weight, grass_type, x, y):
    """ランドスケープグラスの出力 (Grass) に、草を生やす重み (0..1) をつなぐ。"""
    cls = getattr(unreal, "MaterialExpressionLandscapeGrassOutput", None)
    if cls is None:
        unreal.log_warning("[setup_project] MaterialExpressionLandscapeGrassOutput がありません。草は生やしません")
        return
    out = mel.create_material_expression(mat, cls, x, y)
    gi = unreal.GrassInput()
    gi.set_editor_property("name", "Grass")
    gi.set_editor_property("grass_type", grass_type)
    out.set_editor_property("grass_types", [gi])
    if not mel.connect_material_expressions(weight, "", out, "Grass"):
        unreal.log_warning("[setup_project] ランドスケープグラスの出力に重みをつなげませんでした")


def build_sea_graph(mat):
    # 遠景の板。Ocean の沖の色に近い深い青にし、夕日がつやっと映るよう粗さを下げる
    mel.connect_material_property(color(mat, (0.004, 0.022, 0.045), -300, 0), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(mat, 0.04, -300, 150), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, 0.6, -300, 250), "", unreal.MaterialProperty.MP_SPECULAR)


def build_far_terrain_graph(mat):
    # 色は build_far_terrain.py が頂点カラーに入れている (森・田畑・町・浜・海底)
    # VertexColor は glTF に書いたリニアの値をそのまま返す (2.2 乗すると黒くなった)
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -300, 0)
    mel.connect_material_property(vc, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(mat, FAR_TERRAIN_ROUGHNESS, -300, 150), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, FAR_TERRAIN_SPECULAR, -300, 250), "", unreal.MaterialProperty.MP_SPECULAR)


def create_landscape_material(directory=MATERIAL_DIR, rebuild=REBUILD_MATERIAL):
    # 草のアセットが有るか無いか (と、そのパス) でもグラフが変わる
    used = [a.get_path_name() if a else None
            for a in [grass_assets.grass_type] + [getattr(grass_assets, k) for k in GROUND_TEXTURE_KEYS]]
    return create_material("M_Landscape", build_landscape_graph, directory, rebuild, extra=used)


def create_material(name, build_graph, directory=MATERIAL_DIR, rebuild=REBUILD_MATERIAL, extra=()):
    path = f"{directory}/{name}"
    digest = recipe(build_graph, *extra)
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        if not rebuild or state.fresh(path, digest, path):
            return mat
        # 1回では消し残しが出るので、無くなるまで繰り返す
        for _ in range(10):
            if mel.get_num_material_expressions(mat) == 0:
                break
            mel.delete_all_material_expressions(mat)
        action = "組み直し"
    else:
        mat = asset_tools.create_asset(name, directory, unreal.Material, unreal.MaterialFactoryNew())
        action = "作成"
    build_graph(mat)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    state.done(path, digest)
    log(f"{action}: {path}")
    return mat


# ---------------------------------------------------------------- 夜 (星空・防犯灯)
# 星空は空の球 (Is Sky のマテリアル M_FD_Sky) に描く。空の球があると大気は球の上に描かれるので、
# 大気の明るさ・太陽と月の円盤も同じマテリアルで足す。星は時刻に合わせて天の北極のまわりに回る (FDTimeOfDay が回す)
NIGHT_MPC = "MPC_FD_Night"
NIGHT_PARAMS = (  # (名前, 既定値)。プレイ中は FDTimeOfDay が上書きする
    ("NightLights", 0.0),          # 防犯灯の点き具合 (0..1)
    ("StarRotation", 4.0),         # 地方恒星時 (ラジアン)。既定は夏至の 21 時ごろ
    ("StarBrightness", 9.0),       # 0 等星の明るさ (cd/m2)
    ("MilkyWayBrightness", 0.12),  # 天の川の明るさ (cd/m2)
    ("CityGlowBrightness", 0.3),  # 福岡市・前原の街明かりの明るさ (cd/m2)
    ("HouseLights", 0.0),          # 灯っている家の窓の割合 (0..1)。暗くなると上がり、夜更けには下がる
    ("SinLatitude", 0.553987),     # 星空の緯度 (sin, cos)。既定は糸島 (33.641°)。FDTimeOfDay がコースの緯度で上書きする
    ("CosLatitude", 0.832525),     # (コースごとにマテリアルを作り直さなくてよいよう、焼き込まずに渡す)
    ("SinGridRotation", 0.0),      # コースの升目の回転 (sin, cos)。北が UE の -Y から回っている角度。FDTimeOfDay が書く
    ("CosGridRotation", 1.0),
)
SKY_DOME_RADIUS_CM = 1.0e8         # 空の球の半径 (1000 km。遠景の地形 (110 km 四方) より十分外)
LAMP_GLOW_COLOR = (1.0, 0.95, 0.88)
LAMP_GLOW_NITS = 400.0             # 点いた防犯灯の光る面の明るさ (cd/m2)。実物より暗いが、夜の露出ではまぶしく光る

# 星・天の川・街明かり (cd/m2) を返す HLSL。Dir はカメラへの向き (CameraVector)。
# UE の +X が東、+Y が南。空の向きを赤道座標 (赤経・赤緯) に直し、そこで星を決めるので、恒星時で回すと日周運動になる
SKY_HLSL = """
float3 d = -normalize(Dir);
// 東と北の向き。コースの升目を回しているときは UE の軸から GridRotation 度ずれる (tools/terrain/geo.py)
float e = d.x * CosGrid + d.y * SinGrid, n = d.x * SinGrid - d.y * CosGrid, u = d.z;
float sl = SinLat, cl = CosLat;
// 天の子午線 (時角 0)・西・天の北極の向きの成分
float ha = -sl * n + cl * u;
float hb = -e;
float hz = cl * n + sl * u;
float cs = cos(LST), sn = sin(LST);
float3 q = float3(cs * ha + sn * hb, sn * ha - cs * hb, hz);
float ext = smoothstep(-0.02, 0.25, u);   // 地平線の近くは大気で暗い

// 星 (約1万個)。空を 1/28 ラジアンの立方体の格子に分け、格子ごとに 1 つ星を置く (球に移した点が格子の中に残るものだけ)
float pix = max(length(fwidth(q)), 1e-6);
float sigma = max(0.0009, 0.6 * pix);
float peak = (0.0009 / sigma) * (0.0009 / sigma);   // 画面が粗いと星をにじませ、明るさの合計は変えない
const float K = 28.0;
float3 p = q * K;
float3 c0 = floor(p);
float3 stars = 0;
for (int i = -1; i <= 1; i++)
for (int j = -1; j <= 1; j++)
for (int k = -1; k <= 1; k++)
{
    float3 cell = c0 + float3(i, j, k);
    float3 h1 = frac(sin(float3(dot(cell, float3(127.1, 311.7, 74.7)), dot(cell, float3(269.5, 183.3, 246.1)),
                                dot(cell, float3(113.5, 271.9, 124.6)))) * 43758.5453);
    float3 h2 = frac(sin(float3(dot(cell, float3(419.2, 371.9, 168.2)), dot(cell, float3(237.3, 97.1, 309.6)),
                                dot(cell, float3(61.7, 199.1, 283.3)))) * 24634.6345);
    float3 s = normalize(cell + 0.1 + 0.8 * h1) * K;
    if (any(floor(s) != cell)) continue;
    float ang = length(p - s) / K;
    // 等級: 暗い星ほど多い (1 等級ごとに約 2.8 倍)
    float mag = max(-1.5, 6.5 + log10(max(h2.x, 1e-4)) / 0.45);
    float tw = 1.0 + 0.3 * (1.0 - saturate(u * 3.0)) * sin(Time * (5.0 + 9.0 * h2.y) + h2.z * 50.0);
    float3 tint = lerp(lerp(float3(0.70, 0.80, 1.0), float3(1.0, 1.0, 1.0), saturate(h2.y * 2.5)),
                       float3(1.0, 0.75, 0.5), saturate(h2.y * 2.5 - 1.5));
    stars += tint * (pow(10.0, -0.4 * mag) * tw * exp(-(ang * ang) / (sigma * sigma)));
}

// 天の川: 銀河面 (北極は赤経 192.9°・赤緯 27.1°) に沿った帯。いて座の銀河の中心ほど明るく、暗黒帯が通る
const float3 NGP = float3(-0.8676, -0.1981, 0.4560);
const float3 GC = float3(-0.0549, -0.8734, -0.4838);
float sb = dot(q, NGP);
float lc = dot(q, GC);
float f = 0.0, amp = 0.5;
float3 x = q * 4.0 + 3.1;
#define FD_HASH(c) frac(sin(dot(c, float3(127.1, 311.7, 74.7))) * 43758.5453)
for (int o = 0; o < 5; o++)
{
    float3 i0 = floor(x);
    float3 fr = frac(x);
    fr = fr * fr * (3.0 - 2.0 * fr);
    float v = lerp(lerp(lerp(FD_HASH(i0), FD_HASH(i0 + float3(1, 0, 0)), fr.x),
                        lerp(FD_HASH(i0 + float3(0, 1, 0)), FD_HASH(i0 + float3(1, 1, 0)), fr.x), fr.y),
                   lerp(lerp(FD_HASH(i0 + float3(0, 0, 1)), FD_HASH(i0 + float3(1, 0, 1)), fr.x),
                        lerp(FD_HASH(i0 + float3(0, 1, 1)), FD_HASH(i0 + float3(1, 1, 1)), fr.x), fr.y), fr.z);
    f += amp * v;
    amp *= 0.5;
    x = x * 2.07 + 11.3;
}
#undef FD_HASH
float w = 0.13 + 0.06 * (f - 0.5);
// むら (星雲や星の集まり) を強くして、一様な霞に見えないようにする
float clump = 0.1 + 1.8 * smoothstep(0.35, 0.72, f);
float band = exp(-(sb * sb) / (w * w)) * (0.25 + 0.75 * pow(saturate(0.5 + 0.5 * lc), 4.0)) * clump;
band += 0.8 * exp(-(1.0 - lc) * 18.0) * exp(-(sb * sb) / 0.03);
float lane = (sb - 0.015 - 0.05 * (f - 0.5)) / 0.03;
float dust = 1.0 - 0.9 * exp(-lane * lane) * saturate(lc * 1.5 + 0.3) * smoothstep(0.3, 0.55, f);
float3 milky = float3(1.0, 0.93, 0.85) * band * dust;

// 街明かり: 東南東 (方位 107°) の福岡市と、南南東 (160°) の前原の空が地平線の近くだけ橙にぼんやり明るい
float2 hd = normalize(float2(e, n) + 1e-5);
float glow = (pow(saturate(dot(hd, float2(0.956, -0.292))), 3.0)
              + 0.4 * pow(saturate(dot(hd, float2(0.342, -0.940))), 10.0)) * exp(-max(u, 0.0) / 0.15) * step(-0.05, u);

return (stars * StarB * peak + milky * MilkyB) * ext + float3(1.0, 0.62, 0.35) * glow * GlowB;
"""

night_assets = types.SimpleNamespace(collection=None, sky=None, lamp_glow=None)


def create_night_collection():
    """MPC_FD_Night (夜の値を FDTimeOfDay からマテリアルへ渡す)。無いパラメータだけ足す
    (作り直すとパラメータの ID が変わり、使っているマテリアルがつながらなくなるため)。"""
    path = f"{MATERIAL_DIR}/{NIGHT_MPC}"
    if eal.does_asset_exist(path):
        mpc = eal.load_asset(path)
    else:
        mpc = asset_tools.create_asset(NIGHT_MPC, MATERIAL_DIR, unreal.MaterialParameterCollection,
                                       unreal.MaterialParameterCollectionFactoryNew())
        log(f"作成: {path}")
    params = list(mpc.get_editor_property("scalar_parameters"))
    have = {str(p.get_editor_property("parameter_name")): p for p in params}
    changed = False
    for name, value in NIGHT_PARAMS:
        if name in have:
            if abs(have[name].get_editor_property("default_value") - value) > 1e-6:
                have[name].set_editor_property("default_value", value)
                changed = True
            continue
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", name)
        p.set_editor_property("default_value", value)
        params.append(p)
        changed = True
    if changed:
        mpc.set_editor_property("scalar_parameters", params)
        eal.save_loaded_asset(mpc)
        state.changed.append(path)
        log(f"パラメータ: {path} ({', '.join(n for n, _ in NIGHT_PARAMS)})")
    night_assets.collection = mpc
    return mpc


def night_param(mat, name, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionCollectionParameter, x, y)
    e.set_editor_property("collection", night_assets.collection)
    e.set_editor_property("parameter_name", name)
    return e


def build_sky_graph(mat):
    """空の球のマテリアル。大気の明るさ + 太陽と月の円盤 + 星・天の川・街明かり (SKY_HLSL)。"""
    set_props(mat, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, is_sky=True, two_sided=True)
    custom = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, -600, 300)
    custom.set_editor_property("code", SKY_HLSL)
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    custom.set_editor_property("description", "Stars")
    inputs = []
    for name in ("Dir", "LST", "Time", "StarB", "MilkyB", "GlowB", "SinLat", "CosLat", "SinGrid", "CosGrid"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", name)
        inputs.append(ci)
    custom.set_editor_property("inputs", inputs)
    sources = (
        ("Dir", mel.create_material_expression(mat, unreal.MaterialExpressionCameraVectorWS, -900, 200)),
        ("LST", night_param(mat, "StarRotation", -900, 280)),
        ("Time", mel.create_material_expression(mat, unreal.MaterialExpressionTime, -900, 360)),
        ("StarB", night_param(mat, "StarBrightness", -900, 440)),
        ("MilkyB", night_param(mat, "MilkyWayBrightness", -900, 520)),
        ("GlowB", night_param(mat, "CityGlowBrightness", -900, 600)),
        ("SinLat", night_param(mat, "SinLatitude", -900, 680)),
        ("CosLat", night_param(mat, "CosLatitude", -900, 760)),
        ("SinGrid", night_param(mat, "SinGridRotation", -900, 840)),
        ("CosGrid", night_param(mat, "CosGridRotation", -900, 920)),
    )
    for pin, src in sources:
        mel.connect_material_expressions(src, "", custom, pin)
    view = mel.create_material_expression(mat, unreal.MaterialExpressionSkyAtmosphereViewLuminance, -600, -200)
    disks = []
    for i in (0, 1):  # 0 = 太陽、1 = 月 (FDTimeOfDay の MoonLight)
        disk = mel.create_material_expression(mat, unreal.MaterialExpressionSkyAtmosphereLightDiskLuminance, -600, -50 + 120 * i)
        disk.set_editor_property("light_index", i)
        disks.append(disk)
    total = add(mat, add(mat, view, disks[0], -350, -150), add(mat, disks[1], custom, -350, 150), -150, 0)
    mel.connect_material_property(total, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)


def build_lamp_glow_graph(mat):
    """防犯灯の光る面。昼は白い樹脂のカバー、夜は MPC_FD_Night の NightLights に合わせて光る。"""
    for usage in ("used_with_instanced_static_meshes", "used_with_nanite"):
        try:
            mat.set_editor_property(usage, True)
        except Exception:
            pass
    mel.connect_material_property(color(mat, (0.8, 0.8, 0.78), -500, -100), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(mat, 0.3, -500, 0), "", unreal.MaterialProperty.MP_ROUGHNESS)
    glow = multiply(mat, color(mat, tuple(c * LAMP_GLOW_NITS for c in LAMP_GLOW_COLOR), -700, 150),
                    night_param(mat, "NightLights", -700, 250), -450, 200)
    mel.connect_material_property(glow, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)


# 建物 (tools/terrain/buildings.py)。窓の板は作らず、壁のマテリアルが UV の格子に窓を描く。
# 壁: UV0 の U = 窓の列、V = 階 (基礎は負)。UV1 の X = 建物ごとの乱数、Y = 窓の描き方 (buildings.py の STYLE_*:
# 0 窓なし、1 家、2 店 (1 階がガラス張り)、3 コンビニ (ガラス張りと色の帯、夜通し明るい)、4 カフェ (大きな窓)、
# 5 社寺 (窓なし、縦の板張り)、6 事務所・学校 (横に続く窓))。頂点の色 = 壁の色
# 屋根: UV1 の X = 建物ごとの乱数、Y = 屋根の種類 (0 瓦、1 金属、2 平らなコンクリート)。頂点の色 = 屋根の色
# 壁と屋根の模様と凹凸の絵 (tools/terrain/building_textures.py) は、ワールド座標で貼る (壁は横 = 壁に沿った向き、縦 = 高さ。
# 屋根は横 = 軒に沿った向き、縦 = 流れの上向き)。凹凸はワールド空間の法線にしてから渡す
BUILDING_TEXTURE_DIR = f"{SCENERY_DIR}/BuildingTextures"
WINDOW_NITS = 30.0                 # 灯った窓の明るさ (cd/m2)。カーテン越しはこの 3 割ほど
SIDING_SHARE = 0.55                # 壁がサイディングの家の割合 (ほかはモルタル)
WALL_NORMAL_STRENGTH = 1.0
ROOF_NORMAL_STRENGTH = 1.0
# 面の向きに沿った軸。t = 壁に沿った横 (屋根は軒に沿った向き)、b = 上 (屋根は流れの上向き)
SURFACE_AXES_HLSL = """
float3 n = normalize(N);
float3 t = abs(n.z) > 0.99 ? float3(1, 0, 0) : normalize(cross(float3(0, 0, 1), n));
float3 b = cross(n, t);
"""
BUILDING_HLSL = """
float2 f = frac(UV);
float2 cell = floor(UV);
float bid = floor(Seed.x * 1024.0);
float hb = frac(sin(bid * 12.9898 + 4.1414) * 43758.5453);
float hb2 = frac(sin(bid * 78.233 + 1.618) * 24634.6345);
float hb3 = frac(sin(bid * 39.425 + 2.718) * 15731.743);
float h1 = frac(sin(dot(float3(cell, bid), float3(12.9898, 78.233, 0.3713))) * 43758.5453);
float h2 = frac(sin(dot(float3(cell, bid), float3(39.346, 11.135, 0.8315))) * 24634.6345);
float siding = step(frac(hb * 7.13 + hb2 * 3.7), SIDING);
float found = step(UV.y, -0.001);
float st = floor(Seed.y + 0.5);
float ground = step(-0.5, cell.y) * step(cell.y, 0.5);
float shopfront = (st > 1.5 && st < 3.5) ? ground : 0.0;   // 店とコンビニの 1 階
// 窓の大きさは建物ごと、窓の無い列 (壁・柱) が少し混じる。幅の広い窓は真ん中に縦の框 (引き違い窓)
float hw = lerp(0.17, 0.36, hb);
float y0 = 0.30, y1 = lerp(0.70, 0.88, hb2);
float keep = step(0.14, h2);
if (st > 5.5) { hw = 0.5; y0 = 0.36; y1 = 0.74; keep = 1.0; }
else if (st > 4.5) { keep = 0.0; }
else if (st > 3.5) { hw = 0.40; y0 = 0.14; y1 = 0.86; keep = 1.0; }
if (shopfront > 0.5) { hw = 0.47; y0 = 0.05; y1 = st > 2.5 ? 0.68 : 0.78; keep = 1.0; }
float m = step(0.5, st) * keep * step(abs(f.x - 0.5), hw) * step(y0, f.y) * step(f.y, y1);
// コンビニの軒の色の帯 (店ごとに青・緑・赤のどれか。店の名前や印は描かない)
float band = (st > 2.5 && st < 3.5) ? ground * step(0.73, f.y) * step(f.y, 0.87) : 0.0;
float3 bandC = hb < 0.33 ? float3(0.02, 0.10, 0.40) : (hb < 0.66 ? float3(0.02, 0.28, 0.07) : float3(0.50, 0.04, 0.02));
float fr = 0.035;
float glass = m * step(abs(f.x - 0.5), hw - fr) * step(y0 + fr * 1.5, f.y) * step(f.y, y1 - fr * 1.5);
glass *= hw > 0.22 ? step(0.012, abs(f.x - 0.5)) : 1.0;
"""
BUILDING_HLSL_BASE = """
float3 wall = VC * lerp(0.9, 1.08, hb) * lerp(PD.r, SD.r, siding);
wall *= lerp(0.78, 1.0, saturate(UV.y * 3.0));      // 地面の近く (1 階の下 1m) は泥はねで暗い
wall *= (st > 4.5 && st < 5.5) ? 0.82 + 0.18 * step(0.07, frac(UV.x * 14.0)) : 1.0;   // 社寺の縦の板張り
wall = lerp(wall, float3(0.30, 0.29, 0.27) * CD.r, found);
// ガラスの奥にカーテンが見える窓もある
float3 glassC = lerp(float3(0.012, 0.015, 0.02), float3(0.10, 0.09, 0.07) * (0.5 + 0.5 * h2), step(0.55, frac(h1 * 3.7)));
glassC = shopfront + step(3.5, st) * step(st, 4.5) > 0.5 ? float3(0.03, 0.03, 0.028) : glassC;
return lerp(lerp(lerp(wall, bandC, band), float3(0.33, 0.33, 0.32), m), glassC, glass);
"""
BUILDING_HLSL_ROUGH = """
return lerp(lerp(lerp(lerp(0.85, 0.92, found), 0.3, band), 0.4, m), 0.06, glass);
"""
BUILDING_HLSL_NORMAL = """
float3 tn = found > 0.5 ? CN : (siding > 0.5 ? SN : PN);
float k = STRENGTH * (1.0 - m) * (1.0 - band);
return normalize(n + (t * tn.x + b * tn.y) * k);
"""
# 留守の家 (1 割強) は灯らない。Lit (HouseLights) より乱数の小さい窓が灯るので、夜が更けると 1 つずつ消えていく。
# コンビニは暗い間ずっと明るい。店とカフェは夜更け (Lit が 0.2 を切るころ) に閉まる。事務所は灯る窓が少ない
BUILDING_HLSL_EMISSIVE = """
float dark = saturate(Lit * 40.0);
float on = step(0.13, hb3) * saturate((Lit - h1) * 25.0);
float3 c = h2 < 0.55 ? float3(1.0, 0.68, 0.38) : (h2 < 0.85 ? float3(1.0, 0.88, 0.74) : float3(0.82, 0.9, 1.0));
float curtain = lerp(0.25, 1.0, frac(h1 * 7.31));
if (st > 2.5 && st < 3.5) { on = dark * 2.0; c = float3(0.9, 0.95, 1.0); curtain = 1.0; }
else if (shopfront > 0.5 || (st > 3.5 && st < 4.5)) { on = saturate((Lit - 0.2) * 10.0) * 1.3; c = float3(1.0, 0.74, 0.45); curtain = 1.0; }
else if (st > 5.5) { on = saturate((Lit * 0.5 - h1) * 25.0); c = float3(0.85, 0.92, 1.0); curtain = 0.8; }
return c * (curtain * on * glass * NITS) + bandC * (band * dark * 0.4 * NITS);
"""
WALL_UV_HLSL = """
return float2(dot(WP, t), -WP.z) / 100.0;
"""
ROOF_UV_HLSL = """
return float2(dot(WP, t), -dot(WP, b)) / 100.0;
"""
# 屋根: 頂点の色 x 種類ごとの模様 (瓦・金属・コンクリート) x 建物ごとの色のむら
ROOF_HLSL_BASE = """
float k = Seed.y;
float tex = k < 0.5 ? KD.r : (k < 1.5 ? MD.r : CD.r);
return VC * tex * lerp(0.9, 1.1, frac(sin(floor(Seed.x * 1024.0) * 12.9898) * 43758.5453));
"""
ROOF_HLSL_ROUGH = """
return Seed.y < 0.5 ? 0.5 : (Seed.y < 1.5 ? 0.35 : 0.9);
"""
ROOF_HLSL_NORMAL = """
float3 tn = Seed.y < 0.5 ? KN : (Seed.y < 1.5 ? MN : CN);
return normalize(n + (t * tn.x + b * tn.y) * STRENGTH);
"""

building_assets = types.SimpleNamespace(textures={})   # 名前 -> (色, 凹凸, 大きさ m)


def custom_node(mat, code, inputs, out_type, x, y, desc):
    """inputs: [(名前, 式)]。HLSL の Custom ノードを作ってつなぐ。"""
    custom = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, x, y)
    custom.set_editor_property("code", code)
    custom.set_editor_property("output_type", out_type)
    custom.set_editor_property("description", desc)
    pins = []
    for name, _ in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", name)
        pins.append(ci)
    custom.set_editor_property("inputs", pins)
    for name, src in inputs:
        mel.connect_material_expressions(src, "", custom, name)
    return custom


def texcoord(mat, index, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, x, y)
    e.set_editor_property("coordinate_index", index)
    return e


def mesh_usages(mat):
    for usage in ("used_with_instanced_static_meshes", "used_with_nanite"):
        try:
            mat.set_editor_property(usage, True)
        except Exception:
            pass


def surface_samples(mat, uv_code, kinds, x, y):
    """面に沿ったワールド座標の UV で、kinds の色と凹凸の絵を読む。({名前: (色, 凹凸)}, 法線, 位置) を返す。"""
    out = unreal.CustomMaterialOutputType
    wp = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, x - 600, y)
    nrm = mel.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS, x - 600, y + 100)
    uv = custom_node(mat, SURFACE_AXES_HLSL + uv_code, [("WP", wp), ("N", nrm)], out.CMOT_FLOAT2, x - 400, y, "Surface UV (m)")
    samples = {}
    for i, kind in enumerate(kinds):
        color_tex, normal_tex, size_m = building_assets.textures[kind]
        tiled = multiply(mat, uv, scalar(mat, 1.0 / size_m, x - 400, y + 150 + 200 * i), x - 250, y + 150 + 200 * i)
        samples[kind] = (texture_sample(mat, color_tex, tiled, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, x, y + 200 * i),
                         texture_sample(mat, normal_tex, tiled, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, x, y + 100 + 200 * i))
    return samples, nrm


def build_building_wall_graph(mat):
    """建物の壁。壁の色 (頂点の色) x サイディングかモルタルの模様に窓 (枠とガラス) を描き、基礎はコンクリート。
    夜は MPC_FD_Night の HouseLights の割合の窓が灯る。凹凸はワールド空間の法線で渡す。"""
    mesh_usages(mat)
    set_props(mat, tangent_space_normal=False)
    out = unreal.CustomMaterialOutputType
    s, nrm = surface_samples(mat, WALL_UV_HLSL, ("WallSiding", "WallPlaster", "Concrete"), -1400, -600)
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -1100, 0)
    common = [("UV", texcoord(mat, 0, -1100, -200)), ("Seed", texcoord(mat, 1, -1100, -100))]
    code = (BUILDING_HLSL + BUILDING_HLSL_BASE).replace("SIDING", f"{SIDING_SHARE:.3f}")
    base = custom_node(mat, code, common + [("VC", vc), ("SD", s["WallSiding"][0]), ("PD", s["WallPlaster"][0]),
                                            ("CD", s["Concrete"][0])], out.CMOT_FLOAT3, -600, -200, "Wall base")
    code = (BUILDING_HLSL + BUILDING_HLSL_ROUGH).replace("SIDING", f"{SIDING_SHARE:.3f}")
    rough = custom_node(mat, code, common, out.CMOT_FLOAT1, -600, 0, "Wall roughness")
    code = (SURFACE_AXES_HLSL + BUILDING_HLSL + BUILDING_HLSL_NORMAL).replace("SIDING", f"{SIDING_SHARE:.3f}")
    code = code.replace("STRENGTH", f"{WALL_NORMAL_STRENGTH:.3f}")
    normal = custom_node(mat, code, common + [("N", nrm), ("SN", s["WallSiding"][1]), ("PN", s["WallPlaster"][1]),
                                              ("CN", s["Concrete"][1])], out.CMOT_FLOAT3, -600, 400, "Wall normal (world)")
    code = (BUILDING_HLSL + BUILDING_HLSL_EMISSIVE).replace("SIDING", f"{SIDING_SHARE:.3f}")
    code = code.replace("NITS", f"{WINDOW_NITS:.3f}")
    emis = custom_node(mat, code, common + [("Lit", night_param(mat, "HouseLights", -1100, 200))], out.CMOT_FLOAT3,
                       -600, 200, "Windows lit")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(emis, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)


def build_building_roof_graph(mat):
    """建物の屋根。屋根の色 (頂点の色) x 種類ごとの模様と凹凸 (瓦・金属・コンクリート)。"""
    mesh_usages(mat)
    set_props(mat, tangent_space_normal=False)
    out = unreal.CustomMaterialOutputType
    s, nrm = surface_samples(mat, ROOF_UV_HLSL, ("RoofKawara", "RoofMetal", "Concrete"), -1400, -600)
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -1100, 0)
    seed = texcoord(mat, 1, -1100, -100)
    base = custom_node(mat, ROOF_HLSL_BASE, [("Seed", seed), ("VC", vc), ("KD", s["RoofKawara"][0]),
                                             ("MD", s["RoofMetal"][0]), ("CD", s["Concrete"][0])],
                       out.CMOT_FLOAT3, -600, -200, "Roof base")
    rough = custom_node(mat, ROOF_HLSL_ROUGH, [("Seed", seed)], out.CMOT_FLOAT1, -600, 0, "Roof roughness")
    code = (SURFACE_AXES_HLSL + ROOF_HLSL_NORMAL).replace("STRENGTH", f"{ROOF_NORMAL_STRENGTH:.3f}")
    normal = custom_node(mat, code, [("Seed", seed), ("N", nrm), ("KN", s["RoofKawara"][1]), ("MN", s["RoofMetal"][1]),
                                     ("CN", s["Concrete"][1])], out.CMOT_FLOAT3, -600, 400, "Roof normal (world)")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)


def setup_buildings(doc, meshes):
    """建物の壁と屋根の絵を取り込み、メッシュの FD_BuildingWall / FD_BuildingRoof のスロットを、
    窓を描く壁のマテリアルと屋根のマテリアルに差し替える。
    窓の格子は UV で決まるので、UV は 32bit のまま持つ (16bit だと窓の縁がずれる)。ライトマップ用の UV は作らない (Lumen)。"""
    names = [n for n, m in meshes.items() if m is not None and n.startswith("SM_FD_Buildings")]
    if not names or night_assets.collection is None:
        return
    folder = os.path.dirname(SCENERY_JSON)
    for kind, (color, normal, size_m) in (doc.get("building_textures") or {}).items():
        c = import_tree_texture(os.path.join(folder, color), directory=BUILDING_TEXTURE_DIR)
        n = import_tree_texture(os.path.join(folder, normal), normal=True, directory=BUILDING_TEXTURE_DIR)
        if c and n:
            building_assets.textures[kind] = (c, n, float(size_m))
    need = {"WallSiding", "WallPlaster", "RoofKawara", "RoofMetal", "Concrete"}
    if not need <= set(building_assets.textures):
        unreal.log_warning("[setup_project] 建物の絵が足りません (tools/terrain/build_scenery.py を実行し直してください)")
        return
    tex = [[t.get_path_name() for t in building_assets.textures[k][:2]] + [building_assets.textures[k][2]]
           for k in sorted(building_assets.textures)]
    extra = [night_assets.collection.get_path_name(), [n for n, _ in NIGHT_PARAMS], tex]
    swap = {"FD_BuildingWall": create_material("M_FD_BuildingWall", build_building_wall_graph, extra=extra),
            "FD_BuildingRoof": create_material("M_FD_BuildingRoof", build_building_roof_graph, extra=extra)}
    # コマンドライン (UnrealEditor-Cmd) ではエディタのサブシステムが無いので、古い EditorStaticMeshLibrary を使う
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem) or unreal.EditorStaticMeshLibrary
    for name in names:
        mesh = meshes[name]
        changed = []
        for i, slot in enumerate(mesh.get_editor_property("static_materials")):
            slot_names = [str(slot.get_editor_property("material_slot_name"))]
            current = slot.get_editor_property("material_interface")
            if current:
                slot_names.append(current.get_name())
            for kind, mat in swap.items():
                if any(re.fullmatch(rf"(?:\w*_)?{kind}(?:_\d+)?", n) for n in slot_names):
                    if current != mat:
                        mesh.set_material(i, mat)
                        changed.append(kind)
                    break
        try:
            bs = sub.get_lod_build_settings(mesh, 0)
            if not bs.get_editor_property("use_full_precision_u_vs") or bs.get_editor_property("generate_lightmap_u_vs"):
                bs.set_editor_property("use_full_precision_u_vs", True)
                bs.set_editor_property("generate_lightmap_u_vs", False)
                sub.set_lod_build_settings(mesh, 0, bs)
                changed.append("UV 32bit")
        except Exception as e:
            unreal.log_warning(f"[setup_project] {name} の UV の精度を設定できませんでした: {e}")
        if changed:
            eal.save_loaded_asset(mesh)
            log(f"建物のマテリアル: {name} ({', '.join(changed)})")


def setup_night():
    """夜のパラメータ (MPC)、空のマテリアル、防犯灯の光る面のマテリアルを作る。"""
    mpc = create_night_collection()
    extra = [mpc.get_path_name(), [n for n, _ in NIGHT_PARAMS]]
    night_assets.sky = create_material("M_FD_Sky", build_sky_graph, extra=extra)
    night_assets.lamp_glow = create_material("M_FD_LampGlow", build_lamp_glow_graph, extra=extra)


def setup_lamp_glow(meshes):
    """景観物のメッシュの FD_LampGlow のスロットを、夜に光るマテリアルに差し替える。"""
    if night_assets.lamp_glow is None:
        return
    for name, mesh in meshes.items():
        if mesh is None:
            continue
        changed = False
        for i, slot in enumerate(mesh.get_editor_property("static_materials")):
            names = [str(slot.get_editor_property("material_slot_name"))]
            current = slot.get_editor_property("material_interface")
            if current:
                names.append(current.get_name())
            if any(re.fullmatch(r"(?:\w*_)?FD_LampGlow(?:_\d+)?", n) for n in names) and current != night_assets.lamp_glow:
                mesh.set_material(i, night_assets.lamp_glow)
                changed = True
        if changed:
            eal.save_loaded_asset(mesh)
            log(f"防犯灯のマテリアル: {name}")


def place_sky_dome(eas):
    """星空を描く空の球 (半径 SKY_DOME_RADIUS_CM)。影・当たり判定・Lumen の対象にしない。"""
    if night_assets.sky is None:
        return
    dome = spawn(eas, unreal.StaticMeshActor, (0, 0, 0), label="SkyDome (星空)", folder="Auto/Sky")
    comp = dome.static_mesh_component
    comp.set_static_mesh(eal.load_asset("/Engine/BasicShapes/Sphere"))  # 半径 50 cm
    comp.set_material(0, night_assets.sky)
    no_collision(comp)
    for name, v in (("cast_shadow", False), ("affect_distance_field_lighting", False),
                    ("affect_dynamic_indirect_lighting", False), ("visible_in_ray_tracing", False)):
        try:
            comp.set_editor_property(name, v)
        except Exception as e:
            unreal.log_warning(f"[setup_project] SkyDome の {name} を設定できませんでした: {e}")
    s = SKY_DOME_RADIUS_CM / 50.0
    dome.set_actor_scale3d(unreal.Vector(s, s, s))


def place_night_lights(eas, doc):
    """夜に点く光源 (scenery.json の lights) を FDNightLights に入れて置く。"""
    lights = (doc or {}).get("lights") or {}
    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDNightLights")
    if cls is None:
        if lights:
            unreal.log_warning("[setup_project] FDNightLights がありません (C++ をビルドしてから実行し直してください)。防犯灯の光は置きません")
        return
    for kind, items in lights.items():
        if not items:
            continue
        a = spawn(eas, cls, at((0, 0, 0)), label=f"NightLights ({kind})", folder="Auto/Road")
        transforms = [unreal.Transform(location=unreal.Vector(*at(it[:3])),
                                       rotation=unreal.Rotator(pitch=it[4], yaw=it[3], roll=0.0))
                      for it in items]
        a.set_editor_property("lights", transforms)
        try:
            a.rerun_construction_scripts()
        except Exception:
            pass  # 詳細パネルで値を変えたときと同じく、エディタが作り直す
        log(f"夜の光源: {kind} {len(items)}")


# ---------------------------------------------------------------- レベル
def open_or_create_level():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if eal.does_asset_exist(MAP_PATH):
        les.load_level(MAP_PATH)
        log(f"既存レベルを開きました: {MAP_PATH}")
    else:
        les.new_level(MAP_PATH)
        log(f"レベルを作成: {MAP_PATH}")
    return les


def clear_auto_actors(eas):
    for a in eas.get_all_level_actors():
        if a.actor_has_tag(AUTO_TAG):
            eas.destroy_actor(a)


# 一周コースで今置いているタイル。タイルのデータはタイルの中心が原点なので、置くときに offset だけずらし、
# 置いたアクターに tags の印を付ける (そのタイルの分だけ置き直せるように)
placing = types.SimpleNamespace(offset=(0.0, 0.0, 0.0), tags=[], folder="", data_dir="")


def at(loc):
    """タイルの中の位置 (cm) -> レベルの位置。"""
    o = placing.offset
    return (loc[0] + o[0], loc[1] + o[1], (loc[2] if len(loc) > 2 else 0.0) + o[2])


def spawn(eas, cls, loc=(0, 0, 0), rot=(0, 0, 0), label=None, folder="Auto"):
    # rot は (pitch, yaw, roll)。unreal.Rotator の位置引数は (roll, pitch, yaw) の順なのでキーワードで渡す
    a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]))
    a.tags = list(a.tags) + [AUTO_TAG] + list(placing.tags)
    if placing.folder:
        folder = placing.folder + "/" + folder.split("/", 1)[-1]
    if label:
        a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def load_json(name):
    path = os.path.join(placing.data_dir or DATA_DIR, name)
    if not os.path.exists(path):
        unreal.log_warning(f"[setup_project] {path} がありません (tools/terrain を先に実行)")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def first_component(actor, cls):
    comps = actor.get_components_by_class(cls)
    return comps[0] if comps else None


def place_sky(eas):
    sun_cls = unreal.EditorAssetLibrary.load_blueprint_class("/SunPosition/SunSky")
    if sun_cls is None:
        unreal.log_error("[setup_project] SunSky が見つかりません。SunPosition プラグインを有効にしてください")
    else:
        sun = spawn(eas, sun_cls, label="SunSky (二見ヶ浦の夕日)", folder="Auto/Sky")
        set_props(sun, Latitude=LATITUDE, Longitude=LONGITUDE, TimeZone=TIME_ZONE,
                  Month=MONTH, Day=DAY, SolarTime=SOLAR_TIME, NorthOffset=NORTH_OFFSET - COURSE.rotation,
                  UseDaylightSavingTime=False)
        try:
            sun.call_method("UpdateSun")
        except Exception:
            pass
        tune_sunsky(sun)

    fog = spawn(eas, unreal.ExponentialHeightFog, (0, 0, 0), label="HeightFog", folder="Auto/Sky")
    fog_comp = first_component(fog, unreal.ExponentialHeightFogComponent)
    if fog_comp:
        set_props(fog_comp, **FOG)
        glow = unreal.LinearColor(*FOG_SUN_GLOW, 1.0)
        set_props(fog_comp, DirectionalInscatteringLuminance=glow)
    spawn(eas, unreal.VolumetricCloud, (0, 0, 0), label="VolumetricCloud", folder="Auto/Sky")
    place_sky_dome(eas)
    place_post_process(eas)
    place_time_of_day(eas)


def place_time_of_day(eas):
    """時刻の切り替え (C++ の FDTimeOfDay)。置かなくても GameMode がプレイ開始時に置くが、
    レベルにあれば詳細パネルで時刻ごとの見た目や月の位置を調整して保存できる。"""
    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDTimeOfDay")
    if cls is None:
        unreal.log_warning("[setup_project] FDTimeOfDay がありません (C++ をビルドしてから実行し直してください)")
        return
    tod = spawn(eas, cls, (0, 0, 0), label="TimeOfDay (時刻の切り替え)", folder="Auto/Sky")
    # 夜空の街明かりは糸島から見た福岡市・前原の方向なので、コースの "features" で切ったら消す
    if not course_config.features_of(COURSE)["city_glow"]:
        set_props(tod, CityGlowBrightness=0.0)


def tune_sunsky(sun):
    """SunSky の中の大気・太陽光・空の光を夕景向けにする。"""
    atmo = first_component(sun, unreal.SkyAtmosphereComponent)
    if atmo:
        set_props(atmo, MieScatteringScale=SKY_MIE_SCATTERING_SCALE,
                  AerialPespectiveViewDistanceScale=SKY_AERIAL_PERSPECTIVE_SCALE)
    light = first_component(sun, unreal.DirectionalLightComponent)
    if light:
        # 大気で夕日を赤くし、雲や山のすき間から光の筋が出るようにする
        set_props(light, AtmosphereSunLight=True, EnableLightShaftOcclusion=True, EnableLightShaftBloom=True,
                  BloomScale=0.15, BloomThreshold=4.0)
    sky = first_component(sun, unreal.SkyLightComponent)
    if sky:
        set_props(sky, RealTimeCapture=True)  # 空の色の変化を地面の陰の色に反映する


def place_post_process(eas):
    """画面全体の露出・ブルーム・周辺減光。境界なし (どこにいても効く)。"""
    ppv = spawn(eas, unreal.PostProcessVolume, (0, 0, 0), label="PostProcess (時刻で変わる)", folder="Auto/Sky")
    ppv.set_editor_property("unbound", True)
    st = ppv.get_editor_property("settings")
    values = dict(auto_exposure_method=unreal.AutoExposureMethod.AEM_HISTOGRAM,
                  auto_exposure_min_brightness=EXPOSURE_MIN_EV100,
                  auto_exposure_max_brightness=EXPOSURE_MAX_EV100,
                  auto_exposure_speed_up=2.0, auto_exposure_speed_down=1.0,
                  bloom_intensity=0.45, lens_flare_intensity=0.0, vignette_intensity=0.35,
                  motion_blur_amount=0.1)
    for name, v in values.items():
        try:
            st.set_editor_property(name, v)
            st.set_editor_property("override_" + name, True)
        except Exception as e:
            unreal.log_warning(f"[setup_project] PostProcess {name} を設定できませんでした: {e}")
    ppv.set_editor_property("settings", st)


def no_collision(comp):
    # set_collision_enabled だけだとプロファイル (BlockAll) のままで、レベルを開き直すと当たり判定が戻る
    comp.set_collision_profile_name("NoCollision")
    comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)


def sea_plane(eas, material, center, size_cm, label, z=0.0):
    plane = spawn(eas, unreal.StaticMeshActor, (center[0], center[1], z), label=label, folder="Auto/Sea")
    comp = plane.static_mesh_component
    comp.set_static_mesh(eal.load_asset("/Engine/BasicShapes/Plane"))  # 100 x 100 cm の板
    comp.set_material(0, material)
    comp.set_editor_property("cast_shadow", False)
    no_collision(comp)  # 見た目だけ。バイクが板の上に乗らないように
    plane.set_actor_scale3d(unreal.Vector(size_cm[0] / 100, size_cm[1] / 100, 1.0))
    return plane


def place_far_sea(eas, material, zone=None):
    """WaterZone (= Ocean Extents) の外側に、額縁状に4枚の板を置く。zone は WaterZone の (x0, y0, x1, y1) cm。"""
    h = SEA_ZONE_EXTENT_CM / 2
    x0, y0, x1, y1 = zone or (-h, -h, h, h)
    o = SEA_FAR_HALF_CM
    z = SEA_FAR_Z_CM
    sea_plane(eas, material, ((x1 + o) / 2, 0), (o - x1, 2 * o), "FarSea East", z)
    sea_plane(eas, material, ((x0 - o) / 2, 0), (x0 + o, 2 * o), "FarSea West", z)
    sea_plane(eas, material, ((x0 + x1) / 2, (y1 + o) / 2), (x1 - x0, o - y1), "FarSea South", z)
    sea_plane(eas, material, ((x0 + x1) / 2, (y0 - o) / 2), (x1 - x0, y0 + o), "FarSea North", z)


def place_sea(eas, sea_material, zone=None, resolution=SEA_ZONE_RESOLUTION):
    """Water プラグインの Ocean を Z=0 に置く。地形は削らず、海底はランドスケープのまま透けて見える。
    zone は WaterZone の (x0, y0, x1, y1) cm (無ければ原点を中心に SEA_ZONE_EXTENT_CM 四方)。"""
    h = SEA_ZONE_EXTENT_CM / 2
    zone = zone or (-h, -h, h, h)
    center = ((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)
    extent = (zone[2] - zone[0], zone[3] - zone[1])
    if not hasattr(unreal, "WaterBodyOcean"):
        unreal.log_warning("[setup_project] Water プラグインが無いため、仮の海面 (板) を置きます")
        size = SEA_FALLBACK_SIZE_M * 100
        sea_plane(eas, sea_material, (0, 0), (size, size), "Sea (仮の海面)")
        return

    ocean = spawn(eas, unreal.WaterBodyOcean, (0, 0, 0), label="Ocean", folder="Auto/Sea")
    h = SEA_SPLINE_HALF_CM
    spline = ocean.get_water_spline()
    spline.set_spline_points([unreal.Vector(x, y, 0) for x, y in ((h, -h), (h, h), (-h, h), (-h, -h))],
                             unreal.SplineCoordinateSpace.WORLD)
    for i in range(spline.get_number_of_spline_points()):  # 既定の曲線だと角が丸まり、地形の上を横切る
        spline.set_spline_point_type(i, unreal.SplinePointType.LINEAR, True)
    body = ocean.get_water_body_component()
    body.set_editor_property("affects_landscape", False)  # ランドスケープを削ったり盛ったりしない
    # 既定の波は最大 5m あり、海岸の道路 (海面 +0.5m 以上) が水に沈むので、小さい波に差し替える
    if OCEAN_USE_CUSTOM_WAVES:
        apply_waves(ocean, body)
    else:
        ocean.set_water_waves(None)
    if OCEAN_USE_CUSTOM_MATERIAL:
        apply_ocean_material(body)
    # Ocean は原点 (陸の上の小さな四角) にあるので、WaterZone が原点からずれていても覆えるよう広げる
    ocean_ext = (extent[0] + 2 * abs(center[0]), extent[1] + 2 * abs(center[1]))
    body.set_editor_property("ocean_extents", unreal.Vector2D(*ocean_ext))
    body.set_editor_property("collision_extents", unreal.Vector(ocean_ext[0] / 2, ocean_ext[1] / 2, 10000.0))

    # Ocean を置くと WaterZone が自動でできる。再実行で置き直せるよう印をつける
    for wz in eas.get_all_level_actors():
        if wz.get_class().get_name() != "WaterZone":
            continue
        if not wz.actor_has_tag(AUTO_TAG):
            wz.tags = list(wz.tags) + [AUTO_TAG] + list(placing.tags)
        wz.set_folder_path("Auto/Sea")
        wz.set_actor_location(unreal.Vector(center[0], center[1], 0), False, False)
        wz.set_editor_property("zone_extent", unreal.Vector2D(*extent))
        wz.set_editor_property("render_target_resolution", unreal.IntPoint(resolution, resolution))
    place_far_sea(eas, sea_material, zone)
    log(f"海: Ocean (Z=0)、WaterZone {extent[0] / 100000:.1f} x {extent[1] / 100000:.1f} km、"
        f"遠景の板 {SEA_FAR_HALF_CM * 2 / 100000:.0f} km 四方")


def ensure_waves_asset(ocean):
    """Ocean に既定で付く波アセットを複製して使う (エンジン側のアセットは書き換えない)。"""
    path = f"{WATER_DIR}/FD_OceanWaves"
    if eal.does_asset_exist(path):
        return eal.load_asset(path)
    src = None
    try:
        ref = ocean.get_editor_property("water_waves")
        src = ref.get_editor_property("water_waves_asset") if ref else None
    except Exception:
        pass
    src_path = src.get_path_name().split(".")[0] if src else DEFAULT_WAVES_ASSET
    if not eal.does_asset_exist(src_path):
        unreal.log_warning(f"[setup_project] 既定の波アセット {src_path} が見つかりません。波なしにします")
        return None
    asset = eal.duplicate_asset(src_path, path)
    log(f"波アセットを複製: {src_path} -> {path}")
    return asset


def configure_waves(asset, scale=1.0):
    # UE5.8 の WaterWavesAsset では snake_case の "water_waves" では取れず、元の名前でだけ取れる
    gerstner = asset.get_editor_property("WaterWaves")
    old = gerstner.get_editor_property("GerstnerWaveGenerator")
    # 同じ生成器の値を変えて設定し直しても波は計算し直されない。新しい生成器に差し替えると計算し直される
    gen = unreal.new_object(old.get_class(), outer=gerstner)
    params = dict(WAVES)
    params["MinAmplitude"] *= scale
    params["MaxAmplitude"] *= scale
    set_props(gen, **params)
    gerstner.set_editor_property("GerstnerWaveGenerator", gen)
    asset.set_editor_property("WaterWaves", gerstner)


def set_waves_asset(ocean, asset):
    # Ocean には既定で WaterWavesAssetReference が付いている。このクラスは Python に公開されていないので、
    # 無いときだけクラスをパスで読み込んで作る
    ref = ocean.get_editor_property("water_waves")
    if ref is None or ref.get_class().get_name() != "WaterWavesAssetReference":
        ref = unreal.new_object(unreal.load_class(None, "/Script/Water.WaterWavesAssetReference"), outer=ocean)
    set_props(ref, WaterWavesAsset=asset)
    ocean.set_water_waves(ref)


def apply_waves(ocean, body):
    asset = ensure_waves_asset(ocean)
    if asset is None:
        ocean.set_water_waves(None)
        return
    path = f"{WATER_DIR}/FD_OceanWaves"
    digest = recipe(apply_waves)
    if state.fresh(path, digest, path):   # 波は前回と同じ。アセットはそのまま使う
        set_waves_asset(ocean, asset)
        return
    scale = 1.0
    height = None
    for _ in range(5):
        configure_waves(asset, scale)
        set_waves_asset(ocean, asset)
        try:
            height = body.get_max_wave_height()
        except Exception:
            break
        if height <= WAVE_MAX_HEIGHT_CM:
            break
        scale *= WAVE_MAX_HEIGHT_CM / height * 0.95
    if height is not None and height > WAVE_MAX_HEIGHT_CM:
        # 小さくできなかったときは、道路が沈まないよう波なしにする
        unreal.log_warning(f"[setup_project] 波を {WAVE_MAX_HEIGHT_CM:.0f} cm 以下にできなかったため (現在 {height:.0f} cm)、波なしにします")
        ocean.set_water_waves(None)
        height = body.get_max_wave_height()
    eal.save_loaded_asset(asset)
    state.done(path, digest)
    log(f"波: 最大の高さ {height:.0f} cm" if height is not None else "波: 設定しました (高さは取得できず)")


def apply_ocean_material(body):
    """Ocean の既定マテリアルの子 (マテリアルインスタンス) を作り、色だけ変える。"""
    parent = body.get_editor_property("water_material")
    if parent is None:
        unreal.log_warning("[setup_project] Ocean のマテリアルが取得できませんでした")
        return
    path = f"{WATER_DIR}/MI_FD_Ocean"
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = asset_tools.create_asset("MI_FD_Ocean", WATER_DIR, unreal.MaterialInstanceConstant,
                                      unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)  # Ocean は毎回置き直すので、parent は常にエンジン既定のマテリアル
    names = [str(n) for n in mel.get_vector_parameter_names(mi)]
    log(f"Ocean マテリアルの色パラメータ: {', '.join(names)}")
    mel.clear_all_material_instance_parameters(mi)  # 以前の実行で上書きした値を消し、既定値から始める
    for name, rgb in (("Absorption", OCEAN_ABSORPTION), ("Scattering", OCEAN_SCATTERING)):
        if rgb is None:
            continue
        if name in names:
            mel.set_material_instance_vector_parameter_value(mi, name, unreal.LinearColor(*rgb, 1.0))
        else:
            unreal.log_warning(f"[setup_project] Ocean マテリアルに {name} がありません (色は既定のまま)")
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi)
    body.set_editor_property("water_material", mi)


def place_landmarks(eas):
    doc = load_json("landmarks.json")
    if not doc:
        return
    for lm in doc["landmarks"]:
        spawn(eas, unreal.TargetPoint, at(lm["location_cm"]), label=f"目印: {lm['name']}", folder="Auto/Landmarks")
    log(f"目印 {len(doc['landmarks'])} 件")


def place_player_start(eas):
    """県道54号の、夫婦岩にいちばん近い点に道路の向きで置く。"""
    roads = load_json("roads.json")
    lms = load_json("landmarks.json")
    if not roads:
        return
    target = (0.0, 0.0)
    if lms:
        for lm in lms["landmarks"]:
            if "夫婦岩" in lm["name"]:
                target = tuple(lm["location_cm"][:2])
    best = None
    for r in roads["roads"]:
        if r["priority"] > 1:
            continue
        pts = r["points_cm"]
        for i in range(len(pts) - 1):
            d = (pts[i][0] - target[0]) ** 2 + (pts[i][1] - target[1]) ** 2
            if best is None or d < best[0]:
                best = (d, pts[i], pts[i + 1], r)
    if best is None:
        unreal.log_warning("[setup_project] 主要道路が見つからないため PlayerStart を原点に置きます")
        spawn(eas, unreal.PlayerStart, (0, 0, 1000), label="PlayerStart", folder="Auto")
        return
    _, p0, p1, r = best
    import math
    yaw = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    spawn(eas, unreal.PlayerStart, (p0[0], p0[1], p0[2] + 150), (0, yaw, 0), label="PlayerStart", folder="Auto")
    log(f"PlayerStart: {r['name'] or r['highway']} 上 ({p0[0]:.0f}, {p0[1]:.0f}, {p0[2]:.0f})")


# ---------------------------------------------------------------- 景観物
def import_scenery_mesh(name, gltf_path, directory=SCENERY_DIR, nanite=SCENERY_NANITE):
    """glTF を directory (既定は /Game/FukuokaDrive/Scenery) に取り込み、StaticMesh を返す。"""
    # glTF の取り込み (Interchange) はメッシュを <名前>/StaticMeshes/<名前> に置く
    path = f"{directory}/{name}/StaticMeshes/{name}"
    if not eal.does_asset_exist(path):
        path = f"{directory}/{name}"
    digest = recipe(import_scenery_mesh, nanite, files=[gltf_path])
    if eal.does_asset_exist(path) and (not REIMPORT_SCENERY or state.fresh(path, digest, path)):
        return eal.load_asset(path)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", gltf_path)
    task.set_editor_property("destination_path", directory)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    asset_tools.import_asset_tasks([task])
    mesh = None
    for p in task.get_editor_property("imported_object_paths") or []:
        obj = eal.load_asset(p)
        if isinstance(obj, unreal.StaticMesh):
            mesh = obj
    if mesh is None and eal.does_asset_exist(path):
        mesh = eal.load_asset(path)
    if mesh is None:
        unreal.log_warning(f"[setup_project] {gltf_path} を取り込めませんでした")
        return None
    if nanite:
        enable_nanite(mesh)
    eal.save_loaded_asset(mesh)
    # 初めて取り込むときは、取り込み先の本当のパス (<名前>/StaticMeshes/<名前>) で記録する
    path = mesh.get_path_name().split(".")[0]
    state.done(path, digest)
    log(f"取り込み: {path}")
    return mesh


def enable_nanite(mesh):
    try:
        settings = mesh.get_editor_property("nanite_settings")
        if settings.get_editor_property("enabled"):
            return
        settings.set_editor_property("enabled", True)
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if hasattr(sub, "set_nanite_settings"):
            sub.set_nanite_settings(mesh, settings, True)
        else:
            mesh.set_editor_property("nanite_settings", settings)
    except Exception as e:
        unreal.log_warning(f"[setup_project] {mesh.get_name()} を Nanite にできませんでした: {e}")


def place_mesh(eas, mesh, loc, yaw, label, folder):
    a = spawn(eas, unreal.StaticMeshActor, tuple(loc), (0, yaw, 0), label=label, folder=folder)
    comp = a.static_mesh_component
    comp.set_static_mesh(mesh)
    no_collision(comp)  # バイクの接地判定に引っかからないように
    return a


def place_instances(eas, cls, mesh, items, label, folder, stretch_x=False, no_shadow=False):
    """items は [x, y, z, yaw, 拡大率 (, pitch)]。stretch_x なら X だけ拡大する (ガードレール・区画線・電線の長さ)。"""
    a = spawn(eas, cls, at((0, 0, 0)), label=label, folder=folder)
    comp = first_component(a, unreal.InstancedStaticMeshComponent)
    comp.set_static_mesh(mesh)
    if no_shadow:
        comp.set_editor_property("cast_shadow", False)
    transforms = [unreal.Transform(location=unreal.Vector(it[0], it[1], it[2]),
                                   rotation=unreal.Rotator(pitch=it[5] if len(it) > 5 else 0.0, yaw=it[3], roll=0),
                                   scale=unreal.Vector(it[4], 1.0, 1.0) if stretch_x else unreal.Vector(it[4], it[4], it[4]))
                  for it in items]
    comp.add_instances(transforms, False, False)   # アクター (タイルの中心) からの位置
    return a


def build_foliage_graph(mat):
    """葉の板のマテリアル。葉の絵 (パラメータ Leaf) x 樹冠の奥の陰 (頂点の色 R) x 木ごとのばらつき。透明な所は切り抜く。
    葉の板は表と裏を別の面で作ってあるので、片面のマテリアルでよい。"""
    sm_enum = unreal.MaterialShadingModel
    foliage = getattr(sm_enum, "MSM_TWO_SIDED_FOLIAGE", None) or getattr(sm_enum, "MSM_TWOSIDED_FOLIAGE")
    set_props(mat, blend_mode=unreal.BlendMode.BLEND_MASKED, shading_model=foliage, opacity_mask_clip_value=FOLIAGE_CLIP)
    for usage in ("used_with_instanced_static_meshes", "used_with_nanite"):
        try:
            mat.set_editor_property(usage, True)
        except Exception:
            pass
    tex = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -1200, 0)
    tex.set_editor_property("parameter_name", "Leaf")
    default = "/Engine/EngineResources/DefaultTexture"
    if eal.does_asset_exist(default):
        tex.set_editor_property("texture", eal.load_asset(default))
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -1200, 300)
    ao = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -950, 300)
    mel.connect_material_expressions(scalar(mat, FOLIAGE_AO_MIN, -1100, 250), "", ao, "A")
    mel.connect_material_expressions(scalar(mat, 1.0, -1100, 280), "", ao, "B")
    mel.connect_material_expressions(vc, "R", ao, "Alpha")
    rnd = mel.create_material_expression(mat, unreal.MaterialExpressionPerInstanceRandom, -1200, 450)
    var = lerp(mat, scalar(mat, FOLIAGE_INSTANCE_VARIATION[0], -1100, 420), scalar(mat, FOLIAGE_INSTANCE_VARIATION[1], -1100, 470),
               rnd, -950, 450)
    tinted = multiply(mat, tex, vector_param(mat, "Tint", (1.0, 1.0, 1.0), -1200, -200), -900, 0)  # tex の最初の出力は RGB
    base = multiply(mat, multiply(mat, tinted, ao, -700, 100), var, -500, 100)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(multiply(mat, base, scalar(mat, FOLIAGE_TRANSMISSION, -500, 250), -300, 250), "",
                                  unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(tex, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.connect_material_property(scalar(mat, FOLIAGE_ROUGHNESS, -300, 400), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, FOLIAGE_SPECULAR, -300, 480), "", unreal.MaterialProperty.MP_SPECULAR)


def build_bark_graph(mat):
    """樹皮のマテリアル。色 (パラメータ Color) と凹凸 (パラメータ Normal、ノーマルマップ)。"""
    try:
        mat.set_editor_property("used_with_instanced_static_meshes", True)
        mat.set_editor_property("used_with_nanite", True)
    except Exception:
        pass
    col = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -900, 0)
    col.set_editor_property("parameter_name", "Color")
    default = "/Engine/EngineResources/DefaultTexture"
    if eal.does_asset_exist(default):
        col.set_editor_property("texture", eal.load_asset(default))
    nrm = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -900, 300)
    nrm.set_editor_property("parameter_name", "Normal")
    nrm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    flat = "/Engine/EngineMaterials/DefaultNormal"
    if eal.does_asset_exist(flat):
        nrm.set_editor_property("texture", eal.load_asset(flat))
    rnd = mel.create_material_expression(mat, unreal.MaterialExpressionPerInstanceRandom, -900, 550)
    var = lerp(mat, scalar(mat, 0.85, -800, 500), scalar(mat, 1.1, -800, 600), rnd, -650, 550)
    base = multiply(mat, col, var, -500, 0)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nrm, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(scalar(mat, 0.9, -300, 400), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, 0.25, -300, 480), "", unreal.MaterialProperty.MP_SPECULAR)


def import_tree_texture(png, normal=False, directory=FOLIAGE_DIR):
    """木の絵 (葉の透過 PNG、樹皮の色と凹凸) を FOLIAGE_DIR に取り込む (絵が変わったときだけ)。
    アセットの名前はファイル名と同じ。normal=True ならノーマルマップとして取り込む (sRGB なし、法線用の圧縮)。"""
    name = os.path.splitext(os.path.basename(png))[0]
    path = f"{directory}/{name}"
    digest = recipe(import_tree_texture, normal, files=[png])
    if state.fresh(path, digest, path):
        return eal.load_asset(path)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", png)
    task.set_editor_property("destination_path", directory)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    asset_tools.import_asset_tasks([task])
    if not eal.does_asset_exist(path):
        unreal.log_warning(f"[setup_project] {png} を取り込めませんでした")
        return None
    texture = eal.load_asset(path)
    if normal:
        texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        texture.set_editor_property("srgb", False)
    eal.save_loaded_asset(texture)
    state.done(path, digest)
    log(f"取り込み: {path}")
    return texture


def tree_instance(kind, parent, textures):
    """kind (glTF のマテリアル名) のマテリアルインスタンス MI_<kind>。textures は {パラメータ名: テクスチャ}。"""
    name = f"MI_{kind}"
    path = f"{FOLIAGE_DIR}/{name}"
    digest = recipe(tree_instance, kind, parent.get_name(), sorted((k, t.get_path_name()) for k, t in textures.items()))
    if state.fresh(path, digest, path):
        return eal.load_asset(path)
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = asset_tools.create_asset(name, FOLIAGE_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    for param, texture in textures.items():
        mel.set_material_instance_texture_parameter_value(mi, param, texture)
    eal.save_loaded_asset(mi)
    state.done(path, digest)
    log(f"作成: {path}")
    return mi


def setup_foliage(doc, meshes):
    """葉の絵と樹皮の絵を取り込み、葉と樹皮のマテリアルを作って、木のメッシュのスロットを差し替える。"""
    leaves = doc.get("leaf_textures") or {}
    barks = doc.get("bark_textures") or {}
    if not leaves and not barks:
        return
    folder = os.path.dirname(SCENERY_JSON)
    instances = {}
    if leaves:
        parent = create_material("M_FD_Foliage", build_foliage_graph, FOLIAGE_DIR)
        for kind, fname in leaves.items():
            tex = import_tree_texture(os.path.join(folder, fname))
            if tex:
                instances[kind] = tree_instance(kind, parent, {"Leaf": tex})
    if barks:
        parent = create_material("M_FD_Bark", build_bark_graph, FOLIAGE_DIR)
        for kind, (color, normal) in barks.items():
            c = import_tree_texture(os.path.join(folder, color))
            n = import_tree_texture(os.path.join(folder, normal), normal=True)
            if c and n:
                instances[kind] = tree_instance(kind, parent, {"Color": c, "Normal": n})
    for name, mesh in meshes.items():
        if mesh is None:
            continue
        changed, leafy = [], False
        for i, slot in enumerate(mesh.get_editor_property("static_materials")):
            names = [str(slot.get_editor_property("material_slot_name"))]
            current = slot.get_editor_property("material_interface")
            if current:
                names.append(current.get_name())
            # glTF のマテリアル名のスロット。取り込みで前に MI_ など、後ろに番号が付くことがある (FD_Bark は FD_BarkCedar に一致させない)
            for kind, mi in instances.items():
                if any(re.fullmatch(rf"(?:\w*_)?{kind}(?:_\d+)?", n) for n in names):
                    leafy = leafy or kind.startswith(("FD_Leaf_", "FD_Flower_"))
                    if current != mi:
                        mesh.set_material(i, mi)
                        changed.append(kind)
                    break
        if leafy and preserve_nanite_area(mesh):
            changed.append("Nanite Preserve Area")
        if changed:
            eal.save_loaded_asset(mesh)
            log(f"木のマテリアル: {name} ({', '.join(changed)})")


def preserve_nanite_area(mesh):
    """遠くで Nanite が面を減らしても、葉の板の面積 (茂りぐあい) を保つ。変えたら True。"""
    try:
        settings = mesh.get_editor_property("nanite_settings")
        # UE 5.5 から bPreserveArea は ShapePreservation (列挙) に置き換わった
        if hasattr(unreal, "NaniteShapePreservation"):
            want = unreal.NaniteShapePreservation.PRESERVE_AREA
            if settings.get_editor_property("shape_preservation") == want:
                return False
            settings.set_editor_property("shape_preservation", want)
        else:
            if settings.get_editor_property("preserve_area"):
                return False
            settings.set_editor_property("preserve_area", True)
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if hasattr(sub, "set_nanite_settings"):
            sub.set_nanite_settings(mesh, settings, True)
        else:
            mesh.set_editor_property("nanite_settings", settings)
        return True
    except Exception as e:
        unreal.log_warning(f"[setup_project] {mesh.get_name()} の Nanite Preserve Area を設定できませんでした: {e}")
        return False


SCENERY_JSON = os.path.join(DATA_DIR, "scenery", "scenery.json")


def import_scenery():
    """景観物のメッシュを取り込み、(scenery.json の中身, {名前: StaticMesh}) を返す。"""
    folder = os.path.dirname(SCENERY_JSON)
    if not os.path.exists(SCENERY_JSON):
        unreal.log_warning(f"[setup_project] {SCENERY_JSON} がありません (tools/terrain/build_scenery.py を先に実行)")
        return None, {}
    with open(SCENERY_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    meshes = {}
    for name, fname in doc["meshes"].items():
        meshes[name] = import_scenery_mesh(name, os.path.join(folder, fname))
    setup_foliage(doc, meshes)
    setup_lamp_glow(meshes)
    setup_buildings(doc, meshes)
    return doc, meshes


def place_scenery(eas, doc, meshes):
    """夫婦岩・しめ縄・鳥居 (1つずつ) と、ガードレール・木・花 (FDInstances でまとめて並べる)。"""
    if not doc:
        return
    meoto = doc.get("meoto")
    if meoto:
        for r in meoto["rocks"]:
            if meshes.get(r["mesh"]):
                place_mesh(eas, meshes[r["mesh"]], at(r["location_cm"]), r["yaw"], f"夫婦岩 ({r['name']})", "Auto/Meoto")
        rope = meoto["rope"]
        if meshes.get(rope["mesh"]):
            place_mesh(eas, meshes[rope["mesh"]], at(rope["location_cm"]), 0.0, "しめ縄", "Auto/Meoto")
        t = meoto["torii"]
        if meshes.get(t["mesh"]):
            place_mesh(eas, meshes[t["mesh"]], at(t["location_cm"]), t["yaw"], "鳥居", "Auto/Meoto")
        log(f"夫婦岩と鳥居を置きました (しめ縄 {rope['length_m']:.0f} m)")

    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDInstances")
    if cls is None:
        unreal.log_warning("[setup_project] FDInstances がありません (C++ をビルドしてから実行し直してください)。木とガードレールは置きません")
        return
    # 道路に沿ってつながった形 (ガードレールのビーム・区画線・側溝)。形の座標がそのまま UE の座標なので原点に1つ置く
    for name, opt in doc.get("world_meshes", {}).items():
        if meshes.get(name):
            a = place_mesh(eas, meshes[name], at((0, 0, 0)), 0.0, name.replace("SM_FD_", ""),
                           "Auto/Guardrail" if "Guardrail" in name else "Auto/Buildings" if "Buildings" in name
                           else "Auto/Shrines" if name.startswith("SM_FD_Shrine") else "Auto/Road")
            if not opt.get("shadow", True):
                a.static_mesh_component.set_editor_property("cast_shadow", False)

    counts = []
    stretch = doc.get("stretch_x", [])
    seasons, cull = doc.get("seasons", {}), doc.get("cull_cm", {})
    for name, items in doc["instances"].items():
        if not items or not meshes.get(name):
            continue
        sub = ("Auto/Guardrail" if "Guardrail" in name else "Auto/Road" if name.startswith("SM_FD_Road")
               else "Auto/Shrines" if name.startswith("SM_FD_Shrine")
               else "Auto/Flowers" if name in seasons else "Auto/Trees")
        a = place_instances(eas, cls, meshes[name], items, name.replace("SM_FD_", ""), sub, name in stretch,
                            name in doc.get("no_shadow", []))
        if name in seasons:   # 花と桜: C++ が Y キーの季節に合わせて出し入れする
            set_props(a, SeasonMask=int(seasons[name]))
        if name in cull:      # 小さな花の株は遠くで消す (消える手前の 2 割で薄くする)
            comp = first_component(a, unreal.InstancedStaticMeshComponent)
            end = int(cull[name])
            for prop, value in (("instance_start_cull_distance", int(end * 0.8)), ("instance_end_cull_distance", end)):
                try:
                    comp.set_editor_property(prop, value)
                except Exception as e:
                    unreal.log_warning(f"[setup_project] {name} の {prop} を設定できませんでした: {e}")
        counts.append(f"{name.replace('SM_FD_', '')} {len(items)}")
    log("並べたもの: " + ", ".join(counts))


# ---------------------------------------------------------------- 草地の草
GRASS_FOLDER = os.path.join(DATA_DIR, "grass")


def build_grass_graph(mat):
    """草の葉のマテリアル。色は地面と同じ草地の色 x 根元の陰 (頂点の色 R) x 枯れた葉 (G) x 株ごとのばらつき。
    風でゆれ (葉先ほど大きく、B で葉ごとに時間をずらす)、消える距離の手前で地面に沈む。
    葉は表と裏を別の面で作ってあるので片面でよい。"""
    sm_enum = unreal.MaterialShadingModel
    foliage = getattr(sm_enum, "MSM_TWO_SIDED_FOLIAGE", None) or getattr(sm_enum, "MSM_TWOSIDED_FOLIAGE")
    set_props(mat, shading_model=foliage)
    try:
        mat.set_editor_property("used_with_instanced_static_meshes", True)
    except Exception:
        pass
    vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -1600, 600)
    c = grass_ground_color(mat, -1100, -900, vertex=True)
    ao = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -900, 500)
    mel.connect_material_expressions(scalar(mat, GRASS_ROOT_AO, -1100, 450), "", ao, "A")
    mel.connect_material_expressions(scalar(mat, GRASS_TIP_BRIGHT, -1100, 500), "", ao, "B")
    mel.connect_material_expressions(vc, "R", ao, "Alpha")
    g = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, -1400, 700)
    for ch, on in (("r", False), ("g", True), ("b", False), ("a", False)):
        g.set_editor_property(ch, on)
    mel.connect_material_expressions(vc, "", g, "")
    dry_blade = ramp(mat, g, 1.0 - GRASS_DRY_BLADES, 1.0, -1000, 700)
    c = lerp(mat, c, color(mat, GRASS_DRY_BLADE_COLOR, -900, 600), dry_blade, -700, 300)
    rnd = mel.create_material_expression(mat, unreal.MaterialExpressionPerInstanceRandom, -1100, 900)
    var = lerp(mat, scalar(mat, GRASS_INSTANCE_VARIATION[0], -1000, 850), scalar(mat, GRASS_INSTANCE_VARIATION[1], -1000, 950),
               rnd, -850, 900)
    base = multiply(mat, multiply(mat, c, ao, -550, 400), var, -400, 500)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(multiply(mat, base, scalar(mat, GRASS_TRANSMISSION, -400, 650), -250, 650), "",
                                  unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(scalar(mat, 0.65, -250, 750), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, 0.3, -250, 820), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(grass_wind(mat, vc, -250, 1100), "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)


def grass_wind(mat, vc, x, y):
    """草の WPO (cm)。風のゆれ (葉先ほど大きい) + 消える距離の手前で地面に沈める分。"""
    def sine(phase, yy):
        e = mel.create_material_expression(mat, unreal.MaterialExpressionSine, x - 300, yy)
        mel.connect_material_expressions(phase, "", e, "")
        return e

    def along(k, yy):
        """ワールドの位置を風の向きに測った値 x k (の小数部分。Sine は 1 周ごとに同じなので小数部分だけでよい)。
        ワールド座標は大きい (LWC) ので、先に掛けて Frac で小さな値にしてから足す。"""
        wpos = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, x - 1000, yy)
        scaled = multiply(mat, wpos, color(mat, (WIND_DIR[0] * k, WIND_DIR[1] * k, 0.0), x - 1000, yy + 80), x - 850, yy)
        frac = mel.create_material_expression(mat, unreal.MaterialExpressionFrac, x - 750, yy)
        mel.connect_material_expressions(scaled, "", frac, "")
        dot = mel.create_material_expression(mat, unreal.MaterialExpressionDotProduct, x - 650, yy)
        mel.connect_material_expressions(frac, "", dot, "A")
        mel.connect_material_expressions(color(mat, (1.0, 1.0, 0.0), x - 750, yy + 80), "", dot, "B")
        return dot

    time = mel.create_material_expression(mat, unreal.MaterialExpressionTime, x - 1100, y)
    b = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, x - 1100, y + 150)
    for ch, on in (("r", False), ("g", False), ("b", True), ("a", False)):
        b.set_editor_property(ch, on)
    mel.connect_material_expressions(vc, "", b, "")
    # Sine は 1 で 1 周する (Period = 1)
    phase = add(mat, add(mat, multiply(mat, time, scalar(mat, WIND_SPEED, x - 1000, y + 50), x - 800, y),
                         along(WIND_WAVE, y + 250), x - 500, y),
                multiply(mat, b, scalar(mat, 0.35, x - 1000, y + 200), x - 800, y + 150), x - 400, y)
    gust_phase = add(mat, multiply(mat, time, scalar(mat, GUST_SPEED, x - 1000, y + 450), x - 800, y + 400),
                     along(GUST_WAVE, y + 550), x - 500, y + 400)
    gust = add(mat, multiply(mat, sine(gust_phase, y + 400), scalar(mat, 0.5, x - 300, y + 480), x - 200, y + 400),
               scalar(mat, 0.5, x - 300, y + 520), x - 100, y + 400)
    sway = add(mat, multiply(mat, sine(phase, y), scalar(mat, 0.5, x - 300, y + 80), x - 200, y), gust, x - 50, y)
    r = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, x - 1100, y + 700)
    for ch, on in (("r", True), ("g", False), ("b", False), ("a", False)):
        r.set_editor_property(ch, on)
    mel.connect_material_expressions(vc, "", r, "")
    bendy = multiply(mat, r, r, x - 900, y + 700)   # 葉先ほど大きく (根元は動かない)
    amount = multiply(mat, multiply(mat, sway, bendy, x + 50, y + 200), scalar(mat, WIND_CM, x - 50, y + 300), x + 150, y + 250)
    wind = multiply(mat, amount, color(mat, (WIND_DIR[0], WIND_DIR[1], 0.0), x + 50, y + 350), x + 250, y + 300)
    fade_cls = getattr(unreal, "MaterialExpressionPerInstanceFadeAmount", None)
    if fade_cls is None:
        return wind
    fade = mel.create_material_expression(mat, fade_cls, x + 50, y + 500)
    sink = multiply(mat, fade, color(mat, (0.0, 0.0, -GRASS_SINK_CM), x + 50, y + 600), x + 250, y + 550)
    return add(mat, wind, sink, x + 400, y + 400)


def import_texture(png, directory, normal=False, linear=False):
    """PNG を directory に取り込む (絵が変わったときだけ)。名前はファイル名と同じ。
    normal=True ならノーマルマップ、linear=True なら色ではない値 (sRGB なし) として取り込む。
    (import_tree_texture と同じ処理。そちらを変えると木の絵がすべて取り込み直しになるので分けてある)"""
    name = os.path.splitext(os.path.basename(png))[0]
    path = f"{directory}/{name}"
    digest = recipe(import_texture, normal, linear, files=[png])
    if state.fresh(path, digest, path):
        return eal.load_asset(path)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", png)
    task.set_editor_property("destination_path", directory)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    asset_tools.import_asset_tasks([task])
    if not eal.does_asset_exist(path):
        unreal.log_warning(f"[setup_project] {png} を取り込めませんでした")
        return None
    texture = eal.load_asset(path)
    if normal:
        texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
    if normal or linear:
        texture.set_editor_property("srgb", False)
    eal.save_loaded_asset(texture)
    state.done(path, digest)
    log(f"取り込み: {path}")
    return texture


def per_platform(cls, value):
    v = cls()
    v.set_editor_property("default", value)
    return v


def set_struct(struct, **props):
    for name, value in props.items():
        try:
            struct.set_editor_property(name, value)
        except Exception as e:
            unreal.log_warning(f"[setup_project] 草の設定 {name} を変えられませんでした: {e}")


def create_grass_type(meshes):
    """ランドスケープグラス (どの草をどれだけ、どの距離まで生やすか) を作る。meshes は {名前: StaticMesh}。"""
    path = f"{GRASS_DIR}/{GRASS_TYPE_NAME}"
    used = [(spec, meshes[spec["mesh"]].get_path_name()) for spec in GRASS_VARIETIES if meshes.get(spec["mesh"])]
    if not used:
        return None
    digest = recipe(create_grass_type, used)
    if state.fresh(path, digest, path):
        return eal.load_asset(path)
    if eal.does_asset_exist(path):
        grass_type = eal.load_asset(path)
    else:
        factory = getattr(unreal, "LandscapeGrassTypeFactory", None)
        grass_type = asset_tools.create_asset(GRASS_TYPE_NAME, GRASS_DIR, unreal.LandscapeGrassType, factory() if factory else None)
    if grass_type is None:
        unreal.log_warning("[setup_project] ランドスケープグラスを作れませんでした。草は生やしません")
        return None
    varieties = []
    for spec, _ in used:
        v = unreal.GrassVariety()
        scale = unreal.FloatInterval()
        scale.set_editor_property("min", spec["scale"][0])
        scale.set_editor_property("max", spec["scale"][1])
        set_struct(v, grass_mesh=meshes[spec["mesh"]],
                   grass_density=per_platform(unreal.PerPlatformFloat, spec["density"]),
                   use_grid=True, placement_jitter=1.0,
                   start_cull_distance=per_platform(unreal.PerPlatformInt, spec["cull"][0]),
                   end_cull_distance=per_platform(unreal.PerPlatformInt, spec["cull"][1]),
                   scaling=unreal.GrassScaling.UNIFORM, scale_x=scale,
                   random_rotation=True, align_to_surface=True,
                   cast_dynamic_shadow=False, receives_decals=False)
        varieties.append(v)
    grass_type.set_editor_property("grass_varieties", varieties)
    eal.save_loaded_asset(grass_type)
    state.done(path, digest)
    log(f"作成: {path} ({', '.join(spec['mesh'] for spec, _ in used)})")
    return grass_type


def setup_grass():
    """草の株と地面の模様を取り込み、草のマテリアルとランドスケープグラスを作って grass_assets に入れる。
    ランドスケープマテリアルより先に呼ぶ (ランドスケープマテリアルがこれらを使う)。"""
    info_path = os.path.join(GRASS_FOLDER, "grass.json")
    if not os.path.exists(info_path):
        unreal.log_warning(f"[setup_project] {info_path} がありません (tools/terrain/build_grass.py を先に実行)。草地は色だけにします")
        return
    with open(info_path, encoding="utf-8") as f:
        info = json.load(f)
    ground = info.get("ground") or {}
    for key in GROUND_TEXTURE_KEYS:   # grass.json では ground_ を付けない (color / soil_color / ...)
        fname = ground.get(key.replace("ground_", ""))
        if fname:
            normal = key.endswith("normal")
            setattr(grass_assets, key, import_texture(os.path.join(GRASS_FOLDER, fname), GRASS_DIR,
                                                      normal=normal, linear=not normal))
    material = create_material("M_FD_Grass", build_grass_graph, GRASS_DIR)
    meshes = {}
    for name, fname in info.get("meshes", {}).items():
        mesh = import_scenery_mesh(name, os.path.join(GRASS_FOLDER, fname), GRASS_DIR, nanite=False)
        if mesh is None:
            continue
        if mesh.get_material(0) != material:
            mesh.set_material(0, material)
            eal.save_loaded_asset(mesh)
            log(f"草のマテリアル: {name}")
        meshes[name] = mesh
    grass_assets.grass_type = create_grass_type(meshes)


# ---------------------------------------------------------------- 遠景の地形
FAR_TERRAIN_FOLDER = os.path.join(DATA_DIR, "far")


def import_far_terrain():
    """遠景の地形のメッシュを取り込む (glTF が変わったときだけ。取り込みに少し時間がかかる)。"""
    gltf = os.path.join(FAR_TERRAIN_FOLDER, f"{FAR_TERRAIN_MESH}.gltf")
    if not os.path.exists(gltf):
        unreal.log_warning(f"[setup_project] {gltf} がありません (tools/terrain/build_far_terrain.py を先に実行)。遠景の地形は置きません")
        return None
    return import_scenery_mesh(FAR_TERRAIN_MESH, gltf, FAR_TERRAIN_DIR, nanite=True)


def place_far_terrain(eas, mesh, material):
    """ランドスケープの外側の地形 (1枚の Nanite メッシュ、当たり判定なし)。"""
    if mesh is None:
        return
    a = place_mesh(eas, mesh, (0, 0, 0), 0.0, "遠景の地形", "Auto/FarTerrain")
    a.static_mesh_component.set_material(0, material)
    info_path = os.path.join(FAR_TERRAIN_FOLDER, "far_terrain.json")
    info = json.load(open(info_path, encoding="utf-8")) if os.path.exists(info_path) else {}
    log(f"遠景の地形: {info.get('half_m', 0) * 2 / 1000:.0f} km 四方、三角形 {info.get('triangles', 0):,}")


# ---------------------------------------------------------------- クロスカブ
def vector_param(mat, name, rgb, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    return e


def scalar_param(mat, name, v, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", v)
    return e


def build_paint_graph(mat):
    """車体色。色とつや (つや消しの色は粗く) は C++ がパラメータ Color / Roughness で変える。"""
    mel.connect_material_property(vector_param(mat, "Color", VEHICLE_PAINT_DEFAULT, -400, 0), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar_param(mat, "Roughness", 0.28, -400, 200), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, 0.6, -400, 300), "", unreal.MaterialProperty.MP_SPECULAR)


def build_light_graph(mat):
    """ライトのレンズ。Color x Intensity で光る (ブレーキランプは C++ が Intensity を上げる)。"""
    col = vector_param(mat, "Color", (1.0, 1.0, 1.0), -600, 0)
    mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -300, 100)
    mel.connect_material_expressions(col, "", mul, "A")
    mel.connect_material_expressions(scalar_param(mat, "Intensity", 10.0, -600, 200), "", mul, "B")
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(scalar(mat, 0.15, -300, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)


def light_instance(name, parent, spec):
    path = f"{VEHICLE_DIR}/{name}"
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = asset_tools.create_asset(name, VEHICLE_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    c = spec["color"]
    mel.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(c[0], c[1], c[2], 1.0))
    mel.set_material_instance_scalar_parameter_value(mi, "Intensity", spec["intensity"])
    eal.save_loaded_asset(mi)
    return mi


def setup_vehicle():
    """クロスカブのメッシュを取り込み、車体色とライトのレンズのスロットを専用のマテリアルに差し替える。"""
    folder = os.path.join(PROJECT_DIR, "tools", "vehicle", "out", "crosscub")
    if not os.path.isdir(folder):
        unreal.log_warning(f"[setup_project] {folder} がありません (py -3 tools/vehicle/build_crosscub.py を先に実行)。"
                           "バイクは仮の形のままです")
        return
    gltfs = [os.path.join(folder, f"{name}.gltf") for name in VEHICLE_MESHES]
    digest = recipe(setup_vehicle, files=gltfs)
    assets = [f"{VEHICLE_DIR}/{n}" for n in ("M_FD_VehiclePaint", "M_FD_VehicleLight", "MI_CC_HeadLens", "MI_CC_TailLens")]
    if state.fresh(VEHICLE_DIR, digest, *assets):
        return
    paint = create_material("M_FD_VehiclePaint", build_paint_graph, VEHICLE_DIR)
    light = create_material("M_FD_VehicleLight", build_light_graph, VEHICLE_DIR)
    replacements = {
        "FD_CC_Paint": paint,
        "FD_CC_HeadLens": light_instance("MI_CC_HeadLens", light, HEADLIGHT_LENS),
        "FD_CC_TailLens": light_instance("MI_CC_TailLens", light, TAIL_LENS),
    }
    for name in VEHICLE_MESHES:
        mesh = import_scenery_mesh(name, os.path.join(folder, f"{name}.gltf"), VEHICLE_DIR, nanite=False)
        if mesh is None:
            continue
        swapped = []
        for i, slot in enumerate(mesh.get_editor_property("static_materials")):
            names = [str(slot.get_editor_property("material_slot_name"))]
            current = slot.get_editor_property("material_interface")
            if current:
                names.append(current.get_name())
            for key, material in replacements.items():
                if any(key in n for n in names):
                    mesh.set_material(i, material)
                    swapped.append(key)
                    break
        eal.save_loaded_asset(mesh)
        b = mesh.get_bounding_box()
        size = b.max - b.min
        log(f"車両 {name}: {size.x:.0f} x {size.y:.0f} x {size.z:.0f} cm、差し替えたマテリアル {swapped or 'なし'}")
    state.done(VEHICLE_DIR, digest)


def setup_walker():
    """歩く人のメッシュ (胴・上腕・前腕・太もも・すね) を取り込む。"""
    folder = os.path.join(PROJECT_DIR, "tools", "vehicle", "out", "walker")
    if not os.path.isdir(folder):
        unreal.log_warning(f"[setup_project] {folder} がありません (py -3 tools/vehicle/build_walker.py を先に実行)。"
                           "歩く人は仮の形のままです")
        return
    for name in WALKER_MESHES:
        mesh = import_scenery_mesh(name, os.path.join(folder, f"{name}.gltf"), VEHICLE_DIR, nanite=False)
        if mesh is None:
            continue
        b = mesh.get_bounding_box()
        size = b.max - b.min
        log(f"歩く人 {name}: {size.x:.0f} x {size.y:.0f} x {size.z:.0f} cm")


# ---------------------------------------------------------------- ミニマップとファストトラベル
UI_DIR = f"{ROOT}/UI{COURSE_SUBDIR}"
MINIMAP_TEXTURE = "T_FD_Minimap"   # C++ の AFDBikePawn::MinimapTexture の既定値と同じ
MINIMAP_PNG = os.path.join(DATA_DIR, "minimap.png")

# ファストトラベルの行き先 (F キーのメニューの並び順)。
# landmark: その目印にいちばん近い道路 (優先度 max_priority 以下) の上に置く
# ref / corner: その番号の道路の、エリアの角 (corner の向き) にいちばん近い点に、エリアの内側を向けて置く
TRAVEL_POINTS = [
    ("二見ヶ浦 夫婦岩", dict(landmark="夫婦岩", max_priority=1)),
    ("櫻井神社", dict(landmark="櫻井神社", max_priority=3)),
    ("県道54号 北東の端 (福岡市方面)", dict(ref="54", corner=(1, -1))),
    ("県道54号 西の端 (志摩方面)", dict(ref="54", corner=(-1, 1))),
]
TRAVEL_EDGE_INSET_CM = 15000.0   # エリアの端からこれだけ内側 (端は遠景との境目なので少し離す)
TRAVEL_LIFT_CM = 150.0           # 道路より上に置く (着いたときに C++ が地面に下ろす)


def import_minimap():
    """build_minimap.py の地図の画像を取り込む (画像が変わったときだけ)。"""
    path = f"{UI_DIR}/{MINIMAP_TEXTURE}"
    if not os.path.exists(MINIMAP_PNG):
        unreal.log_warning(f"[setup_project] {MINIMAP_PNG} がありません (py -3 tools/terrain/build_minimap.py を先に実行)。"
                           "ミニマップは地図なしで出ます")
        return
    digest = recipe(import_minimap, files=[MINIMAP_PNG])
    if state.fresh(path, digest, path):
        return
    # 取り込んだアセットの名前はファイル名になるので、アセットの名前で一時的に写してから取り込む
    import shutil
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    src = os.path.join(tmp_dir, f"{MINIMAP_TEXTURE}.png")
    shutil.copyfile(MINIMAP_PNG, src)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", UI_DIR)
    task.set_editor_property("destination_name", MINIMAP_TEXTURE)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    asset_tools.import_asset_tasks([task])
    shutil.rmtree(tmp_dir, ignore_errors=True)

    texture = None
    for p in task.get_editor_property("imported_object_paths") or []:
        obj = eal.load_asset(p)
        if isinstance(obj, unreal.Texture2D):
            texture = obj
    if texture is None and eal.does_asset_exist(path):
        texture = eal.load_asset(path)
    if texture is None:
        unreal.log_warning(f"[setup_project] {MINIMAP_PNG} を取り込めませんでした")
        return
    actual = texture.get_path_name().split(".")[0]
    if actual != path:
        eal.rename_asset(actual, path)
        texture = eal.load_asset(path)
    # UI 用: 端は伸ばす (地図の外は端の色)、常に全解像度で読む、縮小用のミップは作る
    for name, value in (("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI),
                        ("address_x", unreal.TextureAddress.TA_CLAMP),
                        ("address_y", unreal.TextureAddress.TA_CLAMP),
                        ("never_stream", True),
                        ("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)):
        try:
            texture.set_editor_property(name, value)
        except Exception as e:
            unreal.log_warning(f"[setup_project] {MINIMAP_TEXTURE} の {name} を設定できませんでした ({e})")
    eal.save_loaded_asset(texture)
    state.done(path, digest)
    log(f"取り込み: {path} ({texture.blueprint_get_size_x()} x {texture.blueprint_get_size_y()})")


def find_travel_spot(roads, landmarks, spec):
    """行き先の (位置, 次の点) を道路の点から選ぶ。見つからなければ None。"""
    if "landmark" in spec:
        lm = next((lm for lm in landmarks if spec["landmark"] in lm["name"]), None)
        if lm is None:
            return None
        tx, ty = lm["location_cm"][:2]
        best = None
        for r in roads:
            if r["priority"] > spec["max_priority"]:
                continue
            pts = r["points_cm"]
            for i in range(len(pts) - 1):
                d = (pts[i][0] - tx) ** 2 + (pts[i][1] - ty) ** 2
                if best is None or d < best[0]:
                    best = (d, pts[i], pts[i + 1])
        return best[1:] if best else None

    cx, cy = spec["corner"]
    limit = 201600.0 - TRAVEL_EDGE_INSET_CM
    best = None
    for r in roads:
        if r["ref"] != spec["ref"]:
            continue
        pts = r["points_cm"]
        for i, p in enumerate(pts):
            if abs(p[0]) > limit or abs(p[1]) > limit or len(pts) < 2:
                continue
            score = p[0] * cx + p[1] * cy
            if best is None or score > best[0]:
                # 隣の点のうち、角から遠い (エリアの内側の) 方を向く
                nbrs = [pts[j] for j in (i - 1, i + 1) if 0 <= j < len(pts)]
                inner = min(nbrs, key=lambda q: q[0] * cx + q[1] * cy)
                best = (score, p, inner)
    return best[1:] if best else None


def place_travel_points(eas):
    import math
    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDTravelPoint")
    if cls is None:
        unreal.log_warning("[setup_project] FDTravelPoint がありません (C++ をビルドしてから実行)。ファストトラベルの行き先は置きません")
        return
    roads = load_json("roads.json")
    lms = load_json("landmarks.json")
    if not roads:
        return
    landmarks = lms["landmarks"] if lms else []
    for order, (name, spec) in enumerate(TRAVEL_POINTS):
        spot = find_travel_spot(roads["roads"], landmarks, spec)
        if spot is None:
            unreal.log_warning(f"[setup_project] ファストトラベルの行き先「{name}」の場所が見つかりません")
            continue
        p0, p1 = spot
        yaw = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        a = spawn(eas, cls, (p0[0], p0[1], p0[2] + TRAVEL_LIFT_CM), (0, yaw, 0), label=f"行き先: {name}",
                  folder="Auto/TravelPoints")
        set_props(a, DisplayName=name, Order=order)
        log(f"ファストトラベル: {name} ({p0[0]:.0f}, {p0[1]:.0f}, {p0[2]:.0f})")


# ---------------------------------------------------------------- 一周コース (World Partition のレベル)
# tools/terrain/build_tiles.py が作った tiles.json があれば、4km のタイルを並べた一周コースのレベル (LOOP_MAP_PATH) を作る。
# タイルごとにランドスケープ (C++ の FDEditorTools) と景観物を置き、変わったタイルだけ置き直す。
# 最初の区間のレベル (MAP_PATH) には触らない
LOOP_NAME = COURSE.name
LOOP_DIR = os.path.join(PROJECT_DIR, "tools", "terrain", "out", LOOP_NAME)
LOOP_AREA_JSON = COURSE.path
TILES_JSON = os.path.join(LOOP_DIR, "tiles.json")
LOOP = os.path.exists(TILES_JSON)
LOOP_MAP_PATH = f"{ROOT}/Maps/{COURSE.map}"
TILE_ASSET_DIR = f"{ROOT}/Tiles"            # タイルごとの形 (建物・区画線・ガードレールのビームなど、置き場所が決まったもの)
ROAD_LAYER_INFO = f"{MATERIAL_DIR}/Road_LayerInfo"
COAST_MASK_DEFAULT = "/Engine/EngineResources/WhiteSquareTexture"   # 海岸の絵の既定 (白 = どこでも砂浜にしてよい)
LANDSCAPE_IMPORT_VERSION = 3               # FDEditorTools.CreateLandscape の作り方を変えたら上げる (タイルの地面を作り直す)
LOOP_SEA_ZONE_RESOLUTION = 4096             # WaterZone は約 24km 四方なので、海岸の判定の細かさ (約 6m) を保つ
LANDSCAPE_TAG = "fd_landscape"
GLOBAL_TAG = "fd_global"
BASE_TILE = AREA                            # 木や花など、どのタイルでも同じ形の取り込みとマテリアルはこのタイルのデータで作る
if LOOP:
    FAR_TERRAIN_FOLDER = os.path.join(LOOP_DIR, "far")
    MINIMAP_PNG = os.path.join(LOOP_DIR, "minimap.png")


def tile_tag(name):
    return f"fd_tile_{name}"


def load_tiles():
    with open(TILES_JSON, encoding="utf-8") as f:
        doc = json.load(f)
    # 最初の区間を先に (共通のメッシュとマテリアルを作る)
    doc["tiles"].sort(key=lambda t: (t["name"] != BASE_TILE, t["name"]))
    return doc


def open_or_create_loop_level():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if eal.does_asset_exist(LOOP_MAP_PATH):
        les.load_level(LOOP_MAP_PATH)
        log(f"既存レベルを開きました: {LOOP_MAP_PATH}")
    else:
        try:
            les.new_level(LOOP_MAP_PATH, True)   # World Partition (アクターごとのファイル)
        except TypeError:
            les.new_level(LOOP_MAP_PATH)
        log(f"レベルを作成: {LOOP_MAP_PATH}")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    # ストリーミングは使わず、プレイ中もすべて読み込んでおく (遠くの木や建物が近づいてから急に出ないように)。
    # World Partition はアクターごとのファイルに分けるため (変えたタイルの分だけが Git の差分になる)
    if unreal.FDEditorTools.disable_world_partition_streaming(world):
        log("World Partition: ストリーミングを切りました (すべて読み込む)")
    else:
        unreal.log_warning("[setup_project] World Partition のストリーミングを切れませんでした")
    load_all_actors(world)
    return les, world


def load_all_actors(world):
    """World Partition のレベルはエディタでも近くのアクターしか読み込まないので、置き直す前に全部読み込む。"""
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if lib is None:
        return
    try:
        descs = lib.get_actor_descs()
        guids = [d.get_editor_property("guid") for d in descs]
        if guids:
            lib.load_actors(guids)
            log(f"World Partition: アクター {len(guids)} 個を読み込みました")
    except Exception as e:
        unreal.log_warning(f"[setup_project] World Partition のアクターを読み込めませんでした: {e}")


def destroy_tagged(eas, *tags, without=None):
    n = 0
    for a in eas.get_all_level_actors():
        if all(a.actor_has_tag(t) for t in tags) and not (without and a.actor_has_tag(without)):
            eas.destroy_actor(a)
            n += 1
    return n


def tile_data_dir(tile):
    return os.path.join(PROJECT_DIR, "tools", "terrain", "out", tile["name"])


def import_tile_scenery(tile, base_doc):
    """タイルの景観物を取り込む。置き場所の決まった形 (world_meshes) はタイルのフォルダへ、木や花など共通の形は
    SCENERY_DIR へ (最初の区間で取り込み済みならそれを使う)。({名前: StaticMesh}, scenery.json の中身) を返す。"""
    path = os.path.join(tile_data_dir(tile), "scenery", "scenery.json")
    if not os.path.exists(path):
        unreal.log_warning(f"[setup_project] {path} がありません (tools/terrain/build_tiles.py を先に実行)")
        return None, {}
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    folder = os.path.dirname(path)
    world = set(doc.get("world_meshes", {}))
    meshes = {}
    for name, fname in doc["meshes"].items():
        gltf = os.path.join(folder, fname)
        if name in world:
            meshes[name] = import_scenery_mesh(name, gltf, f"{TILE_ASSET_DIR}/{tile['name']}")
        elif tile["name"] == BASE_TILE:
            meshes[name] = import_scenery_mesh(name, gltf)
        else:
            existing = f"{SCENERY_DIR}/{name}/StaticMeshes/{name}"
            meshes[name] = eal.load_asset(existing) if eal.does_asset_exist(existing) else import_scenery_mesh(name, gltf)
    setup_foliage(base_doc, meshes)
    setup_lamp_glow(meshes)
    setup_buildings(base_doc, meshes)
    return doc, meshes


def landscape_inputs(tile):
    d = tile_data_dir(tile)
    return [os.path.join(d, n) for n in ("heightmap.r16", "road_layer.r8", "landscape_import.json")]


def tile_landscape_material(tile, parent, corner, size_cm):
    """タイルのランドスケープ用のマテリアルインスタンス。海岸の絵 (tools/terrain/build_coast.py の coast_mask.png) と
    その範囲を M_Landscape に渡す。絵が無ければ M_Landscape のまま (低い所はすべて砂浜)。"""
    png = os.path.join(tile_data_dir(tile), "coast_mask.png")
    if not os.path.exists(png):
        unreal.log_warning(f"[setup_project] {png} がありません。低い所はすべて砂浜になります (build_tiles.py --coast)")
        return parent
    directory = f"{TILE_ASSET_DIR}/{tile['name']}"
    mask = import_texture(png, directory)
    if mask is None:
        return parent
    name = f"MI_FD_Landscape_{tile['name']}"
    path = f"{directory}/{name}"
    mi = eal.load_asset(path) if eal.does_asset_exist(path) else asset_tools.create_asset(
        name, directory, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    mel.set_material_instance_texture_parameter_value(mi, "CoastMask", mask)
    mel.set_material_instance_vector_parameter_value(mi, "TileCorner", unreal.LinearColor(corner[0], corner[1], 0.0, 0.0))
    mel.set_material_instance_scalar_parameter_value(mi, "TileSize", size_cm)
    eal.save_loaded_asset(mi)
    return mi


ROAD_LAYER_CREATED_KEY = f"{ROAD_LAYER_INFO}#created"


def ensure_road_layer_info():
    """道路のレイヤー情報 (M_Landscape の LandscapeLayerSample "Road" と同じ名前) が無ければ作って保存する。
    キットで入れたプロジェクトには Content が無いので、これが無いと道路が塗られず草になる。"""
    if eal.does_asset_exist(ROAD_LAYER_INFO):
        return
    cls = getattr(unreal, "FDEditorTools", None)
    if cls is None or not hasattr(cls, "create_layer_info"):
        unreal.log_error("[setup_project] FDEditorTools.CreateLayerInfo がありません (C++ をビルドし直してください)")
        return
    info = cls.create_layer_info(ROAD_LAYER_INFO, "Road")
    if info is None:
        return
    eal.save_loaded_asset(info)
    state.done(ROAD_LAYER_CREATED_KEY, "yes")
    log(f"道路のレイヤー情報 {ROAD_LAYER_INFO} を作りました")


def road_layer_mark():
    """ここで作ったレイヤー情報なら、ランドスケープの作り方のハッシュに足す (道路を塗らずに作った地面を 1 回作り直す)。
    手で作ってあったプロジェクト (糸島) ではハッシュは変わらない。"""
    return ["kit_road_layer"] if state.data.get(ROAD_LAYER_CREATED_KEY) else []


def place_tile_landscape(eas, world, tile, material):
    """タイルのランドスケープを (作り直す)。heightmap.r16 と road_layer.r8 (tools/terrain/apply_roads.py) から作る。"""
    r16, r8, info_path = landscape_inputs(tile)
    if not os.path.exists(r16) or not os.path.exists(info_path):
        unreal.log_warning(f"[setup_project] {tile['name']} のハイトマップがありません (build_tiles.py を先に実行)")
        return
    cls = getattr(unreal, "FDEditorTools", None)
    if cls is None:
        unreal.log_error("[setup_project] FDEditorTools がありません (C++ をビルドしてから実行し直してください)")
        return
    with open(info_path, encoding="utf-8") as f:
        info = json.load(f)
    n = int(info["resolution"].split("x")[0])
    corner = [info["corner_location_cm"][k] + tile["offset_cm"][k] for k in range(3)]
    removed = destroy_tagged(eas, tile_tag(tile["name"]), LANDSCAPE_TAG)
    layer = eal.load_asset(ROAD_LAYER_INFO) if eal.does_asset_exist(ROAD_LAYER_INFO) else None
    if layer is None:
        unreal.log_warning(f"[setup_project] {ROAD_LAYER_INFO} がありません。道路は塗りません")
    if not os.path.exists(r8):
        unreal.log_warning(f"[setup_project] {r8} がありません。道路は塗りません (apply_roads.py を実行し直してください)")
    material = tile_landscape_material(tile, material, corner, (n - 1) * info["scale"][0])
    ls = cls.create_landscape(world, r16, n, unreal.Vector(*corner), unreal.Vector(*info["scale"]), material,
                              layer, r8 if os.path.exists(r8) else "", f"Landscape {tile['name']}")
    if ls is None:
        unreal.log_error(f"[setup_project] {tile['name']} のランドスケープを作れませんでした (Saved/Logs を確認)")
        return
    ls.tags = list(ls.tags) + [AUTO_TAG, tile_tag(tile["name"]), LANDSCAPE_TAG]
    ls.set_folder_path(f"Tiles/{tile['name']}")
    log(f"ランドスケープ: {tile['name']} ({n} x {n}、角 {corner[0]:.0f}, {corner[1]:.0f}){'、作り直し' if removed else ''}")


def place_tile(eas, tile, doc, meshes):
    """タイルの景観物・夜の光・目印を、タイルの位置へずらして置く。"""
    placing.offset = tuple(tile["offset_cm"])
    placing.tags = [tile_tag(tile["name"])]
    placing.folder = f"Tiles/{tile['name']}"
    placing.data_dir = tile_data_dir(tile)
    try:
        place_scenery(eas, doc, meshes)
        place_night_lights(eas, doc)
        place_landmarks(eas)
    finally:
        placing.offset, placing.tags, placing.folder, placing.data_dir = (0.0, 0.0, 0.0), [], "", ""


def tile_recipe(tile, meshes):
    available = [name for name in ("FDInstances", "FDNightLights")
                 if unreal.load_class(None, f"/Script/FukuokaDrive.{name}") is not None]
    available += [name for name, mesh in sorted(meshes.items()) if mesh]
    d = tile_data_dir(tile)
    files = [os.path.join(d, "scenery", "scenery.json"), os.path.join(d, "landmarks.json")]
    return recipe(place_tile, tile["offset_cm"], available, files=files)


def loop_travel_points():
    """一周コースの経由点 (areas/itoshima_loop.json の waypoints) を、コースの上の (位置, 次の点) にする。UE の cm。"""
    route_path = os.path.join(LOOP_DIR, "loop_route.json")
    if not os.path.exists(route_path) or not os.path.exists(LOOP_AREA_JSON):
        return []
    with open(route_path, encoding="utf-8") as f:
        pts = json.load(f)["points"]
    with open(LOOP_AREA_JSON, encoding="utf-8") as f:
        waypoints = json.load(f)["waypoints"]
    xy = [(p["x_m"] * 100.0, -p["y_m"] * 100.0) for p in pts]   # 北 + の m -> UE の cm (Y は南)
    out = []
    for wp in waypoints:
        best = min(range(len(pts)), key=lambda i: (pts[i]["lat"] - wp["lat"]) ** 2 + (pts[i]["lon"] - wp["lon"]) ** 2)
        nxt = xy[(best + 3) % len(xy)]
        out.append((wp["name"], xy[best], nxt))
    return out


def road_z_near(tiles, x, y):
    """(x, y) cm にいちばん近い道路の点の高さ (cm)。そのタイルの roads.json から。"""
    best = None
    for t in tiles["tiles"]:
        ox, oy = t["offset_cm"][:2]
        half = tiles["tile_size_m"] * 50.0
        if abs(x - ox) > half or abs(y - oy) > half:
            continue
        path = os.path.join(tile_data_dir(t), "roads.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for r in json.load(f)["roads"]:
                for p in r["points_cm"]:
                    d = (p[0] + ox - x) ** 2 + (p[1] + oy - y) ** 2
                    if best is None or d < best[0]:
                        best = (d, p[2])
    return best[1] if best else 5000.0


def place_loop_travel_points(eas, tiles):
    import math
    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDTravelPoint")
    if cls is None:
        unreal.log_warning("[setup_project] FDTravelPoint がありません (C++ をビルドしてから実行)。ファストトラベルの行き先は置きません")
        return
    for order, (name, (x, y), (nx, ny)) in enumerate(loop_travel_points()):
        z = road_z_near(tiles, x, y)
        yaw = math.degrees(math.atan2(ny - y, nx - x))
        a = spawn(eas, cls, (x, y, z + TRAVEL_LIFT_CM), (0, yaw, 0), label=f"行き先: {name}", folder="Auto/TravelPoints")
        set_props(a, DisplayName=name, Order=order)
        log(f"ファストトラベル: {name} ({x:.0f}, {y:.0f}, {z:.0f})")


def populate_loop_global(eas, tiles, sea_material, far_mesh, far_material):
    """どのタイルにも属さないもの (空・海・遠景・スタート・ファストトラベル) を置き直す。"""
    placing.tags = [GLOBAL_TAG]
    try:
        place_sky(eas)
        if tiles.get("sea", True):   # 海にかからないコース (山の中だけ) は海を置かない (tiles.json の sea)
            zone = [v * 100.0 for v in tiles["water_zone_m"]]
            place_sea(eas, sea_material, zone, LOOP_SEA_ZONE_RESOLUTION)
            place_water_refresh(eas)
        place_far_terrain(eas, far_mesh, far_material)
        place_loop_player_start(eas, tiles)
        place_loop_travel_points(eas, tiles)
        place_course_info(eas)
    finally:
        placing.tags = []


def place_loop_player_start(eas, tiles):
    """夫婦岩があるコース (糸島一周) は夫婦岩の前 (最初の区間 = タイル (0, 0) なので、ずらさない)。
    無ければコースの最初の経由点に、コースの進む向きで置く。"""
    import math
    lms = load_json("landmarks.json")
    stops = loop_travel_points()
    if (lms and any("夫婦岩" in lm["name"] for lm in lms["landmarks"])) or not stops:
        place_player_start(eas)
        return
    name, (x, y), (nx, ny) = stops[0]
    z = road_z_near(tiles, x, y)
    yaw = math.degrees(math.atan2(ny - y, nx - x))
    spawn(eas, unreal.PlayerStart, (x, y, z + 150), (0, yaw, 0), label="PlayerStart", folder="Auto")
    log(f"PlayerStart: {name} ({x:.0f}, {y:.0f}, {z:.0f})")


def place_course_info(eas):
    """コースごとの値 (ミニマップの範囲、緯度経度) を C++ の FDCourseInfo に持たせる。"""
    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDCourseInfo")
    if cls is None:
        unreal.log_warning("[setup_project] FDCourseInfo がありません (C++ をビルドしてから実行し直してください)")
        return
    info = spawn(eas, cls, (0, 0, 0), label=f"CourseInfo ({LOOP_NAME})", folder="Auto")
    set_props(info, CourseName=LOOP_NAME, Latitude=LATITUDE, Longitude=LONGITUDE)
    if COURSE.rotation:
        set_props(info, GridRotationDeg=COURSE.rotation)
    minimap = f"{UI_DIR}/{MINIMAP_TEXTURE}"
    if COURSE_SUBDIR and eal.does_asset_exist(minimap):   # コースごとの地図 (糸島は C++ の既定の地図のまま)
        set_props(info, MinimapTexture=eal.load_asset(minimap))
    bounds_path = os.path.join(LOOP_DIR, "minimap.json")
    if os.path.exists(bounds_path):
        with open(bounds_path, encoding="utf-8") as f:
            b = json.load(f)
        set_props(info, MinimapWorldMin=unreal.Vector2D(*b["world_min_cm"]),
                  MinimapWorldMax=unreal.Vector2D(*b["world_max_cm"]))


def place_water_refresh(eas):
    """開いた直後に海が地形を読み直すようにする (FDWaterRefresh.h)。"""
    cls = unreal.load_class(None, "/Script/FukuokaDrive.FDWaterRefresh")
    if cls is None:
        unreal.log_warning("[setup_project] FDWaterRefresh がありません (C++ をビルドしてから実行し直してください)")
        return
    spawn(eas, cls, (0, 0, 0), label="WaterRefresh", folder="Auto/Sea")


def loop_global_recipe(tiles, far_mesh):
    available = [name for name in ("FDTimeOfDay", "FDTravelPoint", "FDWaterRefresh", "FDCourseInfo")
                 if unreal.load_class(None, f"/Script/FukuokaDrive.{name}") is not None]
    available += ["Water" if hasattr(unreal, "WaterBodyOcean") else "NoWater", "Far" if far_mesh else "NoFar"]
    available += ["Sky" if night_assets.sky else "NoSky"]
    files = [os.path.join(DATA_DIR, n) for n in ("landmarks.json", "roads.json")]
    files += [TILES_JSON, os.path.join(LOOP_DIR, "loop_route.json"), LOOP_AREA_JSON,
              os.path.join(FAR_TERRAIN_FOLDER, "far_terrain.json"), os.path.join(LOOP_DIR, "minimap.json")]
    return recipe(populate_loop_global, available, files=files)


def refresh_water_zones(eas):
    """海 (WaterZone) は置いた時のランドスケープで水の範囲を決める。ランドスケープを後から置いたので、範囲を
    一度変えて戻し、地形を読み直させる (そのままだとタイルの所の海が描かれず、海底の砂が見える)。"""
    for wz in eas.get_all_level_actors():
        if wz.get_class().get_name() != "WaterZone":
            continue
        extent = wz.get_editor_property("zone_extent")
        wz.set_editor_property("zone_extent", unreal.Vector2D(extent.x + 100.0, extent.y))
        wz.set_editor_property("zone_extent", extent)
        log("海: WaterZone に地形を読み直させました")


def build_loop(sea_material, far_mesh, far_material):
    tiles = load_tiles()
    les, world = open_or_create_loop_level()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    landscape_material = eal.load_asset(f"{MATERIAL_DIR}/M_Landscape")
    changed = False

    key = f"{LOOP_MAP_PATH}#global"
    digest = loop_global_recipe(tiles, far_mesh)
    if not state.fresh(key, digest, LOOP_MAP_PATH):
        destroy_tagged(eas, GLOBAL_TAG)
        populate_loop_global(eas, tiles, sea_material, far_mesh, far_material)
        state.done(key, digest)
        changed = True

    ensure_road_layer_info()
    base_doc = None
    for tile in tiles["tiles"]:
        name = tile["name"]
        key = f"{LOOP_MAP_PATH}#landscape:{name}"
        coast = os.path.join(tile_data_dir(tile), "coast_mask.png")
        digest = recipe(place_tile_landscape, tile["offset_cm"], LANDSCAPE_IMPORT_VERSION, *road_layer_mark(),
                        files=landscape_inputs(tile) + ([coast] if os.path.exists(coast) else []))
        if not state.fresh(key, digest, LOOP_MAP_PATH):
            place_tile_landscape(eas, world, tile, landscape_material)
            state.done(key, digest)
            changed = True

        if base_doc is None:
            with open(SCENERY_JSON, encoding="utf-8") as f:
                base_doc = json.load(f)
        doc, meshes = import_tile_scenery(tile, base_doc)
        if doc is None:
            continue
        key = f"{LOOP_MAP_PATH}#tile:{name}"
        digest = tile_recipe(tile, meshes)
        if not state.fresh(key, digest, LOOP_MAP_PATH):
            removed = destroy_tagged(eas, tile_tag(name), without=LANDSCAPE_TAG)
            place_tile(eas, tile, doc, meshes)
            state.done(key, digest)
            changed = True
            log(f"タイル {name} を置きました (前の {removed} 個は消しました)")
    if changed:
        refresh_water_zones(eas)
    if changed or not eal.does_asset_exist(LOOP_MAP_PATH):
        les.save_current_level()
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    else:
        log("一周コースのレベルは前回と同じなので置き直しません")


def populate_level(eas, sea_material, far_mesh, far_material, scenery, scenery_meshes):
    """レベルの自動配置物 (印 AUTO_TAG のついたもの) を置き直す。手で置いたもの (ランドスケープなど) は残る。"""
    clear_auto_actors(eas)
    place_sky(eas)
    place_sea(eas, sea_material)
    place_far_terrain(eas, far_mesh, far_material)
    place_scenery(eas, scenery, scenery_meshes)
    place_night_lights(eas, scenery)
    place_landmarks(eas)
    place_player_start(eas)
    place_travel_points(eas)


def level_recipe(scenery_meshes, far_mesh):
    # 置くもののクラス (C++ やプラグイン) やメッシュがあるかどうかでも置くものが変わる
    available = [name for name in ("FDTimeOfDay", "FDInstances", "FDTravelPoint", "FDNightLights")
                 if unreal.load_class(None, f"/Script/FukuokaDrive.{name}") is not None]
    available += [name for name, mesh in sorted(scenery_meshes.items()) if mesh]
    available += ["Water" if hasattr(unreal, "WaterBodyOcean") else "NoWater", "Far" if far_mesh else "NoFar"]
    available += ["Sky" if night_assets.sky else "NoSky"]
    files = [os.path.join(DATA_DIR, n) for n in ("landmarks.json", "roads.json")]
    files += [SCENERY_JSON, os.path.join(FAR_TERRAIN_FOLDER, "far_terrain.json")]
    return recipe(populate_level, available, files=files)


def main():
    global state
    state = SetupState()
    setup_grass()
    create_landscape_material()
    setup_vehicle()
    setup_walker()
    setup_night()
    sea_material = create_material("M_Sea", build_sea_graph)
    far_material = create_material("M_FarTerrain", build_far_terrain_graph)
    far_mesh = import_far_terrain()
    import_minimap()
    if LOOP:
        build_loop(sea_material, far_mesh, far_material)
    else:
        build_first_area(sea_material, far_mesh, far_material)
    if state.changed:
        # 取り込んだメッシュのマテリアルは、レベルに置いたときに使い道の印が付いて未保存になる。
        # 残すとエディタを閉じるときに保存されて後から差分になるので、ここで保存しておく
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    state.save()
    log(f"完了 (作り直したもの: {', '.join(state.changed) if state.changed else 'なし'})")


def build_first_area(sea_material, far_mesh, far_material):
    """最初の区間 (二見ヶ浦の 4km 四方) だけのレベル。ランドスケープは手で取り込んだもの。"""
    scenery, scenery_meshes = import_scenery()
    digest = level_recipe(scenery_meshes, far_mesh)
    if state.fresh(MAP_PATH, digest, MAP_PATH):
        log("レベルは前回と同じなので置き直しません")
    else:
        les = open_or_create_level()
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        populate_level(eas, sea_material, far_mesh, far_material, scenery, scenery_meshes)
        les.save_current_level()
        state.done(MAP_PATH, digest)


main()
