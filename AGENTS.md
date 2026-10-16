# AGENTS.md — 植物 (木・低木・草花・シダ) を足す人と AI へ

このリポジトリは、国土地理院と OpenStreetMap のデータから日本の地域を UE 5.8 のジオラマにします
(使い方は [tools/map_kit/README.md](tools/map_kit/README.md))。
ここに書くのは、**植物 (木・低木・草花・シダ) を UE を使わずに足すとき**の決まりです。
UE への取り込み・配置・見た目の確認は、マージの後にオーナーの PC で行います。

植物の足し方は 2 通りあり、どちらも同じ検査 (`plants/check.py`) を通して同じように置かれます。
- **A. ファイル**: Blender などで作った `.glb` と葉・樹皮の PNG を、`plants/<種類>/` に `plant.json` と一緒に置く
- **B. コード**: 形と絵を作る Python を `plants/<種類>.py` に書く (見本 [plants/yamamomo.py](tools/map_kit/terrain/plants/yamamomo.py))

## 守ること
- 種類は **日本に自然に生える植物だけ** (外来の園芸種や欧州の種類は入れない)
- **作る種類と順番は [plants/PLAN.md](tools/map_kit/terrain/plants/PLAN.md) の表のとおり** (九州 → 沖縄 → 四国 → 中国 → 関西 → 中部 → 関東 → 東北 → 北陸 → 北海道)。
  いまの地方の、まだ作っていない種類のいちばん上から作る。表に無い種類は作らない。表が済んだら次の指示を待つ。
  作った種類は、同じ PR で PLAN.md の「状態」を「済」にする (PLAN.md で変えてよいのはそこだけ)
- **外部のアセット・画像・3D モデルを使わない**。形も葉の絵も自分で作る (無料・ライセンスの心配なし)
- **写真を「見て」形の参考にするのはよい** (樹冠の形・幹の分かれ方・葉の大きさと色をつかむため)。そのときの決まり:
  - 使ってよい写真: 利用条件が許すもの (Wikimedia Commons のパブリックドメイン・CC0・CC BY / CC BY-SA など。1 枚ごとにライセンスを確かめる)。
    AI の利用やスクレイピングを禁じているサイト、ストックフォトのサイトは使わない。迷ったら使わない
  - 写真を絵や形に写さない (葉の絵に貼る・なぞる・色を吸い取る、はしない)。見て特徴をつかみ、自分で描く・作る
  - 写真をリポジトリに入れない (`plants/` にもコミットにも入れない)。PR の説明に、見た写真の URL とライセンスを書く
  - 1 種類あたり 2〜3 枚 (木全体、葉の近く、幹) くらいで十分
- **`plants/notes/<種類>.md` (特徴メモ) があれば、それを見た目の基準にする** (樹形・幹・葉・花の数字と言葉。書き方は `plants/notes/README.md`)。
  メモと違う形にするときは、PR の説明に理由を書く
- キット側に依存ライブラリを足さない (`plants/` のコードで使えるのは numpy と Pillow だけ。Blender は作る側で使うのは自由)
- 変えてよいのは `tools/map_kit/terrain/plants/` に **新しい種類を足すこと** (と、自分が足した種類を直すこと) だけ
  - 変えない: `plants/__init__.py`・`plants/check.py` (受け口と検査)、`plants/` にある他の人の種類、
    `build_scenery.py`・`foliage.py`・`flowers.py`・`scenery_meshes.py`・`bark.py` (読んで部品を使うのは可)、
    `tools/map_kit/ue/`、`tools/map_kit/Source/`、`maps/` (各地域のフォルダはキットの入れ直しで上書きされる)、`Content/`
  - 受け口に足りない所があれば、コードを変えずに PR の説明に書く
- コメントと文書は日本語で、既存のコードと同じ書き方にする

## A. ファイルで足す (.glb)
`tools/map_kit/terrain/plants/<種類のローマ字>/` に置く (例 `plants/ubamegashi/`):

```
plants/ubamegashi/
  plant.json                     種類の説明と置き方
  SM_FD_Ubamegashi_A.glb         形 (1 つの形 = 1 ファイル。A/B/C で 2〜3 本の違う形があると森が単調にならない)
  SM_FD_Ubamegashi_B.glb
  T_FD_Leaf_Ubamegashi.png       葉の絵
  T_FD_BarkUbamegashi_D.png      樹皮の色 (既存の樹皮を使うなら不要)
  T_FD_BarkUbamegashi_N.png      樹皮の凹凸 (法線)
```

`plant.json`:
```json
{
  "name_ja": "ウバメガシ",
  "latin": "Quercus phillyraeoides",
  "regions": ["kyushu", "shikoku", "chugoku", "kansai", "chubu", "kanto"],
  "leaves": {"FD_Leaf_Ubamegashi": "T_FD_Leaf_Ubamegashi.png"},
  "barks": {"FD_BarkUbamegashi": ["T_FD_BarkUbamegashi_D.png", "T_FD_BarkUbamegashi_N.png"]},
  "meshes": {
    "SM_FD_Ubamegashi_A": {"file": "SM_FD_Ubamegashi_A.glb", "height_m": 5.0, "habitat": ["coast"], "share": 0.10},
    "SM_FD_Ubamegashi_B": {"file": "SM_FD_Ubamegashi_B.glb", "height_m": 3.5, "habitat": ["coast", "ridge"], "share": 0.05, "seasons": 15}
  }
}
```

