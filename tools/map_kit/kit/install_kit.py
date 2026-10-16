"""このリポジトリの「地域のジオラマを作る仕組み」一式を、別の UE5 プロジェクトへ入れる (または新しく作る)。

入れるもの:
    Source/FukuokaDrive/       C++ モジュール (バイク・歩行・時刻・夜の光・景観の並べ方・ミニマップ・海の登録し直し・ランドスケープの取り込み)
                               モジュール名は FukuokaDrive のまま入れる (setup_project.py が /Script/FukuokaDrive.* を読むため)
    tools/terrain, ue, vehicle データ作り (国土地理院・OSM) と UE の組み立て (setup_project.py, editor.py, rebuild.bat)
    Config の必要な設定       Python のリモート実行、Lumen、露出、テクスチャプール、再インポート確認を出さない、GameMode
    .uproject                  モジュールとプラグイン (Water, SunPosition, PythonScriptPlugin, EditorScriptingUtilities, EnhancedInput)
    .gitattributes/.gitignore  LFS と生成物の除外

Content は入れない (setup_project.py がすべて作る)。

使い方 (標準ライブラリだけ、Python 3.8 以上):
    py -3 tools/kit/install_kit.py <プロジェクトのフォルダか .uproject>
    py -3 tools/kit/install_kit.py <新しいフォルダ> --create MyDiorama   .uproject から新しく作る

ツーリングシミュレータ (走りのコア 1 つに、地域のマップを足していく形):
    py -3 tools/kit/install_kit.py touring --create TouringSim --regions ../maps
        コアを作る。--regions のフォルダ (.uproject からの相対) の下の地域を読み込み、起動すると地域を選ぶ画面が出る
    py -3 tools/kit/install_kit.py touring --add-region ../maps/sikanosima --title 志賀島
        コアに地域を足す: <地域>/<レベル名>.uplugin (コンテンツプラグイン)、Content/、areas/ を作り、
        course.txt をこの地域にする。コースの設定は <地域>/areas/<地域>.json (tools/kit/area_picker.py が書く)。
        レベル名 (= プラグイン名) は既定でフォルダ名の頭を大文字にしたもの (--map で変えられる)
    オプション:
        --no-mcp    UE 付属の MCP サーバー (ModelContextProtocol, AllToolsets) を入れない (既定では有効にし、エディタを開くと自動で起動する)
        --startup-map <レベル名>   起動時に開くレベルを /Game/FukuokaDrive/Maps/<レベル名> にする (コースを作った後に使う)
        --regions <フォルダ>       ツーリングシミュレータのコアにする (地域を並べるフォルダ。何度でも足せる)
        --dry-run   何を変えるかだけ表示する

何度実行してもよい (同じ結果になる)。既存の設定は残し、足りないキーだけ足す (キーが同じで値が違うものは上書きする)。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# キットの置き場所は 2 通り: キットだけのフォルダ (diorama_project の tools/map_kit。kit/ terrain/ ue/ vehicle/ Source/ が並ぶ) か、
# fukuoka_drive のようなプロジェクト (tools/ の下にスクリプト、Source/ はプロジェクトの直下)
KIT_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KIT_ROOT = KIT_TOOLS if os.path.isdir(os.path.join(KIT_TOOLS, "Source")) else os.path.dirname(KIT_TOOLS)
ENGINE_VERSION = "5.8"
MODULE = "FukuokaDrive"

PLUGINS = ["Water", "SunPosition", "PythonScriptPlugin", "EditorScriptingUtilities", "EnhancedInput"]
MCP_PLUGINS = ["ModelContextProtocol", "AllToolsets"]

# (ファイル, セクション, [(キー, 値)])。キーが "+" で始まるものは「無ければ足す」行
INI = [
    ("DefaultEngine.ini", "/Script/EngineSettings.GameMapsSettings", [
        ("GlobalDefaultGameMode", f"/Script/{MODULE}.FDGameMode")]),
    ("DefaultEngine.ini", "/Script/Engine.RendererSettings", [
        ("r.DynamicGlobalIlluminationMethod", "1"), ("r.ReflectionMethod", "1"), ("r.Shadow.Virtual.Enable", "1"),
        ("r.GenerateMeshDistanceFields", "True"), ("r.AllowStaticLighting", "False"),
        ("r.Nanite.ProjectEnabled", "True"), ("r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange", "True")]),
    ("DefaultEngine.ini", "/Script/WindowsTargetPlatform.WindowsTargetSettings", [
        ("DefaultGraphicsRHI", "DefaultGraphicsRHI_DX12"), ("+D3D12TargetedShaderFormats", "PCD3D_SM6")]),
    ("DefaultEngine.ini", "/Script/PythonScriptPlugin.PythonScriptPluginSettings", [
        ("bRemoteExecution", "True"), ("RemoteExecutionMulticastBindAddress", "127.0.0.1")]),
    ("DefaultEngine.ini", "ConsoleVariables", [
        ("r.EyeAdaptation.CachedLightingPreExposure", "8")]),
    ("DefaultEngine.ini", "SystemSettings", [
        ("r.Streaming.PoolSize", "4000")]),
    ("DefaultInput.ini", "/Script/Engine.InputSettings", [
        ("DefaultPlayerInputClass", "/Script/EnhancedInput.EnhancedPlayerInput"),
        ("DefaultInputComponentClass", "/Script/EnhancedInput.EnhancedInputComponent")]),
    ("DefaultEditorPerProjectUserSettings.ini", "/Script/UnrealEd.EditorLoadingSavingSettings", [
        ("bMonitorContentDirectories", "False")]),
]
MCP_INI = [
    ("DefaultEditorPerProjectUserSettings.ini", "/Script/ModelContextProtocolEngine.ModelContextProtocolSettings", [
        ("bAutoStartServer", "True")]),
    ("DefaultGame.ini", "/Script/Engine.AssetManagerSettings", [
        ("+PrimaryAssetTypesToScan", '(PrimaryAssetType="GameFeatureData",AssetBaseClass="/Script/GameFeatures.GameFeatureData",'
         'bHasBlueprintClasses=False,bIsEditorOnly=False,Directories=((Path="/Game/Unused")),SpecificAssets=,'
         'Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=AlwaysCook))')]),
]

GITATTRIBUTES = """# UE のバイナリアセットは Git LFS で管理する
*.uasset filter=lfs diff=lfs merge=lfs -text
*.umap filter=lfs diff=lfs merge=lfs -text
*.ubulk filter=lfs diff=lfs merge=lfs -text
*.uexp filter=lfs diff=lfs merge=lfs -text
*.r16 filter=lfs diff=lfs merge=lfs -text
Content/**/*.png filter=lfs diff=lfs merge=lfs -text
*.py text eol=lf
*.json text eol=lf
*.md text eol=lf
"""
GITIGNORE = """Binaries/
DerivedDataCache/
Intermediate/
Saved/
.vs/
*.sln
tools/terrain/out/
tools/vehicle/out/
__pycache__/
*.pyc
"""

TARGET_CS = """using UnrealBuildTool;

