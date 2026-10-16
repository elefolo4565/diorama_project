"""地図の上で、ジオラマにする範囲を多角形で描いてコースの設定に書き出す画面 (ブラウザで開く)。

使い方 (PC で):
    py -3 tools/kit/area_picker.py            ブラウザで http://127.0.0.1:8765/ を開く
    py -3 tools/kit/area_picker.py --once     書き出したら終わる (Claude がスキルから使う時。最後の行に保存先を出す)
    オプション: --port N

画面でやること:
    1. 地名を入れて「検索」→ その周りの地図が出る (地理院地図。写真・OSM にも切り替えられる)
    2. 「範囲を描く」→ 地図をクリックして多角形の頂点を置く。頂点はドラッグで動かせる。ダブルクリックか「描き終わる」で閉じる
       作られる 4km 四方のタイルが重ねて表示される (20 枚まで)
    3. 必要なら「行き先を置く」でファストトラベルの行き先をクリックで足す (無ければ真ん中に近い道路が 1 か所)。
       「エリア内の名所」に印を付けると、範囲の中の名所 (展望所・灯台・滝・浜・神社・寺など、OSM) を探して行き先にできる
    4. コース名を入れて「書き出す」→ tools/terrain/areas/<コース名>.json ができる
    5. py -3 tools/kit/make_diorama.py <コース名> で世界を作る

地名検索は OSM の Nominatim をこのサーバー経由で使う (結果は tools/terrain/out/_cache にキャッシュ)。
"""

import hashlib
import http.server
import json
import os
import re
import socket
import sys
import threading
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TERRAIN = os.path.join(ROOT, "tools", "terrain")
AREAS = os.path.join(TERRAIN, "areas")
sys.path.insert(0, TERRAIN)

from geo import TOOLS_DIR, http_get, http_post_form  # noqa: E402

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# エリア内の名所として探すもの ({タグ: 値 (None なら何でも)}, 画面に出す種類, 優先度: 小さいほど先)
LANDMARK_TAGS = [
    ({"tourism": "viewpoint"}, "展望所", 0),
    ({"man_made": "lighthouse"}, "灯台", 0),
    ({"natural": "waterfall"}, "滝", 1),
    ({"waterway": "waterfall"}, "滝", 1),
    ({"natural": "beach"}, "浜", 1),
    ({"tourism": "attraction"}, "名所", 2),
    ({"amenity": "place_of_worship", "religion": "shinto"}, "神社", 3),
    ({"amenity": "place_of_worship", "religion": "buddhist"}, "寺", 3),
    ({"historic": None}, "史跡", 3),
    ({"tourism": "museum"}, "博物館", 4),
    ({"natural": "peak"}, "山", 4),
]


def tag_filter(want):
    return "".join(f'["{k}"]' if v is None else f'["{k}"="{v}"]' for k, v in want.items())


def matches(tags, want):
    return all(k in tags if v is None else tags.get(k) == v for k, v in want.items())


NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
MAP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")
MAX_TILES = 20


def search(q):
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 6, "countrycodes": "jp", "accept-language": "ja"})
    cache = os.path.join(TOOLS_DIR, "out", "_cache", "nominatim_ui", hashlib.md5(q.encode("utf-8")).hexdigest() + ".json")
    res = json.loads(http_get(url, cache, retries=1) or b"[]")
    return [{"name": r.get("display_name", ""), "lat": float(r["lat"]), "lon": float(r["lon"]),
             "bbox": [float(v) for v in r.get("boundingbox", [])]} for r in res]


