"""The Unreal live bridge — day one, per docs/unreal-port.md.

Drives a RUNNING UnrealEditor via the engine's own Python remote-execution protocol
(multicast handshake, enabled in FerryUnreal/Config/DefaultEngine.ini). No cold restarts:
iteration is seconds, state reads are live, screenshots on demand.

Usage:
    python unreal/drive.py exec "unreal.log('hello from the bridge')"
    python unreal/drive.py eval "len(unreal.EditorLevelLibrary.get_all_level_actors())"
    python unreal/drive.py shot C:/Users/Alejandro/FerryUnreal/Shots/view.png
"""
import sys
import time
from pathlib import Path

ENGINE_PY = Path(r"C:\Program Files\Epic Games\UE_5.8\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python")
sys.path.insert(0, str(ENGINE_PY))

import remote_execution as re  # the engine's reference client


def connect(timeout=10.0):
    rex = re.RemoteExecution()
    rex.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        nodes = rex.remote_nodes
        if nodes:
            rex.open_command_connection(nodes[0]["node_id"])
            return rex
        time.sleep(0.25)
    rex.stop()
    raise SystemExit("no running UnrealEditor answered the multicast handshake "
                     "(is the editor open with remote execution enabled?)")


def run(code, exec_mode="ExecuteStatement"):
    rex = connect()
    try:
        result = rex.run_command(code, exec_mode=exec_mode)
        if not result["success"]:
            print("FAILED:", result.get("result"))
            return 1
        out = result.get("output") or []
        for line in out:
            print(f"[{line['type']}] {line['output']}")
        if result.get("result") not in (None, "None"):
            print(result["result"])
        return 0
    finally:
        rex.stop()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ping"
    if cmd == "ping":
        sys.exit(run("import unreal; unreal.log('bridge pong')"))
    elif cmd == "exec":
        sys.exit(run(sys.argv[2]))
    elif cmd == "eval":
        sys.exit(run(sys.argv[2], exec_mode="EvaluateStatement"))
    elif cmd == "shot":
        path = sys.argv[2].replace("\\", "/")
        sys.exit(run(
            "import unreal; unreal.AutomationLibrary.take_high_res_screenshot("
            f"1280, 720, r'{path}')"))
    else:
        sys.exit(f"unknown command {cmd}")
