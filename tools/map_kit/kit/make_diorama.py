"""コースの設定 1 つから、走れる UE のレベルまでを通しで作る (途中で止まっても、もう一度実行すれば続きから)。

使い方 (PC で。tools/terrain/areas/<コース名>.json を先に書いておく。地図で範囲を描くなら tools/kit/area_picker.py):
    py -3 tools/kit/make_diorama.py <コース名>             すべて
    py -3 tools/kit/make_diorama.py <コース名> --data      データ作り (国土地理院・OSM) だけ。UE には触らない
    py -3 tools/kit/make_diorama.py <コース名> --ue        UE の組み立てだけ (データはできている前提)
    py -3 tools/kit/make_diorama.py <コース名> --redo      できているデータも作り直す
    オプション:
        --max-tiles N   タイルがこれより多ければ止める (既定 20。ストリーミングを切って全部読むので、多いとメモリが足りない)
        --no-startup    起動時に開くレベルを変えない

手順と、できたかの見分け方 (tools/terrain/out/<コース名>/ の中):
    1 route    build_loop.py            loop_route.json
    2 tiles    build_tiles.py           tiles.json と、各タイルの scenery.json
    3 overpass Overpass の 504 などで建物・店が取れなかったタイルを --scenery で作り直す (最大 3 回)
    4 far      build_far_terrain.py     far/SM_FD_FarTerrain.gltf
    5 minimap  build_minimap.py         minimap.png
    6 ue       tools/ue/rebuild.bat     エディタを閉じ、C++ をビルドし、開いて setup_project.py (GUI のエディタで実行する)
    7 verify   setup_project.py をもう一度実行し「作り直したもの: なし」になるか
    8 startup  起動時に開くレベルをこのコースにする

終了コード: 0 成功 / 1 失敗 (最後に何をすればよいかを表示する)
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TERRAIN = os.path.join(ROOT, "tools", "terrain")
UE = os.path.join(ROOT, "tools", "ue")
sys.path.insert(0, TERRAIN)
sys.path.insert(0, HERE)

from course import Course  # noqa: E402


def log(msg):
    print(f"[diorama] {msg}", flush=True)


def fail(msg):
    log(f"止まりました: {msg}")
    sys.exit(1)


def py(script, *args, cwd=TERRAIN, capture=False):
    cmd = [sys.executable, script, *args]
    log("実行: " + " ".join(os.path.relpath(a, ROOT) if os.path.isabs(a) else a for a in cmd[1:]))
    if not capture:
        return subprocess.run(cmd, cwd=cwd).returncode, ""
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    out = []
    for line in p.stdout:
        print(line, end="", flush=True)
        out.append(line)
    return p.wait(), "".join(out)


def set_course(name):
    path = os.path.join(TERRAIN, "course.txt")
    want = f"# 作るコースの名前 (tools/terrain/areas/<名前>.json)。setup_project.py と rebuild.bat がこれを読む\n{name}\n"
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    if old != want:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(want)
        log(f"course.txt を {name} にしました")


def tiles_of(course):
    doc = course.tiles_doc()
    return [] if not doc else doc["tiles"]


def tile_out(course, t):
    return os.path.join(TERRAIN, "out", t["name"])


def missing_osm(course):
    """建物か店の Overpass の取得に失敗したタイル (成功すると out/<タイル>/ に json が残る)。"""
    bad = []
    for t in tiles_of(course):
        d = tile_out(course, t)
        if not all(os.path.exists(os.path.join(d, f)) for f in ("osm_buildings.json", "osm_pois.json", "scenery/scenery.json")):
            bad.append(t)
    return bad


def stage_route(course, area_path, redo, max_tiles):
    route = os.path.join(course.out_dir, "loop_route.json")
    if redo or not os.path.exists(route):
        code, _ = py("build_loop.py", area_path)
        if code:
            fail("build_loop.py が失敗しました。経由点の名前 (q) が見つからない時は lat/lon を書き足してください")
    with open(route, encoding="utf-8") as f:
        r = json.load(f)
    n = len(r["tiles"])
    if r.get("mode") == "polygon":
        log(f"多角形の範囲、タイル {n} 枚")
    else:
        log(f"道筋 {r.get('length_km', r.get('km', '?'))} km、タイル {n} 枚")
    if n > max_tiles:
        fail(f"タイルが {n} 枚あり、上限 {max_tiles} 枚を超えています。経由点を減らして区間を短くするか、"
             f"--max-tiles で上限を上げてください (ストリーミングを切っているので、多いとメモリが足りなくなる)")


def stage_tiles(course, area_path, redo):
    tiles = tiles_of(course)
    done = tiles and all(os.path.exists(os.path.join(tile_out(course, t), "scenery", "scenery.json")) for t in tiles)
    if done and not redo:
        log(f"タイル {len(tiles)} 枚はできています")
        return
    for attempt in range(3):
        code, _ = py("build_tiles.py", area_path)
        if code == 0:
            return
        log(f"build_tiles.py が失敗しました ({attempt + 1} 回目)。ダウンロードはキャッシュされるので、続きから作り直します")
        time.sleep(30)
    fail("build_tiles.py が 3 回失敗しました。上のエラーを見てください")


def stage_overpass(course, area_path):
    for attempt in range(3):
        bad = missing_osm(course)
        if not bad:
            return
        names = ", ".join(t["name"] for t in bad)
        log(f"建物や店が取れていないタイル: {names}。Overpass が混んでいる可能性があるので {60 * (attempt + 1)} 秒待って作り直します")
        time.sleep(60 * (attempt + 1))
        for t in bad:
            py("build_tiles.py", area_path, f"{t['tile'][0]},{t['tile'][1]}", "--scenery")
    bad = missing_osm(course)
    if bad:
        log(f"注意: {', '.join(t['name'] for t in bad)} は建物や店の OSM データが取れないまま進めます (後で --scenery で作り直せます)")


def stage_far_and_minimap(course, area_path, redo):
    if redo or not os.path.exists(os.path.join(course.out_dir, "far", "SM_FD_FarTerrain.gltf")):
        if py("build_far_terrain.py", area_path)[0]:
            fail("build_far_terrain.py が失敗しました")
    if redo or not os.path.exists(os.path.join(course.out_dir, "minimap.png")):
        if py("build_minimap.py", area_path)[0]:
            fail("build_minimap.py が失敗しました")


def stage_ue(course):
    if os.name != "nt":
        fail("UE の組み立ては Windows の PC で実行してください")
    log("UE: エディタを閉じて C++ をビルドし、開き直して setup_project.py を実行します (初回は 30 分ほど)")
    code = subprocess.run(["cmd", "/c", os.path.join(UE, "rebuild.bat")], cwd=ROOT).returncode
    if code:
        fail("rebuild.bat が失敗しました。ビルドのエラーなら上の C++ のエラーを、エディタを閉じられない時は"
             "保存の確認ダイアログが出ていないかを確かめてください")
    log("確認: setup_project.py をもう一度実行し、何も作り直さないことを確かめます")
    code, out = py(os.path.join(UE, "editor.py"), "run", os.path.join(UE, "setup_project.py"), cwd=ROOT, capture=True)
    if code:
        fail("2 回目の setup_project.py が失敗しました")
    last = [l for l in out.splitlines() if "完了 (作り直したもの:" in l]
    if not last:
        fail("setup_project.py の最後の「完了」の行が出ませんでした。Saved/Logs の .log を見てください")
    log(last[-1].strip())
    if "なし" not in last[-1]:
        log("注意: 2 回目でも作り直したものがあります (毎回作り直す設定が残っている)。動きはしますが Git に変更が出続けます")
    errors = [l for l in out.splitlines() if "Error" in l or "エラー" in l]
    if errors:
        log(f"注意: エラーらしい行が {len(errors)} 行あります:")
        for l in errors[:20]:
            print("    " + l.strip())


def stage_startup(course):
    import install_kit
    m = f"/Game/FukuokaDrive/Maps/{course.map}.{course.map}"
    install_kit.merge_ini(os.path.join(ROOT, "Config", "DefaultEngine.ini"), "/Script/EngineSettings.GameMapsSettings",
                          [("EditorStartupMap", m), ("GameDefaultMap", m)])
    log(f"起動時に開くレベル: {m}")


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        sys.exit(__doc__)
    name = args[0]
    area_path = os.path.join(TERRAIN, "areas", f"{name}.json")
    if not os.path.exists(area_path):
        fail(f"{os.path.relpath(area_path, ROOT)} がありません")
    max_tiles = int(args[args.index("--max-tiles") + 1]) if "--max-tiles" in args else 20
    redo = "--redo" in args
    data = "--ue" not in args
    ue = "--data" not in args
    started = time.time()

    set_course(name)
    course = Course(name)
    if data:
        stage_route(course, area_path, redo, max_tiles)
        stage_tiles(course, area_path, redo)
        course = Course(name)
        stage_overpass(course, area_path)
        stage_far_and_minimap(course, area_path, redo)
    if ue:
        if not course.tiles_doc():
            fail("tiles.json がありません。先にデータを作ってください (--data)")
        stage_ue(course)
        if "--no-startup" not in args:
            stage_startup(course)
    what = f"レベル /Game/FukuokaDrive/Maps/{course.map}" if ue else f"データ (tools/terrain/out/{name}/preview.png で道筋を確かめられます)"
    log(f"できました: {what} ({(time.time() - started) / 60:.0f} 分)")


if __name__ == "__main__":
    main()