def inside(poly, lat, lon):
    hit = False
    for (y0, x0), (y1, x1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def landmarks(poly):
    """多角形の中の、名前のある名所 (OSM)。有名なもの (Wikipedia の記事があるもの) と優先度の高い種類から並べる。"""
    lats, lons = [p[0] for p in poly], [p[1] for p in poly]
    b = f"{min(lats):.5f},{min(lons):.5f},{max(lats):.5f},{max(lons):.5f}"
    body = "".join(f'nwr{tag_filter(t)}["name"]({b});' for t, _, _ in LANDMARK_TAGS)
    query = f"[out:json][timeout:90];({body});out center tags;"
    cache = os.path.join(TOOLS_DIR, "out", "_cache", "landmarks", hashlib.md5(query.encode("utf-8")).hexdigest() + ".json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(http_post_form(OVERPASS_URL, {"data": query}, retries=1))
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    out, seen = [], set()
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:ja") or tags.get("name")
        c = el.get("center") or el
        if not name or "lat" not in c or name in seen or not inside(poly, c["lat"], c["lon"]):
            continue
        kind, prio = next(((k, p) for t, k, p in LANDMARK_TAGS if matches(tags, t)), ("名所", 5))
        famous = "wikipedia" in tags or "wikidata" in tags
        seen.add(name)
        out.append({"name": name, "kind": kind, "lat": round(c["lat"], 6), "lon": round(c["lon"], 6),
                    "famous": famous, "rank": prio - (3 if famous else 0)})
    out.sort(key=lambda r: (r["rank"], r["name"]))
    return out[:40]


def course_json(req):
    """画面から来た内容を、コースの設定 (areas/<名前>.json) の形にする。"""
    name = str(req.get("name", "")).strip()
    if not NAME_RE.match(name):
        raise ValueError("コース名は英小文字で始まり、英小文字・数字・_ だけで 2〜41 文字にしてください")
    mp = str(req.get("map") or "").strip() or "".join(w.capitalize() for w in name.split("_"))
    if not MAP_RE.match(mp):
        raise ValueError("レベル名は英字で始まり、英数字と _ だけにしてください")
    poly = [[round(float(a), 6), round(float(b), 6)] for a, b in req.get("polygon", [])]
    if len(poly) < 3:
        raise ValueError("範囲の多角形の頂点が 3 つ未満です")
    if not all(20 <= a <= 46 and 122 <= b <= 154 for a, b in poly):
        raise ValueError("範囲が日本の外にあります (国土地理院のデータは日本だけ)")
    tiles = int(req.get("tiles", 0))
    if tiles > MAX_TILES:
        raise ValueError(f"タイルが {tiles} 枚あります。{MAX_TILES} 枚以内に狭めてください")
    feats = req.get("features", {})
    cfg = {
        "name": name,
        "description": str(req.get("description") or "").strip() or f"{name} (地図で範囲を指定)",
        "map": mp,
        "center_lat": round(float(req["center"][0]), 4),
        "center_lon": round(float(req["center"][1]), 4),
        "tile_size_px": 4033,
        "meters_per_px": 1.0,
        "loop": False,
        # 道路・区画線・側溝・標識と神社・線路と駅は入れる。電柱と街灯・ガードレールは画面のチェックで選ぶ
        "features": {"landmarks": bool(feats.get("landmarks", False)), "road_markings": True,
                     "utility_poles": bool(feats.get("utility_poles", False)),
                     "guardrails": bool(feats.get("guardrails", False)),
                     "city_glow": bool(feats.get("city_glow", False)),
                     "shrines": bool(feats.get("shrines", True)),
                     "railways": bool(feats.get("railways", True))},
        "polygon": poly,
    }
    rot = int(req.get("rotation_deg") or 0)
    if not 0 <= rot < 90:
        raise ValueError("タイルの回転は 0〜89 度にしてください")
    if rot:
        cfg["rotation_deg"] = rot
    if req.get("sea") == "none":
        cfg["sea"] = "none"
    wps = [{"name": str(w["name"]).strip(), "lat": round(float(w["lat"]), 6), "lon": round(float(w["lon"]), 6)}
           for w in req.get("waypoints", []) if str(w.get("name", "")).strip()]
    if wps:
        cfg["waypoints"] = wps
    return cfg


def forget_old_data(path, cfg):
    """上書きで範囲が変わったら、前の範囲で作ったデータを消す (原点が変わるとタイルの位置が全部ずれるため)。
    原点が同じでも道筋とタイルの選び方は作り直す。"""
    import glob
    import shutil
    from course import Course
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    old_course = Course(path)
    same_origin = (old.get("center_lat"), old.get("center_lon")) == (cfg["center_lat"], cfg["center_lon"])
    out = os.path.join(TERRAIN, "out")
    doomed = [os.path.join(out, old["name"])]
    if not same_origin:
        doomed += glob.glob(os.path.join(out, f"{old_course.tile_prefix}_*")) + [old_course.tile_dir]
    for d in doomed:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            print(f"前の範囲のデータを消しました: {os.path.relpath(d, ROOT)}", flush=True)


def areas_dir_for(cfg, create):
    """コースの設定を書くフォルダ。ツーリングシミュレータのコアなら地域のフォルダ (<地域>/areas/、無ければ作る)"""
    import course
    if not course.region_dirs():
        return AREAS
    folder = course.region_folders().get(cfg["name"]) or os.path.join(course.region_dirs()[0], cfg["name"])
    if create:
        import install_kit
        desc = cfg.get("description", "")
        title = None if desc.endswith("(地図で範囲を指定)") else desc
        install_kit.add_region(ROOT, folder, cfg["map"], title)
    return os.path.join(folder, "areas")


def save(req):
    cfg = course_json(req)
    areas = areas_dir_for(cfg, create=False)
    path = os.path.join(areas, f"{cfg['name']}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if not json.load(f).get("polygon"):
                raise ValueError(f"{cfg['name']} は道筋で作ったコースなので上書きしません。別のコース名にしてください")
    if os.path.exists(path) and not req.get("overwrite"):
        return {"ok": False, "exists": True, "error": f"{os.path.relpath(path, ROOT)} がもうあります。上書きしますか"}
    if os.path.exists(path):
        forget_old_data(path, cfg)
    areas = areas_dir_for(cfg, create=True)
    os.makedirs(areas, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"ok": True, "path": os.path.relpath(path, ROOT).replace("\\", "/"), "name": cfg["name"],
            "command": f"py -3 tools\\kit\\make_diorama.py {cfg['name']}"}


def existing():
    import course
    out = []
    files = [os.path.join(AREAS, fn) for fn in sorted(os.listdir(AREAS))] if os.path.isdir(AREAS) else []
    for name, folder in course.region_folders().items():
        files.append(os.path.join(folder, "areas", f"{name}.json"))
    for path in files:
        if not path.endswith(".json") or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
        except (OSError, ValueError):
            continue
        if c.get("polygon"):
            out.append({k: c.get(k) for k in ("name", "map", "description", "polygon", "waypoints", "features", "sea")})
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    once = False
    saved = None

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "area_picker.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/search":
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0].strip()
            try:
                return self.send(200, {"results": search(q) if q else []})
            except Exception as e:  # noqa: BLE001 ネットワークの失敗は画面に出す
                return self.send(502, {"error": f"地名検索に失敗しました: {e}"})
        if u.path == "/api/courses":
            return self.send(200, {"courses": existing()})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/landmarks":
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                poly = [[float(a), float(b)] for a, b in req.get("polygon", [])]
                return self.send(200, {"landmarks": landmarks(poly) if len(poly) >= 3 else []})
            except Exception as e:  # noqa: BLE001 Overpass の混雑などは画面に出す
                return self.send(502, {"error": f"名所を探せませんでした (Overpass が混んでいる時はしばらく待って再試行): {e}"})
        if self.path != "/api/save":
            return self.send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            res = save(req)
        except (ValueError, KeyError, TypeError) as e:
            return self.send(400, {"ok": False, "error": str(e)})
        self.send(200, res)
        if res.get("ok"):
            print(f"書き出しました: {res['path']}\n次: {res['command']}", flush=True)
            if Handler.once:
                Handler.saved = res
                threading.Thread(target=self.server.shutdown, daemon=True).start()


class Server(http.server.ThreadingHTTPServer):
    # 既定の SO_REUSEADDR だと、Windows では別の画面がもう使っているポートでも黙って開けてしまい、
    # 書き出しをどちらが受けるか分からなくなる。使用中なら次のポートにする
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def open_server(port, tries=20):
    for p in range(port, port + tries):
        try:
            return Server(("127.0.0.1", p), Handler), p
        except OSError:
            print(f"ポート {p} は使用中 (別の範囲選択の画面が開いているかもしれません)。次を試します", flush=True)
    sys.exit(f"ポート {port}〜{port + tries - 1} がすべて使用中です")


def main():
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8765
    Handler.once = "--once" in args
    srv, port = open_server(port)
    url = f"http://127.0.0.1:{port}/"
    print(f"範囲を選ぶ画面: {url} (終わるには Ctrl+C)", flush=True)
    if "--no-browser" not in args:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    if Handler.saved:
        print(f"SAVED {Handler.saved['name']}", flush=True)


if __name__ == "__main__":
    main()