### .glb の決まり
| 項目 | 決まり |
| --- | --- |
| 形式 | glTF 2.0 の `.glb` 1 ファイル。**絵は入れない** (Blender の書き出しで Images を「None」)。PNG は別に置く |
| 単位・向き | メートル。Blender の Z 上のまま作り、書き出しは既定の「+Y Up」。前後の向きは自由 (向きは置くときにランダム) |
| 原点 | 根元の地面の中心 = (0, 0, 0)。移動・回転・拡大は Apply してから書き出す (ノードに残さない) |
| メッシュ | 1 つにまとめ (Join)、メッシュ名とオブジェクト名を `SM_FD_<種類>_<A/B/C>` にする。マテリアルは何個でもよい (葉・樹皮など) |
| 三角形の数 | 高さ 3m 以上: 2,000〜25,000。それより低いもの: 100〜4,000 (数万本並ぶため) |
| 大きさ | `.glb` は 8 MB まで |
| 必要な頂点の値 | 位置・法線・UV (葉と樹皮)。頂点の色 (COLOR_0) は任意で、R を「奥ほど暗く」の陰として使う (0..1) |
| 法線 | 葉の板は、樹冠の中心から外向きにそろえると樹冠全体が丸く光る (既存の木の作り方。任意) |
| LOD・当たり判定・骨・アニメーション | 入れない (UE で Nanite にし、当たり判定は無し) |
| 葉の板の裏 | 裏面は要らない (UE の葉のマテリアルは両面)。入れてもよい |

### マテリアル
- 葉・花: `FD_Leaf_<種類>` / `FD_Flower_<種類>` → `plant.json` の `leaves` に絵を書く。UE で葉用のマテリアル (切り抜き・透過光・風) に差し替わる
- 樹皮: `FD_Bark<種類>` → `barks` に絵を書く。既存の樹皮 `FD_Bark` (シイ・タブ)・`FD_PineBark`・`FD_BarkCedar` をそのまま使ってもよい (その名前にするだけ)
- 絵の無い単色: `FD_<名前>` (色と粗さは .glb の値を使う)。`Material.001` などのままにしない

## B. コードで足す (.py)
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
| 葉の絵 | `T_<マテリアル名>.png` | `T_FD_Leaf_Yamamomo.png` |
| 樹皮の絵 | `T_<マテリアル名>_D.png` と `_N.png` (法線) | `T_FD_BarkSakura_D.png` |
| 種類のフォルダ・ファイル | ローマ字の小文字 | `ubamegashi/`、`yamamomo.py` |

## 絵 (PNG) の決まり (A・B 共通)
- 葉・花: 1024x1024、RGBA。葉の無い所はアルファ 0 (UE はアルファ 0.4 未満を切り抜く)。葉の所が全体の 10〜90%。
  小枝ごと何枚かを 1 枚に並べ (既存は 2x2)、板ごとに違う所を貼ると単調にならない。透明な所の色は近くの葉の色で埋める (縮小で縁が黒くならない)
- 樹皮: 色 `_D` と法線 `_N`、1024x1024 程度、上下左右につながる模様。法線の向きは `bark.py` の `normal_map` と同じ
- 色は写真のような明るさの sRGB。光や影を絵に描き込みすぎない (UE の光で付く)

既存の名前 (`scenery_meshes.MATERIALS`、`build_scenery.TREE_KINDS`) と同じ名前は使わない。

## 形の決まり (B. コード)
- `scenery_meshes.Mesh` で作る。単位はメートル、Z が上、原点は根元の地面の中心
- 乱数は `scenery_meshes.Rng(seed)` (同じ seed なら同じ形になること。`random` や `numpy.random` を直接使わない)
- 葉は既存の木と同じ「葉の板」: `foliage.Foliage` と `foliage.clump`、幹と枝は `bark.bark_tube`。
  葉の板の法線は樹冠の中心から外向き、明るさ (頂点の色) は樹冠の奥ほど暗く
- 三角形の数と原点は .glb と同じ

## 置く所 (`habitat`) と割合 (`share`)
- 木を入れ替える: `"coast"` 海岸、`"forest"` 森、`"ridge"` 標高 60m 以上の森、`"farm"` 田畑のあぜ、`"grassland"` 草原
  → その所の木のうち `share` の割合がこの種類になる (例 0.05 = 5%)
