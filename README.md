# diorama_project

国土地理院と OpenStreetMap のデータから、日本の地域を走れるジオラマ (UE 5.8) にするプロジェクトの置き場です。
仕組み (キット) と、地域ごとの UE プロジェクトを 1 つのリポジトリにまとめています。

| フォルダ | 中身 |
| --- | --- |
| `tools/map_kit/` | 仕組みの本体 (使い方は [tools/map_kit/README.md](tools/map_kit/README.md)) |
| `maps/` | 地域ごとの UE プロジェクト (1 地域 1 フォルダ) |
| `maps/sikanosima/` | 志賀島・海の中道 (UE プロジェクト Sikanosima、レベル `/Game/FukuokaDrive/Maps/Sikanosima`、タイル 7 枚) |

## 地域

| 地域 | フォルダ | コース | 備考 |
| --- | --- | --- | --- |
| 志賀島・海の中道 | `maps/sikanosima/` | `sikanosima` | 道路・区画線・神社・線路と駅 (JR 香椎線) あり、電柱・街灯・ガードレールなし |

糸島一周は別のリポジトリ (fukuoka_drive) にあります。

## 決まりごと

- UE の組み立ては GUI のエディタで行う (ヘッドレスで `setup_project.py` を動かすと海が崩れる)
- 新しい地域は `maps/<地域>/` に作る (`py -3 tools\map_kit\kit\install_kit.py maps\<地域> --create <名前>`)
- 仕組みは `tools/map_kit` で直し、`install_kit.py` で各地域へ入れ直す
- UE のアセットは Git LFS。データ作りの途中のもの (`tools/terrain/out/`) はコミットしない
