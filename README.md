# diorama_project

国土地理院と OpenStreetMap のデータから、日本の地域を走れるジオラマ (UE 5.8) にするプロジェクトの置き場です。
仕組み (キット) と、走りのコアと地域のマップを 1 つのリポジトリにまとめています。

## ツーリングシミュレータ (コア 1 つ + 地域のマップ)

2026-10-16 から、UE プロジェクトは走りのコア `touring/TouringSim.uproject` 1 つにまとめ、地域はそこへ足すマップにします。

- **コア** (`touring/`): クロスカブ・歩き・自由飛行・ファストトラベル・ミニマップと地図・時刻と季節・Tab のメニュー、
  共通のアセット (植物・草・建物の絵・神社・バイク)。起動すると「走る地域を選ぶ」画面が出て、Tab のメニューの「走る地域を変える」でも切り替えられる
- **地域** (`maps/<地域>/`): UE のコンテンツプラグイン 1 つ。`<レベル名>.uplugin`、地域のアセット (`Content/`: レベル・タイル・遠景・地図)、
  コースの設定 (`areas/<地域>.json` とタイル)、作り直しの記録 (`SetupState.json`)。UE の中では `/<レベル名>/Maps/<レベル名>`
- 地域を足す: コアで `py -3 tools\kit\area_picker.py` (範囲を描いて書き出すと `maps/<地域>/` ができる) か
  `py -3 tools\kit\install_kit.py . --add-region ..\maps\<地域> --title <表示名>`、そのあと `py -3 tools\kit\make_diorama.py <地域>`
- キットを直したら `py -3 tools\map_kit\kit\install_kit.py touring` でコアへ入れ直す (全地域に効く)

| フォルダ | 中身 |
| --- | --- |
| `tools/map_kit/` | 仕組みの本体 (使い方は [tools/map_kit/README.md](tools/map_kit/README.md)) |
| `touring/` | ツーリングシミュレータのコア (UE プロジェクト TouringSim) |
| `maps/` | 地域 (1 地域 1 フォルダ)。コアへ移す前の地域は、まだ地域ごとの UE プロジェクトのまま |
| `maps/sikanosima/` | 志賀島・海の中道 (UE プロジェクト Sikanosima、レベル `/Game/FukuokaDrive/Maps/Sikanosima`、タイル 7 枚) |

## 地域

| 地域 | フォルダ | コース | 備考 |
| --- | --- | --- | --- |
| 志賀島・海の中道 | `maps/sikanosima/` | `sikanosima` | 道路・区画線・神社・線路と駅 (JR 香椎線) あり、電柱・街灯・ガードレールなし |

糸島一周は別のリポジトリ (fukuoka_drive) にあります。

## 決まりごと

- UE の組み立ては GUI のエディタで行う (ヘッドレスで `setup_project.py` を動かすと海が崩れる)
- 新しい地域は `maps/<地域>/` に、コアの地域として作る (上の「地域を足す」)
- 仕組みは `tools/map_kit` で直し、`install_kit.py` でコアへ入れ直す
- コアで一度に組み立てる地域は 1 つ (`touring/tools/terrain/course.txt` が選ぶ)。2 つのスレッドが同時に組み立てない
- UE のアセットは Git LFS。データ作りの途中のもの (`tools/terrain/out/`) はコミットしない