- 木に足す: `"understory"` 森の木の足もと (シダ・低木・ササなど) → 森の木 1 本ごとに `share` の確率で 1 株
- `regions` (必須): その種類が自然に生える地方 (`kyushu` `okinawa` `shikoku` `chugoku` `kansai` `chubu` `kanto` `tohoku` `hokuriku` `hokkaido`)。
  ジオラマのコースの中心に近い県庁所在地の地方の植物だけが置かれる。コードの植物は PLANTS の各値に `regions=(...)` と書く
- `seasons`: 見える季節のビット (1 春, 2 夏, 4 秋, 8 冬。省略 = 15 = 一年中)
- `place_with`: 季節で見た目が変わる種類 (花・紅葉・落葉) は、同じ枝の形で葉の絵だけ変えた形を作り、
  `"place_with": "<相手のメッシュ名>"` を書く。相手と同じ位置・向きに置かれ、seasons で入れ替わる (seasons は相手と重ねない)。
  見本: `plants/yabutsubakiopus.py` (夏・秋は葉だけ、冬・春は赤い花)
- **季節の形は特徴メモの「季節の形」のとおりに作る** (メモに無ければ一年中 1 つの形でよい)。そのうえで必ず:
  - 落葉樹は冬の形 (幹と枝だけ。葉の板を除き、細い枝先まで見えるようにする) を作る。葉のある形と枝は同じ
  - 冬に枯れる草 (ススキなど) は冬の枯れ色の形 (茶色〜薄い黄土色、穂や葉の名残) を作る
  - 4 つの季節 (1 春, 2 夏, 4 秋, 8 冬) で必ずどれか 1 つの形が見えるようにする (すき間も重なりも作らない)
- 割合は目安。合計が大きくなりすぎたら Claude が調整する

## 見た目の質 (A・B 共通。PR の前にこの順で確かめる)
「木の形の一般形」ではなく「その種類らしい形」を作る。ウバメガシでは、Claude 版 (`plants/ubamegashiopus.py`) は採用、
Codex 版 (`plants/_ubamegashi/`) は不採用だった。理由は下の 1〜4 で、まず両方の preview を見比べてから作り始める。

1. **作る前に樹形を言葉で決め、README.md に書く**。図鑑や植生の知識から、次を決める。
   - 単幹か株立ちか
   - 幹が見えている高さ (樹高の何割か)
   - 樹冠の形 (球・半球・横長・円錐・枝垂れ)
   - 枝の出る角度
   - 海風で傾くか
   例: ウバメガシは根元から何本も細い幹が立つ低木〜小高木で、樹冠は地面近くまで下がる。
   「まっすぐな 1 本の幹の上に丸い葉の塊が乗る」形 (棒付きキャンディ) は、ほとんどの種類で不正解。
2. **樹冠**
   - 下端を水平に切らない。下の方ほど房をまばらにして、縁が自然にばらけるようにする。
   - 葉の板は樹冠の表面近くに房 (クランプ) で置き、中は空ける。房の大きさをばらつかせ、輪郭に凹凸を出す。
   - 奥と下ほど暗くする (頂点の色)。一様な緑の塊にしない。
3. **幹と枝**
   - 根元が太く、先へ行くほど細くする。幹は樹冠の中へ入って枝分かれし、樹冠の下で終わらない。
   - 太さは樹高に合わせる。低木の幹を太くしすぎない。
4. **A/B/C のちがい**: 同じ形を縮小しない。若木と老木、風の当たる所と陰になる所など、生え方のちがいで形を変える
   (傾き・幹の数・樹冠の幅)。並べたときに別の個体に見えること。
5. **確かめる**: check.py の preview の正面と横を見て、1 で書いた樹形と合わなければ直す。
   最低 2 回は直してから PR を出す。PR の説明には、1 の樹形の説明と、直した点を書く。

## 確かめ方 (PR の前に必ず)
```
cd tools/map_kit/terrain
python plants/check.py <種類>      # 例: python plants/check.py ubamegashi (フォルダ) / yamamomo (コード)
```
- `plant.json` と `.glb` の中身・名前・マテリアルと絵・三角形の数・大きさと原点・葉の絵の透過・同じ形になるかを調べ、最後に `OK` と出れば合格
- `out/plants/<種類>_preview.png` (正面・横・真上と葉の絵) ができる。**この画像を見て形を直し、PR の説明に貼る**
  (簡単な描画なので、葉の茂り方・幹の形・大きさの確認用。光や色の最終的な見え方は UE で確かめる)
  (Blender で描いた画像があれば、それも一緒に貼ってよい)
- `out/` はコミットしない。`.blend` や制作スクリプトはコミットしない (作る側で保管する)
- `.glb` と PNG は Git LFS で入る (`.gitattributes`)。push する所に `git lfs` を入れておく

## PR の出し方
- ブランチ `codex/plant-<種類>` から `main` へ。1 PR = 1〜3 種類
- 説明に書くこと: 和名と学名、どこに生えるか (habitat と share の理由)、三角形の数、`check.py` の結果、プレビュー画像
- マージの後、Claude がキットを各地域へ入れ直し、オーナーの PC で取り込んで、オーナーが走って見た目を確かめる
