# 地形・道路データツール

国土地理院の標高タイルと OpenStreetMap から、UE5 のランドスケープ用ハイトマップと道路のポイント列を作ります。
インターネットに接続した PC で実行してください (Python 3.10 以上)。

## 準備

```
cd tools/terrain
py -m pip install -r requirements.txt
```

## 実行

```
py build_terrain.py areas/futamigaura.json
py build_roads.py areas/futamigaura.json
py apply_roads.py areas/futamigaura.json
py build_scenery.py areas/futamigaura.json
py build_grass.py areas/futamigaura.json
py build_far_terrain.py areas/futamigaura.json
py build_minimap.py areas/futamigaura.json
py preview.py areas/futamigaura.json
```

出力は `tools/terrain/out/futamigaura/` に入ります (Git には入れません)。

| ファイル | 内容 |
| --- | --- |
| `preview.png` | 地形・道路・目印の確認用画像 (上が北) |
| `heightmap.png` / `heightmap.r16` | UE ランドスケープ用 16bit ハイトマップ (1px = 1m) |
| `landscape_import.json` | UE で入力する位置・スケール |
| `road_layer.png` / `road_layer.r8` | ランドスケープの Road レイヤー用ウェイトマップ (r8 は同じ内容の RAW。一周コースの C++ の取り込みが読む) |
| `roads.json` | 道路ごとのポイント列 (UE 座標 cm、10m 間隔、ならした路面の高さ付き) |
| `landmarks.json` | 夫婦岩などの目印の UE 座標 |
| `minimap.png` | ミニマップの地図 (2048 x 2048、上が北、範囲はランドスケープと同じ)。海・砂浜・陰影付きの陸に道路を太めに描いたもの |
| `far/` | ランドスケープの外 (110km 四方) の遠景の地形 (`SM_FD_FarTerrain.gltf`)、頂点数などの記録 (`far_terrain.json`)、上から見た色の確認用画像 (`preview.png`) |
| `scenery/` | 夫婦岩・しめ縄・鳥居・ガードレール・木・季節の花と桜・建物 (`SM_FD_Buildings_*`、500m 四方ごと) の形 (`*.gltf`) と置き場所 (`scenery.json`)、配置の確認用画像 (`preview.png`、建物は橙) |
| `gsi_buildings.json` / `osm_buildings.json` | 建物の輪郭 (国土地理院ベクトルタイルの建築物と OSM の建物)。`build_scenery.py` が無ければ取得する |
| `grass/` | 草地の草の株 (`SM_FD_GrassTuft.gltf` 短い草、`SM_FD_GrassTall.gltf` 背の高い草) と地面の模様 (`T_FD_Ground_D/N.png` 草地、`T_FD_Soil_D/N.png` 斜面の土、`T_FD_Asphalt_D/N.png` 道路。D は色のむら、N は凹凸)。UE のランドスケープグラスがカメラの近くの草地だけに生やす |

まず `preview.png` を開き、二見ヶ浦と西側の海岸道路が範囲に入っているか確認します。
ずれていたら `areas/futamigaura.json` の `center_lat` / `center_lon` を直して再実行してください。
ダウンロードしたタイルは `out/_cache/` に残るので、2回目以降は速くなります。

## 糸島一周コース (タイル 15 枚)

最初の区間 (二見ヶ浦) を 4km 四方のタイル (0, 0) として、糸島半島を一周する道路にかかるタイルを並べます。

```
py build_loop.py areas/itoshima_loop.json          一周ルート (OSM の主要道路を最短経路でつなぐ) とかかるタイル
py build_tiles.py areas/itoshima_loop.json         タイルごとの地形・道路・景観物 (境目の高さもそろえる)
py build_far_terrain.py areas/itoshima_loop.json   タイルの外の遠景
py build_minimap.py areas/itoshima_loop.json       一周全体のミニマップ
```

- ルートの通過点は `areas/itoshima_loop.json` の `waypoints` (二見ヶ浦 → 野北 → 芥屋 → 岐志 → 加布里 → 前原 → 今宿 → 今津 → 西浦)。結果は `out/itoshima_loop/loop_route.json` と `preview.png`
- タイルの設定は `areas/itoshima/<名前>.json` (自動で作る)、出力は `out/<タイル名>/`。タイル (0, 0) は `futamigaura` そのもの
- `out/itoshima_loop/tiles.json` にタイルの一覧と UE での置き場所 (`offset_cm`)、海 (WaterZone) の範囲を書きます。`setup_project.py` はこのファイルがあると一周コースのレベルを作ります
- `build_tiles.py ... -1,0` で一部のタイルだけ、`--stitch` で境目のそろえ直しだけ、`--scenery` で景観物だけ作り直せます
- 地形は 640m、道路は 150m タイルの外まで作ってから切り取り、隣のタイルとつながるようにします。境目の画素は両側の平均にそろえ、内側 64px でなじませます
- `build_tiles.py` は景観物の後に `build_coast.py` (海から 160m より遠い低地は砂浜にしない、という絵) も作ります。`--coast` でそれだけ作り直せます
- 15 枚で 30 分ほど、`out/` は約 7GB になります。Overpass が混んでいると 504 で建物や店が取れないことがあるので、その時は `--scenery <タイル>` で作り直してください

## 新しいコースを作る

