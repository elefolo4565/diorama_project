# 植物を作る順番

植物は地方ごとに、この表の上から順に作ります。**いまの地方の、まだ作っていない種類のうち、いちばん上のものから**作ってください。
表に無い種類は作りません (足したいときはオーナーか Claude が表に足します)。
いまの地方がすべて済んだら、次の地方の表をオーナーか Claude が書くまで待ちます。

地方の順: 九州 → **沖縄** → 四国 → 中国 → 関西 → 中部 → 関東 → 東北 → 北陸 → 北海道

1 種類の形は 2〜3 本 (A/B/C)。1 つの地方は 20 種類くらいまで。
`regions` には、その種類が自然に生える地方をすべて書きます (九州で作ったヤマモモは四国・中国…でも使う)。
次の地方では、すでにある種類で足りるものは作り直さず、`regions` に地方を足すだけにします。

## 九州 (Claude 版・Codex 版がそろい、オーナーが選ぶ)

| 状態 | 和名 | 学名 | 置く所 (habitat) | メモ |
| --- | --- | --- | --- | --- |
| 済 | ヤマモモ | Morella rubra | forest, coast | `yamamomo.py` (コードの見本) |
| 済 | ウバメガシ | Quercus phillyraeoides | coast, ridge | 海岸の崖の低い木。小さく硬い葉。`ubamegashiopus.py` (Claude) を置く。Codex 版は見比べて外し `_ubamegashi/` に残す |
| | トベラ | Pittosporum tobira | coast | 海岸の低木 (1〜3m)、丸くこんもり。Claude 版 `toberaopus.py` あり (Codex 版と見比べ中) |
| | ハマヒサカキ | Eurya emarginata | coast | 海岸の低木、潮風で刈り込まれた形。Claude 版 `hamahisakakiopus.py` あり (Codex 版と見比べ中) |
| 済 | シャリンバイ | Rhaphiolepis indica var. umbellata | coast | 海岸の低木、春に白い花 (seasons で花の形を分けてもよい)。Claude 版 `sharinbaiopus.py` あり (Codex 版と見比べ中) |
| | ヤブツバキ | Camellia japonica | forest | 林の中の小高木、冬〜春に赤い花。Claude 版 `yabutsubakiopus.py` あり (Codex 版と見比べ中) |
| | アラカシ | Quercus glauca | forest | 里山のカシ、濃い緑。Claude 版 `arakashiopus.py` あり (Codex 版と見比べ中) |
| | マテバシイ | Lithocarpus edulis | forest, coast | 大きな葉、株立ち。Claude 版 `matebashiiopus.py` あり (Codex 版と見比べ中) |
| | イスノキ | Distylium racemosum | forest | 社寺林の常緑高木。Claude 版 `isunokiopus.py` あり (Codex 版と見比べ中) |
| | アカメガシワ | Mallotus japonicus | farm | 道ばた・畑のふちの落葉樹、赤い新芽。Claude 版 `akamegashiwaopus.py` あり (4 季、Codex 版と見比べ中) |
| | ウラジロ | Gleichenia japonica | understory | 森の足もとのシダ (大きな群れ)。Claude 版 `urajiroopus.py` あり (Codex 版と見比べ中) |
| | コシダ | Dicranopteris linearis | understory | 森の足もとのシダ (日当たりのよい所)。Claude 版 `koshidaopus.py` あり (Codex 版と見比べ中) |
| | アオキ | Aucuba japonica | understory | 森の中の低木 (1〜2m)。Claude 版 `aokiopus.py` あり (Codex 版と見比べ中) |
| | ネザサ | Pleioblastus argenteostriatus f. glaber | understory, farm | 林のふち・あぜのササ。Claude 版 `nezasaopus.py` あり (2 季、Codex 版と見比べ中) |
| | ススキ | Miscanthus sinensis | grassland, farm | 草原・あぜ。秋は穂 (seasons で穂の形を分ける)。Claude 版 `susukiopus.py` あり (3 季、Codex 版と見比べ中) |
| | ソテツ | Cycas revoluta | coast | 南九州の海岸 (kyushu だけ)。Claude 版 `sotetsuopus.py` あり (Codex 版と見比べ中) |

## 沖縄 (いまの地方)

九州で作った種類のうち、ウラジロ・コシダは `regions` に okinawa が入っているので作り直さない。ソテツ・ススキ・ハマヒサカキ・トベラは、採用した版の `regions` に Claude が okinawa を足す。

| 状態 | 和名 | 学名 | 置く所 (habitat) | メモ |
| --- | --- | --- | --- | --- |
| | リュウキュウマツ | Pinus luchuensis | forest, ridge | 沖縄の山と海岸の代表のマツ。笠のように横に広がる樹冠 |
| | ガジュマル | Ficus microcarpa | forest, farm | 気根が垂れ下がり幹のように太る大木。集落・道ばたにも |
| | アダン | Pandanus odoratissimus | coast | 砂浜の奥の低木。タコ足の支柱根、らせん状の長い葉、パイナップルのような実 |
| | フクギ | Garcinia subelliptica | farm | 集落の防風林。まっすぐな幹に厚い葉が密な縦長の樹形 |
| | テリハボク | Calophyllum inophyllum | coast | 海岸の常緑高木。つやのある丸い葉、防潮林 |
| | オオハマボウ | Hibiscus tiliaceus | coast | 海岸・河口の低木〜小高木。ハート形の葉、黄色い花 (夏) |
| | クサトベラ | Scaevola taccada | coast | 砂浜の低木。明るい緑のへら形の葉がこんもり |
| | モンパノキ | Heliotropium foertherianum | coast | 砂浜の低木。銀白色の毛に覆われた葉 |
| | ビロウ | Livistona chinensis var. subglobosa | coast, forest | ヤシの仲間。扇形の大きな葉が垂れる |
| | スダジイ | Castanopsis sieboldii | forest | やんばるの森の主役 (イタジイ)。ブロッコリーのような樹冠、春に黄色い花 |
| | オキナワウラジロガシ | Quercus miyagii | forest | やんばるのカシの大木。板根、葉の裏が白い |
| | アカギ | Bischofia javanica | forest, farm | 大きく広がる常緑高木。赤みのある樹皮、3 枚の小葉 |
| | フカノキ | Schefflera heptaphylla | forest | 森の中の小高木。手のひら形の葉 |
| | ヒカゲヘゴ | Sphaeropteris lepifera | forest | 大きな木生シダ (5〜10m)。幹の頂に長い葉が放射状、葉の付け根の跡が模様に |
| | クワズイモ | Alocasia odora | understory | 森の足もとの大きなサトイモの仲間。1m ほどの巨大な葉 |
| | ゲットウ | Alpinia zerumbet | understory, farm | 道ばた・林のふちのショウガの仲間 (2m)。初夏に白とピンクの花房 |
| | リュウキュウチク | Pleioblastus linearis | grassland, ridge | 尾根・荒れ地の細いササのやぶ |
| | アコウ | Ficus superba var. japonica | farm, coast | 集落・海岸の大木。春と秋に一斉に落葉して新芽 |
| | グンバイヒルガオ | Ipomoea pes-caprae | coast | 砂浜をはうつる草。軍配形の葉、桃色の花 (夏) |
| | チガヤ | Imperata cylindrica | grassland, farm | 草原・あぜの草。初夏に白い穂 |
