# 志賀島を地域ごとのプロジェクトからコアへ移す手順 (PC で 1 回だけ)

2026-10-16 オーナーの決定 (「1 つにまとめる」) と PR #70 の続き。PC の Claude (Remote Control) が行う。
コアは `touring/TouringSim.uproject`。地域は `maps/<地域>/` のコンテンツプラグイン。C++ のモジュール名は FukuokaDrive のまま。

1. UE をすべて閉じる。`git pull` で main を最新にする (手元の変更は消さずに stash する)
2. コアの C++ をビルドする: `touring\tools\ue\build.bat`。クラウドではコンパイルできていないので、
   エラーが出たら `tools/map_kit/Source` を直し、`py -3 tools\map_kit\kit\install_kit.py touring` でコアへ写す
3. 古いプロジェクトから持っていくものを退避する (Git の外):
   - コースの設定: `maps/sikanosima/tools/terrain/areas/sikanosima.json` と `areas/sikanosima/`
   - ダウンロード済みのデータ: `maps/sikanosima/tools/terrain/out/*` を `touring/tools/terrain/out/` へ写す (ダウンロードのやり直しを省く)
4. 古いプロジェクトを片付ける: `maps/sikanosima` の .uproject・Source・Config・Content・tools・Screenshots・.gitattributes・.gitignore を
   `git rm` し、Binaries・Intermediate・Saved・DerivedDataCache も消す (プラグインの中身として読まれないように。Git の履歴には残る)
5. 地域にする: `py -3 touring\tools\kit\install_kit.py touring --add-region ..\maps\sikanosima --title 志賀島・海の中道`、
   退避したコースの設定を `maps/sikanosima/areas/` へ戻す (`areas/sikanosima.json` と `areas/sikanosima/<タイル>.json`)
6. 組み立てる: `py -3 touring\tools\kit\make_diorama.py sikanosima --ue` (GUI のエディタ。ヘッドレスで setup_project を動かさない)。
   2 回目の setup_project が「作り直したもの: なし」になること
7. 確かめる: 再生 → 起動画面「走る地域を選ぶ」→ 志賀島 → 走れる、M の地図とファストトラベル、Tab の「走る地域を変える」
8. PC からコミットする: `touring/` (Content と SetupState.json) と `maps/sikanosima/`。オーナーの .uproject や .mcp.json の手元の変更は入れない。
   ブランチを push し、PR にしてスレッドで知らせる