道筋ではなく「この範囲を全部」作りたいときは、`py -3 tools/kit/area_picker.py` で地図に多角形を描いて書き出せます (`"polygon"` を持つ設定になり、かかる 4km タイルを全部作る)。

コースの設定 `areas/<コース名>.json` を 1 つ書き、`course.txt` をそのコース名にすれば、糸島一周と同じ手順で作れます (くわしくは [docs/course_pipeline.md](../../docs/course_pipeline.md))。

```
{
  "name": "tdk_stage1",
  "description": "ツール・ド・九州 第 1 ステージ",
  "route": "routes/tdk_stage1.gpx",
  "tile_size_px": 4033,
  "meters_per_px": 1.0,
  "corridor_m": 300
}
```

- `route` に GPX か KML (`areas/` からの相対パス) を書くと、その線をそのままコースにします。片道なら `"loop": false` (route がある時の既定)
- `route` の代わりに `waypoints` (名前・緯度・経度) を書くと、OSM の主な道路を最短経路で結びます (糸島一周はこちら)
- 経由点は緯度経度の代わりに `"q"` (地名や施設名) だけでもよく、`build_loop.py` が OSM の Nominatim で探して緯度経度を書き足します
- 中心 (`center_lat` / `center_lon`) と範囲 (`size_px`) は、無ければ `build_loop.py` がコースの線から決めて書き足します。後から変えるとタイルがすべてずれるので、一度決めたら変えないでください
- GPX に経由点が無ければ、スタート・約 20km おき・ゴールをファストトラベルの行き先にします (`waypoints` に書き足されるので、名前は直せます)
- タイルの名前は `<コース名>_<i>_<j>`、設定は `areas/<コース名>/`、UE のレベルは `/Game/FukuokaDrive/Maps/<コース名>` (`"map"` で変えられる)
- 木や花の決め方は糸島 (海沿いの低い里山) 向けです。違う土地では `"vegetation"` で `build_scenery.py` などの定数を変えます。例 (阿蘇): `{"build_scenery.GRASSLAND_MIN_Z_M": 650, "build_scenery.FARM_MAX_Z_M": 800, "build_scenery.BAMBOO_Z_M": [300, 650], "flowers.FIELD_Z_M": [2.5, 800], "flowers.ROADSIDE_Z_M": [2.5, 1200]}`。`GRASSLAND_MIN_Z_M` より高い緩い斜面は草原 (木がほとんど無い) になります
- `"features"` で入れないものを選べます: `"landmarks": false` (夫婦岩・鳥居・ヤシ並木)、`"road_markings": false` (区画線・側溝・標識)、`"utility_poles": false` (電柱と電線・防犯灯)、`"guardrails": false` (ガードレール)、`"road_furniture": false` (この 3 つをまとめて。前の書き方)、`"city_glow": false` (夜空の福岡市・前原の方向の街明かり)。書かなければすべて入れます (糸島一周)
- 海はどれかのタイルに海がある時だけ置きます (山の中だけのコースでは置かない)。`"sea": "none"` で必ず置かないようにできます
- 起動時に開くレベルは `Config/DefaultEngine.ini` の `EditorStartupMap` / `GameDefaultMap` を手で変えます

## UE5 への取り込み

詳しい手順は [tools/ue/README.md](../ue/README.md)。要点だけ:

### ランドスケープ

1. ランドスケープモード → 管理 → 新規 → 「ファイルからインポート」で `heightmap.png` を選ぶ
2. `landscape_import.json` の値を入力する
   - 場所: `location_cm` (0, 0, 0)。UE5.8 の取り込み画面の「場所」はランドスケープの中心を指す
   - スケール (Scale): `scale` (X, Y = 100 で 1px = 1m。Z はエリアの標高差から自動で決めた値)
3. 解像度は 4033 x 4033 のまま取り込む
4. 海面は Z = 0。Water Body Ocean などをこの高さに置く

座標の向き: UE の +X が東、+Y が南。エリア中心が原点 (0, 0) です。

## 仕組みのメモ

- 標高は DEM5A (5m メッシュ、ズーム15) を優先し、欠けている所を DEM10B (10m、ズーム14) で埋めます
- 標高データが無く、範囲の外周につながっている所を海とみなし、海岸から沖へ 1:20 の傾斜 (最大 30m) で海底を作ります
- 内陸のデータ欠損 (池など) は周囲の値で補間します
- `build_far_terrain.py` は DEM10B (ズーム13、約16m) を 40m 間隔に並べ直し、中心から放射状に頂点を置いたメッシュにします。遠いほど粗く (25km 先で約 250m)、見かけの細かさはどこでも同じです。ランドスケープの端の高さとぴったりつなぎ、WaterZone の外の海だけの所は省きます
- 建物は国土地理院のベクトルタイル (基盤地図情報の建築物) の輪郭に、OSM の階数と種類を重ねて作ります。長方形に近い家は瓦 (2 割は金属) の切妻か寄棟、大きな建物は平らな屋根。壁 (サイディング・モルタル)・屋根 (瓦・金属)・基礎の模様と凹凸の絵は `building_textures.py`。窓は壁のマテリアルが描き、夜は時刻に合わせて灯ります (`buildings.py`)
- `apply_roads.py` は道路の高さを約50m区間でならし、路面を平らにして路肩6mで元の地形へつなぎます。橋とトンネルは地形を削りません
