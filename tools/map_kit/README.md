# map_kit (地域のジオラマを作る仕組み)

国土地理院の標高・建物と OpenStreetMap の道路・神社・線路などから、海・地形・道路・木・建物・神社・線路と駅・夜の光までを自動で作り、
UE 5.8 のレベルに組み立てる仕組みです。もとは fukuoka_drive (糸島一周) で作ったもので、ここがその本体です。

| フォルダ | 中身 |
| --- | --- |
| `kit/` | `install_kit.py` (地域のプロジェクトへ入れる・新しく作る)、`area_picker.py` (地図で範囲を描く)、`make_diorama.py` (通しで作る) |
| `terrain/` | データ作り (標高・道路・タイル・景色・建物・神社・線路と駅・遠景・ミニマップ) |
| `ue/` | UE の組み立て (`setup_project.py`、`editor.py`、`rebuild.bat`) |
| `vehicle/` | バイクと歩く人の形 |
| `Source/FukuokaDrive/` | C++ モジュール (名前は FukuokaDrive のまま。`/Script/FukuokaDrive.*` を setup_project.py が使う) |

## 新しい地域を作る

リポジトリの直下 (`C:\_projects\game\diorama_project`) で:

```
py -3 tools\map_kit\kit\install_kit.py maps\<地域> --create <英字のプロジェクト名>
cd maps\<地域>
py -3 -m pip install -r tools\terrain\requirements.txt
py -3 tools\kit\area_picker.py            (地図で範囲を描いて tools\terrain\areas\<コース名>.json を書き出す)
py -3 tools\kit\make_diorama.py <コース名>
```

- UE の組み立ては必ず GUI のエディタで行います (`make_diorama.py` か `tools\ue\editor.py run tools\ue\setup_project.py`)。
  コマンドライン (ヘッドレス) で `setup_project.py` を動かすと海岸の海が崩れます
- エディタは `tools\ue\open_editor.bat` で開きます。.uproject のダブルクリックは、Epic Games Launcher に
  関連付けられていると「Missing Modules」になってプロジェクトの選択画面に戻ります (エディタがプロジェクト無しで起動するため)。
  ダブルクリックで開きたいときは、.uproject を右クリック →「プログラムから開く」→
  `C:\Program Files\Epic Games\Launcher\Engine\Binaries\Win64\UnrealVersionSelector.exe` を「常に使う」にします
- 神社は、コースの設定の `"features"` に `"shrines": true` を書くと作ります (地図で範囲を選ぶ画面は true を書きます)
- 線路と駅も同じく `"railways": true` で作ります (地図で範囲を選ぶ画面は true を書きます)。範囲に線路が無ければ何も置きません

## 仕組みを直すとき

1. ここ (`tools\map_kit`) を直す
2. 地域ごとに入れ直す: `py -3 tools\map_kit\kit\install_kit.py maps\<地域>` (`--create` なし。何度実行しても同じ結果)
3. 地域のフォルダで作り直す (`make_diorama.py <コース名>`、景色だけなら `tools\terrain\build_tiles.py areas\<コース名>.json --scenery`)

地域のフォルダの `tools\` は入れ直しで上書きされるので、地域のフォルダの側では直さないでください
(地域ごとのもの = `tools\terrain\areas\` と `tools\terrain\course.txt` は上書きされません)。
