# AGENTS.md — 植物 (木・低木・草花・シダ) を足す人と AI へ

このリポジトリは、国土地理院と OpenStreetMap のデータから日本の地域を UE 5.8 のジオラマにします
(使い方は [tools/map_kit/README.md](tools/map_kit/README.md))。
ここに書くのは、**植物の形と葉の絵を作る Python コードを、UE を使わずに足すとき**の決まりです。
UE への取り込み・配置・見た目の確認は、マージの後にオーナーの PC で行います。

## 守ること
- 種類は **日本 (福岡・糸島・志賀島のあたり) に実際に生える植物だけ**。外来の園芸種や欧州の種類は入れない
- **外部のアセット・画像・3D モデルを使わない / ダウンロードしない**。形も葉の絵もコードで生成する (無料・ライセンスの心配なし)
- 依存ライブラリを足さない (numpy と Pillow だけ。`tools/map_kit/terrain/requirements.txt`)
- 変えてよいのは `tools/map_kit/terrain/plants/` に **新しいファイルを足すこと** だけ
  - 変えない: `plants/__init__.py`・`plants/check.py` (受け口と検査)、`plants/` にある他の人の種類、
    `build_scenery.py`・`foliage.py`・`flowers.py`・`scenery_meshes.py`・`bark.py` (読んで部品を使うのは可)、
    `tools/map_kit/ue/`、`tools/map_kit/Source/`、`maps/` (各地域のフォルダはキットの入れ直しで上書きされる)、`Content/`
  - 受け口に足りない所があれば、コードを変えずに PR の説明に書く
- コメントと文書は日本語で、既存のコードと同じ書き方にする

## ファイルの置き方 (1 種類 = 1 ファイル)
`tools/map_kit/terrain/plants/<種類のローマ字>.py` (例 `yamamomo.py`)。**[plants/yamamomo.py](tools/map_kit/terrain/plants/yamamomo.py) が見本**です。
ファイルは次を定義します (詳しくは `plants/__init__.py` の説明):

| 名前 | 中身 |
| --- | --- |
| `PLANTS` | `{メッシュ名: dict(make=形を作る関数, height_m=高さの目安, habitat=(置く所, ...), share=割合, seasons=季節)}` |
| `MATERIALS` | 足すマテリアル (`scenery_meshes.MATERIALS` と同じ書き方。色はリニア) |
| `LEAVES` | 葉・花の絵 `{マテリアル名: (PNG の名前, draw(path))}` |
| `BARKS` | 樹皮の絵 `{マテリアル名: (色の PNG, 法線の PNG, draw(color_path, normal_path))}`。既存の `FD_Bark` などを使うなら不要 |

## 名前の決まり (UE 側はこの名前で取り込み方を変える)
| もの | 形式 | 例 |
| --- | --- | --- |
| メッシュ | `SM_FD_<種類>_<A/B/C>` | `SM_FD_Yamamomo_A` |
| 葉・花のマテリアル | `FD_Leaf_<種類>` / `FD_Flower_<種類>` (UE で葉用のマテリアルに差し替わる) | `FD_Leaf_Yamamomo` |
| 樹皮のマテリアル | `FD_Bark<種類>` (`_` を入れない) | `FD_BarkSakura` |
| 葉の絵 | `T_<マテリアル名>.png`、1024x1024、RGBA、葉の無い所はアルファ 0 | `T_FD_Leaf_Yamamomo.png` |
| 樹皮の絵 | `T_<マテリアル名>_D.png` と `_N.png` (法線) | |

既存の名前 (`scenery_meshes.MATERIALS`、`build_scenery.TREE_KINDS`) と同じ名前は使わない。

## 形の決まり
- `scenery_meshes.Mesh` で作る。単位はメートル、Z が上、原点は根元の地面の中心
- 乱数は `scenery_meshes.Rng(seed)` (同じ seed なら同じ形になること。`random` や `numpy.random` を直接使わない)
- 葉は既存の木と同じ「葉の板」: `foliage.Foliage` と `foliage.clump`、幹と枝は `bark.bark_tube`。
  葉の板の法線は樹冠の中心から外向き、明るさ (頂点の色) は樹冠の奥ほど暗く
- 三角形の数: 高さ 3m 以上は 2,000〜25,000、それより低いものは 100〜4,000 (数万本並ぶため)
- 当たり判定は作らない (UE 側で無しにする)

## 置く所 (`habitat`) と割合 (`share`)
- 木を入れ替える: `"coast"` 海岸、`"forest"` 森、`"ridge"` 標高 60m 以上の森、`"farm"` 田畑のあぜ、`"grassland"` 草原
  → その所の木のうち `share` の割合がこの種類になる (例 0.05 = 5%)
- 木に足す: `"understory"` 森の木の足もと (シダ・低木・ササなど) → 森の木 1 本ごとに `share` の確率で 1 株
- `seasons`: 見える季節のビット (1 春, 2 夏, 4 秋, 8 冬。省略 = 15 = 一年中)
- 割合は目安。合計が大きくなりすぎたら Claude が調整する

## 確かめ方 (PR の前に必ず)
```
cd tools/map_kit/terrain
python plants/check.py <種類>      # 例: python plants/check.py yamamomo
```
- 名前・マテリアルと絵・三角形の数・大きさと原点・葉の絵の透過・同じ形になるかを調べ、最後に `OK` と出れば合格
- `out/plants/<種類>_preview.png` (正面・横・真上と葉の絵) ができる。**この画像を見て形を直し、PR の説明に貼る**
  (簡単な描画なので、葉の茂り方・幹の形・大きさの確認用。光や色の最終的な見え方は UE で確かめる)
- `out/` はコミットしない

## PR の出し方
- ブランチ `codex/plant-<種類>` から `main` へ。1 PR = 1〜3 種類
- 説明に書くこと: 和名と学名、どこに生えるか (habitat と share の理由)、三角形の数、`check.py` の結果、プレビュー画像
- マージの後、Claude がキットを各地域へ入れ直し、オーナーの PC で取り込んで、オーナーが走って見た目を確かめる
