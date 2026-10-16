# 植物を作る順番

植物は地方ごとに、この表の上から順に作ります。**いまの地方の、まだ作っていない種類のうち、いちばん上のものから**作ってください。
表に無い種類は作りません (足したいときはオーナーか Claude が表に足します)。
いまの地方がすべて済んだら、次の地方の表をオーナーか Claude が書くまで待ちます。

地方の順: **九州** → 沖縄 → 四国 → 中国 → 関西 → 中部 → 関東 → 東北 → 北陸 → 北海道

1 種類の形は 2〜3 本 (A/B/C)。1 つの地方は 20 種類くらいまで。
`regions` には、その種類が自然に生える地方をすべて書きます (九州で作ったヤマモモは四国・中国…でも使う)。
次の地方では、すでにある種類で足りるものは作り直さず、`regions` に地方を足すだけにします。

## 九州 (いまの地方)

| 状態 | 和名 | 学名 | 置く所 (habitat) | メモ |
| --- | --- | --- | --- | --- |
| 済 | ヤマモモ | Morella rubra | forest, coast | `yamamomo.py` (コードの見本) |
| 済 | ウバメガシ | Quercus phillyraeoides | coast, ridge | 海岸の崖の低い木。小さく硬い葉。`ubamegashiopus.py` (Claude) を置く。Codex 版は見比べて外し `_ubamegashi/` に残す |
| | トベラ | Pittosporum tobira | coast | 海岸の低木 (1〜3m)、丸くこんもり。Claude 版 `toberaopus.py` あり (Codex 版と見比べ中) |
| | ハマヒサカキ | Eurya emarginata | coast | 海岸の低木、潮風で刈り込まれた形。Claude 版 `hamahisakakiopus.py` あり (Codex 版と見比べ中) |
| | シャリンバイ | Rhaphiolepis indica var. umbellata | coast | 海岸の低木、春に白い花 (seasons で花の形を分けてもよい)。Claude 版 `sharinbaiopus.py` あり (Codex 版と見比べ中) |
| | ヤブツバキ | Camellia japonica | forest | 林の中の小高木、冬〜春に赤い花。Claude 版 `yabutsubakiopus.py` あり (Codex 版と見比べ中) |
| | アラカシ | Quercus glauca | forest | 里山のカシ、濃い緑。Claude 版 `arakashiopus.py` あり (Codex 版と見比べ中) |
| | マテバシイ | Lithocarpus edulis | forest, coast | 大きな葉、株立ち。Claude 版 `matebashiiopus.py` あり (Codex 版と見比べ中) |
| | イスノキ | Distylium racemosum | forest | 社寺林の常緑高木 |
| | アカメガシワ | Mallotus japonicus | farm | 道ばた・畑のふちの落葉樹、赤い新芽 |
| | ウラジロ | Gleichenia japonica | understory | 森の足もとのシダ (大きな群れ) |
| | コシダ | Dicranopteris linearis | understory | 森の足もとのシダ (日当たりのよい所) |
| | アオキ | Aucuba japonica | understory | 森の中の低木 (1〜2m) |
| | ネザサ | Pleioblastus argenteostriatus f. glaber | understory, farm | 林のふち・あぜのササ |
| | ススキ | Miscanthus sinensis | grassland, farm | 草原・あぜ。秋は穂 (seasons で穂の形を分ける) |
| | ソテツ | Cycas revoluta | coast | 南九州の海岸 (kyushu だけ) |