public class {cls} : TargetRules
{{
	public {cls}(TargetInfo Target) : base(Target)
	{{
		Type = TargetType.{kind};
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("{module}");
	}}
}}
"""

changes = []
DRY = False


def note(msg):
    changes.append(msg)
    print(f"[kit] {msg}", flush=True)


# --- ファイルの読み書き (.uproject は UTF-16 のことがある) ---
def read_text(path):
    raw = open(path, "rb").read()
    for bom, enc in ((b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"), (b"\xef\xbb\xbf", "utf-8-sig")):
        if raw.startswith(bom):
            return raw.decode(enc), enc
    return raw.decode("utf-8"), "utf-8"


def write_text(path, text, enc="utf-8"):
    if DRY:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nl = "\r\n" if path.endswith((".ini", ".bat", ".uproject", ".cs")) else "\n"
    with open(path, "w", encoding=enc, newline=nl) as f:
        f.write(text)


# --- .uproject ---
def find_uproject(target):
    if target.endswith(".uproject"):
        return os.path.abspath(target)
    found = [f for f in os.listdir(target) if f.endswith(".uproject")] if os.path.isdir(target) else []
    if len(found) != 1:
        sys.exit(f"[kit] {target} に .uproject が {len(found)} 個あります。.uproject を直接指定するか --create を使ってください")
    return os.path.join(os.path.abspath(target), found[0])


def create_uproject(folder, name):
    path = os.path.join(os.path.abspath(folder), f"{name}.uproject")
    if os.path.exists(path):
        return path
    doc = {"FileVersion": 3, "EngineAssociation": engine_version(), "Category": "",
           "Description": "国土地理院と OSM から作る地域のジオラマ", "Modules": [], "Plugins": []}
    note(f"新しいプロジェクト {path} を作る")
    write_text(path, json.dumps(doc, ensure_ascii=False, indent="\t") + "\n")
    return path


def engine_version():
    path = os.path.join(KIT_ROOT, f"{MODULE}.uproject")
    if not os.path.exists(path):
        return ENGINE_VERSION
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("EngineAssociation", ENGINE_VERSION)


def patch_uproject(path, mcp, regions=()):
    text, enc = read_text(path)
    doc = json.loads(text)
    if regions:
        dirs = doc.setdefault("AdditionalPluginDirectories", [])
        for d in regions:
            d = d.replace("\\", "/")
            if d not in dirs:
                dirs.append(d)
                note(f".uproject の AdditionalPluginDirectories に {d} を足す (地域のフォルダを読み込む)")
    mods = doc.setdefault("Modules", [])
    if not any(m.get("Name") == MODULE for m in mods):
        mods.append({"Name": MODULE, "Type": "Runtime", "LoadingPhase": "Default",
                     "AdditionalDependencies": ["Engine", "EnhancedInput"]})
        note(f".uproject にモジュール {MODULE} を足す")
    plugins = doc.setdefault("Plugins", [])
    for name in PLUGINS + (MCP_PLUGINS if mcp else []):
        p = next((p for p in plugins if p.get("Name") == name), None)
        if p is None:
            plugins.append({"Name": name, "Enabled": True})
            note(f".uproject でプラグイン {name} を有効にする")
        elif not p.get("Enabled"):
            p["Enabled"] = True
            note(f".uproject でプラグイン {name} を有効にする (無効だった)")
    new = json.dumps(doc, ensure_ascii=False, indent="\t") + "\n"
    if json.loads(text) != doc:
        write_text(path, new, enc if enc != "utf-8-sig" else "utf-8-sig")


# --- Source ---
def install_source(project_dir, name):
    src = os.path.join(KIT_ROOT, "Source", MODULE)
    dst = os.path.join(project_dir, "Source", MODULE)
    sync_tree(src, dst)
    for kind, cls in (("Game", f"{name}Target"), ("Editor", f"{name}EditorTarget")):
        path = os.path.join(project_dir, "Source", f"{cls[:-len('Target')]}.Target.cs")
        if not os.path.exists(path):
            note(f"{os.path.relpath(path, project_dir)} を作る")
            write_text(path, TARGET_CS.format(cls=cls, kind=kind, module=MODULE))
            continue
        text, enc = read_text(path)
        if f'"{MODULE}"' in text:
            continue
        m = re.search(r"ExtraModuleNames\.(Add|AddRange)\(", text)
        if m:
            line_start = text.rfind("\n", 0, m.start()) + 1
            indent = text[line_start:m.start()]
            text = text[:line_start] + f'{indent}ExtraModuleNames.Add("{MODULE}");\n' + text[line_start:]
        else:
            text = re.sub(r"(base\(Target\)\s*\{)", r'\1\n\t\tExtraModuleNames.Add("%s");' % MODULE, text, count=1)
        note(f"{os.path.relpath(path, project_dir)} に ExtraModuleNames.Add(\"{MODULE}\") を足す")
        write_text(path, text, enc)


# --- tools ---
SKIP_DIRS = {"out", "__pycache__", "_cache"}


def sync_tree(src, dst, transform=None, skip=None):
    """src を dst へ写す。中身が同じファイルは触らない。transform(相対パス, 中身) で写す中身を変えられる。
    skip(相対パス) が真のファイルは写さない。"""
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".pyc"):
                continue
            s = os.path.join(root, f)
            rel = os.path.relpath(s, src)
            if skip and skip(rel.replace(os.sep, "/")):
                continue
            d = os.path.join(dst, rel)
            data = open(s, "rb").read()
            if transform:
                data = transform(rel.replace(os.sep, "/"), data)
            if os.path.exists(d) and open(d, "rb").read() == data:
                continue
            n += 1
            if not DRY:
                os.makedirs(os.path.dirname(d), exist_ok=True)
                with open(d, "wb") as out:
                    out.write(data)
    if n:
        note(f"{os.path.relpath(src, KIT_ROOT)} から {n} 個のファイルを写す")


def install_tools(project_dir, name):
    # build.bat / editor.py はプロジェクト名を決め打ちしているので、入れた先の名前にして写す
    def rename(rel, data):
        if name == MODULE or rel not in ("build.bat", "editor.py", "setup_project.py"):
            return data
        return (data.replace(f"{MODULE}Editor Win64".encode(), f"{name}Editor Win64".encode())
                    .replace(f"{MODULE}.uproject".encode(), f"{name}.uproject".encode()))
    # コースの設定 (areas/) と、いま作るコース (course.txt) はこのリポジトリ (糸島・阿蘇) のものなので写さない。
    # 入れた先のコースを入れ直しで上書きしないためでもある
    def own_course(rel):
        return rel == "course.txt" or rel.startswith("areas/")
    for sub in ("terrain", "ue", "vehicle", "kit"):
        sync_tree(os.path.join(KIT_TOOLS, sub), os.path.join(project_dir, "tools", sub),
                  rename if sub == "ue" else None, own_course if sub == "terrain" else None)
    if not DRY:
        os.makedirs(os.path.join(project_dir, "tools", "terrain", "areas"), exist_ok=True)


# --- Config (.ini) ---
def merge_ini(path, section, pairs):
    text, enc = read_text(path) if os.path.exists(path) else ("", "utf-8")
    lines = text.splitlines()
    head = f"[{section}]"
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == head)
    except StopIteration:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [head] + [f"{k}={v}" for k, v in pairs] + [""]
        note(f"{os.path.basename(path)} に [{section}] を足す")
        write_text(path, "\n".join(lines) + "\n", enc)
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    body = lines[start + 1:end]
    while body and not body[-1].strip():
        body.pop()
    changed = False
    for k, v in pairs:
        want = f"{k}={v}"
        if k.startswith("+"):
            if want not in (l.strip() for l in body):
                body.append(want)
                changed = True
            continue
        idx = next((i for i, l in enumerate(body) if l.split("=", 1)[0].strip() == k), None)
        if idx is None:
            body.append(want)
            changed = True
        elif body[idx].strip() != want:
            body[idx] = want
            changed = True
    if changed:
        lines[start + 1:end] = body + ([""] if end < len(lines) else [])
        note(f"{os.path.basename(path)} の [{section}] を直す")
        write_text(path, "\n".join(lines) + "\n", enc)


def install_config(project_dir, mcp):
    for fname, section, pairs in INI + (MCP_INI if mcp else []):
        merge_ini(os.path.join(project_dir, "Config", fname), section, pairs)


def merge_lines(path, block):
    have = set(open(path, encoding="utf-8").read().splitlines()) if os.path.exists(path) else set()
    add = [l for l in block.splitlines() if l and not l.startswith("#") and l not in have]
    if add:
        note(f"{os.path.basename(path)} に {len(add)} 行足す")
        if not DRY:
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(("\n" if have else "") + "\n".join(add) + "\n")


# --- ツーリングシミュレータの地域 ---
START_MAP = "/Game/FukuokaDrive/Maps/Start.Start"   # 地域を選ぶ起動画面 (setup_project.py が作る)
REGION_CATEGORY = "Touring Region"                 # C++ の FFDRegions はこの Category のプラグインを地域とみなす
REGION_GITATTRIBUTES = """# 地域のアセットは Git LFS で管理する
Content/**/*.png filter=lfs diff=lfs merge=lfs -text
*.json text eol=lf
"""


def default_map_name(folder_name):
    return "".join(w.capitalize() for w in folder_name.split("_"))


def add_region(project_dir, folder, plugin=None, title=None):
    """コアに地域のフォルダ (UE のコンテンツプラグイン) を足す。何度実行してもよい。地域のフォルダを返す。"""
    folder = os.path.abspath(folder)
    name = os.path.basename(folder)
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", name):
        sys.exit(f"[kit] 地域のフォルダ名 {name} は英小文字で始まる英小文字・数字・_ にしてください (コース名になる)")
    plugin = plugin or default_map_name(name)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", plugin):
        sys.exit(f"[kit] レベル名 {plugin} は英字で始まる英数字と _ にしてください")
    uproject = find_uproject(project_dir)
    doc = json.loads(read_text(uproject)[0])
    roots = [os.path.normcase(os.path.normpath(os.path.join(project_dir, d))) for d in doc.get("AdditionalPluginDirectories", [])]
    if os.path.normcase(os.path.dirname(folder)) not in roots:
        sys.exit(f"[kit] {folder} はコアの地域のフォルダ ({', '.join(roots) or 'まだ無い'}) の下にありません。"
                 "コアを --regions 付きで入れ直すか、そこへ置いてください")
    if os.path.isdir(folder):
        if any(f.endswith(".uproject") for f in os.listdir(folder)):
            sys.exit(f"[kit] {folder} に地域ごとの UE プロジェクト (.uproject) が残っています。"
                     "コアの地域にする前に古いプロジェクトのファイルを片付けてください (Content もプラグインの中身として読まれるため)")
        others = [f for f in os.listdir(folder) if f.endswith(".uplugin") and f != f"{plugin}.uplugin"]
        if others:
            sys.exit(f"[kit] {folder} には別の名前のプラグイン {others} があります")
    path = os.path.join(folder, f"{plugin}.uplugin")
    want = {"FileVersion": 3, "Version": 1, "VersionName": "1.0", "FriendlyName": title or name,
            "Description": "ツーリングシミュレータの地域 (国土地理院と OSM から作るマップ)", "Category": REGION_CATEGORY,
            "CanContainContent": True, "EnabledByDefault": True, "ExplicitlyLoaded": False}
    if os.path.exists(path):
        have = json.loads(read_text(path)[0])
        if title is None:
            want["FriendlyName"] = have.get("FriendlyName", want["FriendlyName"])
        merged = {**have, **want}
        if merged != have:
            note(f"{os.path.relpath(path, project_dir)} を直す")
            write_text(path, json.dumps(merged, ensure_ascii=False, indent="\t") + "\n")
    else:
        note(f"地域 {name} ({want['FriendlyName']}) のプラグイン {os.path.relpath(path, project_dir)} を作る")
        write_text(path, json.dumps(want, ensure_ascii=False, indent="\t") + "\n")
    if not DRY:
        for sub in ("Content", "areas"):
            os.makedirs(os.path.join(folder, sub), exist_ok=True)
    merge_lines(os.path.join(folder, ".gitattributes"), REGION_GITATTRIBUTES)
    # いま作るコースをこの地域にする (setup_project.py と rebuild.bat が読む)
    course_txt = os.path.join(project_dir, "tools", "terrain", "course.txt")
    text = f"# 作るコースの名前 (tools/terrain/areas/ か地域のフォルダの areas/ の <名前>.json)。setup_project.py と rebuild.bat がこれを読む\n{name}\n"
    if not os.path.exists(course_txt) or open(course_txt, encoding="utf-8").read() != text:
        note(f"course.txt を {name} にする")
        write_text(course_txt, text)
    return folder


def kit_commit():
    try:
        return subprocess.run(["git", "-C", KIT_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def main():
    global DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--create", metavar="NAME")
    ap.add_argument("--no-mcp", dest="mcp", action="store_false")
    ap.add_argument("--startup-map", metavar="MAP")
    ap.add_argument("--regions", action="append", default=[], metavar="DIR")
    ap.add_argument("--add-region", metavar="DIR")
    ap.add_argument("--map", metavar="NAME")
    ap.add_argument("--title")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    DRY = a.dry_run
    if not os.path.exists(os.path.join(KIT_TOOLS, "terrain", "course.py")):
        sys.exit("[kit] この仕組みのリポジトリに tools/terrain/course.py がありません (コース非依存の仕組みの入った版を使ってください)")
    if a.create:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,19}", a.create):
            sys.exit("[kit] プロジェクト名は英字で始まる英数字 20 文字以内にしてください")
        os.makedirs(a.target, exist_ok=True)
        uproject = create_uproject(a.target, a.create)
    else:
        uproject = find_uproject(a.target)
    project_dir = os.path.dirname(uproject)
    if a.add_region:
        # 地域を足すだけなら、コアに入れたキット (tools/kit) からも実行できる
        folder = a.add_region if os.path.isabs(a.add_region) else os.path.join(project_dir, a.add_region)
        add_region(project_dir, folder, a.map, a.title)
        print(f"[kit] 完了: 地域 {os.path.abspath(folder)} (変更 {len(changes)} 件{'、dry-run なので書いていません' if DRY else ''})")
        return
    if os.path.normcase(project_dir) == os.path.normcase(KIT_ROOT):
        sys.exit("[kit] 入れる先がこのリポジトリ自身です")
    name = os.path.splitext(os.path.basename(uproject))[0]
    if DRY and not os.path.exists(uproject):
        sys.exit(f"[kit] (dry-run) {uproject} はまだありません")

    patch_uproject(uproject, a.mcp, a.regions)
    install_source(project_dir, name)
    install_tools(project_dir, name)
    install_config(project_dir, a.mcp)
    if a.regions:
        # ツーリングシミュレータは地域を選ぶ画面から始まる
        merge_ini(os.path.join(project_dir, "Config", "DefaultEngine.ini"), "/Script/EngineSettings.GameMapsSettings",
                  [("EditorStartupMap", START_MAP), ("GameDefaultMap", START_MAP)])
    elif a.startup_map:
        m = f"/Game/FukuokaDrive/Maps/{a.startup_map}.{a.startup_map}"
        merge_ini(os.path.join(project_dir, "Config", "DefaultEngine.ini"), "/Script/EngineSettings.GameMapsSettings",
                  [("EditorStartupMap", m), ("GameDefaultMap", m)])
    if a.mcp:
        # Claude Code が UE の MCP サーバーへつなぐ設定 (エディタのコンソールの ModelContextProtocol.GenerateClientConfig claude と同じ中身)
        mcp_json = os.path.join(project_dir, ".mcp.json")
        if not os.path.exists(mcp_json):
            note(".mcp.json を作る (unreal-mcp: http://127.0.0.1:8000/mcp)")
            write_text(mcp_json, json.dumps({"mcpServers": {"unreal-mcp": {"type": "http", "url": "http://127.0.0.1:8000/mcp"}}},
                                            indent=2) + "\n")
    merge_lines(os.path.join(project_dir, ".gitattributes"), GITATTRIBUTES)
    merge_lines(os.path.join(project_dir, ".gitignore"), GITIGNORE)
    if not DRY:
        os.makedirs(os.path.join(project_dir, "Content"), exist_ok=True)
        with open(os.path.join(project_dir, "tools", "kit", "installed.json"), "w", encoding="utf-8") as f:
            json.dump({"from": KIT_ROOT, "commit": kit_commit(), "project": name, "mcp": a.mcp}, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"[kit] 完了: {uproject} (変更 {len(changes)} 件{'、dry-run なので書いていません' if DRY else ''})")


if __name__ == "__main__":
    main()
