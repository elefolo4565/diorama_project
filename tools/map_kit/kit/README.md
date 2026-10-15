# 地域のジオラマを作る仕組みを、別の UE5 プロジェクトで使う

このリポジトリで糸島一周を作った仕組み (国土地理院の標高・建物と OpenStreetMap の道路から、海・地形・道路・木・建物・夜の光までを自動で作る) を、
別の UE5 プロジェクトに入れて、別の地域で使うためのスクリプトです。Claude Code のスキル「地域のジオラマ作成」がこの 2 つを使います。

| スクリプト | 動き |
| --- | --- |
| `install_kit.py` | C++ モジュール (`Source/FukuokaDrive`)・`tools/`・必要な Config・プラグインを、別のプロジェクトへ入れる (`--create <名前>` なら新しく作る)。何度実行しても同じ結果 |
| `area_picker.py` | ブラウザで地図を開き、地名検索 → 範囲を多角形で描く → `areas/<コース名>.json` を書き出す画面。作られる 4km タイルとその枚数がその場で見える |
| `make_diorama.py` | コースの設定 `tools/terrain/areas/<コース名>.json` 1 つから、道筋 → タイル → 遠景 → ミニマップ → UE のレベルまでを通しで作る。止まっても再実行で続きから |

```
git clone --depth 1 https://github.com/elefolo4565/fukuoka_drive C:\kit\fukuoka_drive     (GIT_LFS_SKIP_SMUDGE=1 にすると Content の LFS を落とさない)
py -3 C:\kit\fukuoka_drive\tools\kit\install_kit.py C:\Projects\NotoDiorama --create NotoDiorama
cd C:\Projects\NotoDiorama
py -3 -m pip install -r tools\terrain\requirements.txt
py -3 tools\kit\area_picker.py                  (地図で範囲を描いて noto.json を書き出す。道筋で作るなら手で書く: tools/terrain/README.md の「新しいコースを作る」)
py -3 tools\kit\make_diorama.py noto
```

- 範囲の決め方は 2 通り: 道筋 (`"waypoints"` か `"route"`。道に沿った幅 300m にかかるタイル) か、地図で描いた多角形 (`"polygon"`。かかるタイルを全部)。多角形のときファストトラベルの行き先は画面で置いた点か、無ければ真ん中に近い主な道路
- 地図は地理院地図 (航空写真・OSM にも切り替え可)。Google マップは API キーと課金が要り、地図から形を写し取る使い方も規約で禁止されているため、「Google マップで開く」で見比べるだけにしています
- 入れる先のプロジェクト名は何でもよく、C++ モジュールは `FukuokaDrive` の名前のまま追加されます (`/Script/FukuokaDrive.*` を `setup_project.py` が使うため)。Content は入れません (`setup_project.py` がすべて作ります)
- UE 付属の MCP サーバーも有効にし、エディタを開くと自動で起動します (`.mcp.json` も作る)。要らなければ `--no-mcp`
- 新しいコースの設定には `"features": {"landmarks": false, "utility_poles": false, "guardrails": false, "city_glow": false}` を書きます (糸島の名所・電柱と街灯・ガードレール・福岡市の方向の街明かりを入れない。道路と区画線・側溝・標識は入れる)
- 前提: Windows、UE 5.8 (`C:\Program Files\Epic Games\UE_5.8`、違う場所なら環境変数 `UE_ROOT`)、Visual Studio の C++、Python 3.10 以上 (`py -3`)、インターネット (国土地理院・Overpass・Nominatim)。データは日本国内だけ
- タイル (4km 四方) は 20 枚まで (`--max-tiles` で変更)。ストリーミングを切ってすべて読み込むので、多いとメモリが足りなくなります
- UE の組み立ては必ず GUI のエディタで行います (`rebuild.bat` → `editor.py run`)。コマンドラインで `setup_project.py` を動かすと海岸の海が崩れます
