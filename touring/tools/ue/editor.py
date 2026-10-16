"""開いている Unreal Editor を外から操作する (PC の Python で実行。エディタの中ではない)。

エディタの Python の「リモート実行」(Config/DefaultEngine.ini で有効、127.0.0.1 のみ) を使う。

使い方 (py -3 tools/ue/editor.py ...):
    status          エディタが開いていて、命令を受け付けるか
    quit            プレイを止め、変更をすべて保存してからエディタを閉じる (閉じ終わるまで待つ)
    open            エディタを開き、命令を受け付けるようになるまで待つ
    run <script>    開いているエディタで Python スクリプトを実行する (例: tools/ue/setup_project.py)

終了コード: 0 成功 / 1 失敗 / 2 エディタが開いていない (status, quit, run)
"""

import glob
import os
import subprocess
import sys
import time

UE_ROOT = os.environ.get("UE_ROOT", r"C:\Program Files\Epic Games\UE_5.8")
PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "TouringSim.uproject"))
EDITOR_EXE = os.path.join(UE_ROOT, "Engine", "Binaries", "Win64", "UnrealEditor.exe")

QUIT_CODE = """
import unreal
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
try:
    if les.is_in_play_in_editor():
        les.editor_request_end_play()
except Exception:
    pass
ok = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
unreal.log(f"[editor.py] 保存: {ok}")
unreal.SystemLibrary.quit_editor()
"""


def log(msg):
    print(f"[editor] {msg}", flush=True)


def load_remote_execution():
    pattern = os.path.join(UE_ROOT, "Engine", "Plugins", "**", "PythonScriptPlugin", "Content", "Python", "remote_execution.py")
    found = glob.glob(pattern, recursive=True)
    if not found:
        sys.exit(f"[editor] remote_execution.py が見つかりません ({UE_ROOT})")
    sys.path.insert(0, os.path.dirname(found[0]))
    import remote_execution
    return remote_execution


def editor_running():
    """このプロジェクトを開いている UnrealEditor.exe があるか (別のプロジェクトのエディタは数えない)。"""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='UnrealEditor.exe'\" | "
          "ForEach-Object { $_.CommandLine }")
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        res = None
    if res is not None and res.returncode == 0:
        want = os.path.normcase(os.path.normpath(PROJECT))
        for line in res.stdout.splitlines():
            line = os.path.normcase(line.replace("/", "\\"))
            if want in line or os.path.normcase(os.path.basename(PROJECT)) in line:
                return True
        return False
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UnrealEditor.exe"], capture_output=True, text=True).stdout
    return "UnrealEditor.exe" in out


class Editor:
    def __init__(self):
        re = load_remote_execution()
        self.re = re
        cfg = re.RemoteExecutionConfig()
        cfg.multicast_bind_address = "127.0.0.1"
        self.rex = re.RemoteExecution(cfg)

    def __enter__(self):
        self.rex.start()
        return self

    def __exit__(self, *exc):
        self.rex.stop()

    def find_node(self, timeout):
        """このプロジェクトを開いているエディタを探す。"""
        end = time.time() + timeout
        want = os.path.normcase(os.path.dirname(PROJECT))
        while time.time() < end:
            for node in self.rex.remote_nodes:
                root = os.path.normcase(os.path.normpath(node.get("project_root", "")))
                if not root or root == want:
                    return node["node_id"]
            time.sleep(0.5)
        return None

    def run(self, node_id, code_or_file, raise_on_failure=True):
        self.rex.open_command_connection(node_id)
        res = self.rex.run_command(code_or_file, unattended=True, exec_mode=self.re.MODE_EXEC_FILE,
                                   raise_on_failure=False)
        for line in res.get("output", []):
            print(line.get("output", "").rstrip(), flush=True)
        if raise_on_failure and not res.get("success"):
            log(f"失敗: {res.get('result')}")
            return False
        return True


def cmd_status():
    if not editor_running():
        log("エディタは開いていません")
        return 2
    with Editor() as ed:
        node = ed.find_node(10)
    if node is None:
        log("エディタは開いていますが、命令を受け付けません (リモート実行が無効か、起動の途中)")
        return 1
    log("エディタは開いていて、命令を受け付けます")
    return 0


def cmd_quit():
    if not editor_running():
        log("エディタは開いていません")
        return 2
    with Editor() as ed:
        node = ed.find_node(15)
        if node is None:
            log("エディタに命令を送れません。手で保存して閉じてください")
            return 1
        log("保存して閉じます")
        try:
            ed.run(node, QUIT_CODE, raise_on_failure=False)
        except Exception:
            pass  # 閉じるときに接続が切れる
    for _ in range(240):
        if not editor_running():
            log("エディタを閉じました")
            return 0
        time.sleep(0.5)
    log("エディタが閉じません (保存の確認が出ているかもしれません)")
    return 1


def cmd_open():
    if not editor_running():
        log("エディタを開きます")
        subprocess.Popen([EDITOR_EXE, PROJECT], close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    with Editor() as ed:
        node = ed.find_node(600)
    if node is None:
        log("エディタが命令を受け付けるようになりません")
        return 1
    log("エディタが開きました")
    return 0


def cmd_run(script):
    if not editor_running():
        log("エディタは開いていません")
        return 2
    path = os.path.abspath(script)
    with Editor() as ed:
        node = ed.find_node(15)
        if node is None:
            log("エディタに命令を送れません")
            return 1
        log(f"実行: {path}")
        return 0 if ed.run(node, path) else 1


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "status":
        return cmd_status()
    if args[0] == "quit":
        return cmd_quit()
    if args[0] == "open":
        return cmd_open()
    if args[0] == "run" and len(args) == 2:
        return cmd_run(args[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
