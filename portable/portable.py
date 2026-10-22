"""Offline Windows bundle preparation, diagnostics and owned service launch.

This file is shipped as portable/portable.py. It never installs dependencies.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import site
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOS = ("Haike_video", "copy_skill/copy_skill-main", "creatorhub")
BROWSER = "Haike_video/remotion-composer/node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8-sig") == text:
        return
    fd, temporary = tempfile.mkstemp(prefix=".portable-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return fallback


def environment(repo: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    system = Path(env.get("SystemRoot", "C:/Windows"))
    paths = [ROOT / "runtime/python", ROOT / "runtime/node", ROOT / "runtime/ffmpeg/bin",
             ROOT / "runtime/hyperframes/node_modules/.bin", system / "System32"]
    env["PATH"] = os.pathsep.join(map(str, paths)) + os.pathsep + env.get("PATH", "")
    env.pop("PYTHONHOME", None)
    env["PYTHONPATH"] = str(ROOT / repo) if repo else ""
    if repo == "copy_skill/copy_skill-main":
        env["PYTHONPATH"] = str(ROOT / repo / "src")
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1", HAIKE_PORTABLE_OFFLINE="1",
               VIDEOHUB_ROOT=str(ROOT), DOUYIN_MSVC_RUNTIME_DIR=str(ROOT / "runtime/msvc"),
               FFMPEG_BINARY=str(ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"),
               FFPROBE_BINARY=str(ROOT / "runtime/ffmpeg/bin/ffprobe.exe"),
               REMOTION_BROWSER_EXECUTABLE=str(ROOT / BROWSER),
               HYPERFRAMES_BROWSER_PATH=str(ROOT / BROWSER), PRODUCER_HEADLESS_SHELL_PATH=str(ROOT / BROWSER),
               HYPERFRAMES_FFMPEG_PATH=str(ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"),
               HYPERFRAMES_FFPROBE_PATH=str(ROOT / "runtime/ffmpeg/bin/ffprobe.exe"),
               HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_NO_AUTO_INSTALL="1", HYPERFRAMES_NO_UPDATE_CHECK="1",
               PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               PIP_NO_INDEX="1", UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never",
               npm_config_offline="true", BACKLOT_DETACHED="1")
    env["NO_PROXY"] = ",".join(filter(None, (env.get("NO_PROXY", ""), "localhost,127.0.0.1,::1")))
    return env


@contextmanager
def bundle_lock():
    path = ROOT / ".portable/start.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 40
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("另一个初始化或启动仍在执行，请查看 .portable/logs 后重试")
                time.sleep(.2)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def prepare() -> dict:
    started = time.monotonic()
    base = ROOT / "runtime/python"
    if not (base / "python.exe").is_file():
        raise RuntimeError("包内 Python 缺失，请完整解压离线运行包；本工具不会下载安装")
    for repo in REPOS:
        venv = ROOT / repo / ".venv"
        if not (venv / "Scripts/python.exe").is_file():
            raise RuntimeError(f"包内运行环境不完整：{repo}/.venv/Scripts/python.exe")
        write_text(venv / "pyvenv.cfg", f"home = {base}\ninclude-system-site-packages = false\nversion = 3.12.8\nexecutable = {base / 'python.exe'}\n")
    copy = ROOT / "copy_skill/copy_skill-main"
    for path in (copy / ".venv/Lib/site-packages").glob("__editable__.douyin_content_intelligence-*.pth"):
        write_text(path, "../../../src\n")
    config_path = copy / "config/content_intelligence.json"
    config = read_json(config_path)
    if not isinstance(config, dict):
        raise RuntimeError("CopySkill 配置缺失或损坏，请运行完整校验；未覆盖已有配置")
    config.setdefault("media_tools", {}).update(ffmpeg="../../runtime/ffmpeg/bin/ffmpeg.exe", ffprobe="../../runtime/ffmpeg/bin/ffprobe.exe")
    jobs = config.setdefault("jobs", {})
    jobs["lock_root"] = ".locks"
    jobs.setdefault("material_replication", {}).setdefault("episode_research_pack", {})["consumer_root"] = "../../Haike_video"
    visual = jobs.get("trusted_account_news", {}).get("visual_ocr", {})
    visual.update(ffmpeg_path="../../runtime/ffmpeg/bin/ffmpeg.exe", ffprobe_path="../../runtime/ffmpeg/bin/ffprobe.exe")
    crawler = config.setdefault("media_crawler", {})
    crawler.update(root="third_party/MediaCrawler", python="third_party/MediaCrawler/.venv/Scripts/python.exe")
    # A rendering headless browser is not a substitute for interactive platform login.
    if crawler.get("chrome_path") and not Path(crawler["chrome_path"]).is_file():
        crawler["chrome_path"] = ""
    write_json(config_path, config)
    for relative in (".portable/logs", "Haike_video/content/episodes", "Haike_video/content/library",
                     "Haike_video/content/templates", "Haike_video/projects", "Haike_video/renders",
                     "Haike_video/cache", "Haike_video/temp", "Haike_video/work", "creatorhub/data"):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)
    for src, target in (("Haike_video/.env.example", "Haike_video/.env.local"), ("creatorhub/config.example.yaml", "creatorhub/config.yaml")):
        if not (ROOT / target).exists():
            shutil.copyfile(ROOT / src, ROOT / target)
    result = {"root": str(ROOT), "prepared_seconds": round(time.monotonic() - started, 3),
              "network_install": False, "local_tts": "optional_not_started"}
    write_json(ROOT / ".portable/prepared.json", result)
    print("本地路径已就绪；本地 Qwen TTS 为可选扩展，默认跳过。若需要安装，请明确让 Agent 按 Haike_video/docs/LOCAL_TTS_ZH-CN.md 检查安装条件；本次未安装或启动。", flush=True)
    return result


def integrity() -> int:
    manifest = read_json(ROOT / "PACKAGE-MANIFEST.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise RuntimeError("文件清单缺失或损坏，无法完成完整校验")
    count = 0
    for entry in manifest["files"]:
        if entry.get("mutable"):
            continue
        relative = Path(entry["path"])
        path = (ROOT / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(ROOT.resolve()):
            raise RuntimeError("文件清单包含包外路径")
        if not path.is_file():
            raise RuntimeError("包内文件缺失：" + entry["path"])
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != entry["sha256"]:
            raise RuntimeError("包内文件发生变化：" + entry["path"])
        count += 1
    return count


def diagnose(full: bool = False) -> dict:
    started = time.monotonic()
    required = ["runtime/python/python.exe", "runtime/python/pythonw.exe", "runtime/node/node.exe", "runtime/ffmpeg/bin/ffmpeg.exe",
                "runtime/ffmpeg/bin/ffprobe.exe", BROWSER,
                "Haike_video/backlot/server.py", "Haike_video/remotion-composer/node_modules/@remotion/cli/package.json"]
    required += [f"runtime/msvc/{name}.dll" for name in ("msvcp140", "vcruntime140", "vcruntime140_1")]
    required += [f"{repo}/.venv/Scripts/{name}.exe" for repo in REPOS for name in ("python", "pythonw")]
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    if missing:
        raise RuntimeError("离线运行包缺少文件：" + "、".join(missing[:8]))
    checks = [([str(ROOT / "Haike_video/.venv/Scripts/python.exe"), "-s", "-c",
                "import sys; assert sys.version_info[:3] == (3,12,8); import fastapi, uvicorn"], "Haike_video"),
              ([str(ROOT / "runtime/node/node.exe"), "--version"], None),
              ([str(ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"), "-version"], None)]
    for command, repo in checks:
        try:
            completed = subprocess.run(command, cwd=ROOT / repo if repo else ROOT, env=environment(repo),
                                       capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("包内运行工具无法启动，请查看完整诊断：" + Path(command[0]).name) from error
        if completed.returncode:
            write_text(ROOT / ".portable/logs/diagnose-process.log", completed.stderr.decode("utf-8", errors="replace"))
            raise RuntimeError("包内运行工具检查失败：" + Path(command[0]).name)
    result = {"ok": True, "root": str(ROOT), "full": full,
              "file_count": integrity() if full else None, "diagnose_seconds": round(time.monotonic() - started, 3)}
    write_json(ROOT / ".portable/logs/diagnose.json", result)
    print("离线运行工具检查通过。" + ("完整文件校验通过。" if full else "完整文件校验可运行 03-check.cmd -Full。"), flush=True)
    return result


def http_json(port: int, path: str):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=.8) as response:
            return json.loads(response.read(32768))
    except (OSError, ValueError):
        return None


def own_identity(port: int, kind: str, nonce: str | None = None):
    identity = http_json(port, "/api/portable/identity")
    if not isinstance(identity, dict) or identity.get("kind") != kind:
        return None
    try:
        same_root = os.path.normcase(str(Path(identity["root"]).resolve())) == os.path.normcase(str(ROOT.resolve()))
    except (KeyError, TypeError, ValueError):
        return None
    if not same_root or not isinstance(identity.get("pid"), int) or identity["pid"] <= 0 or not identity.get("nonce"):
        return None
    if nonce is not None and identity["nonce"] != nonce:
        return None
    health = http_json(port, "/api/health" if kind == "backlot" else "/health")
    if not isinstance(health, dict):
        return None
    if kind == "backlot" and (health.get("ok") is not True or health.get("app") != "backlot"):
        return None
    if kind == "creatorhub" and not (health.get("ok") is True or health.get("status") == "ok"):
        return None
    return identity


def choose_port(requested: int, kind: str, excluded: set[int]):
    if kind == "backlot" and requested != 4188:
        raise RuntimeError("工作台入口统一为4188，请使用本项目启动器")
    state = read_json(ROOT / ".portable/services.json", {})
    recorded = [item.get("port") for item in state.get("services", []) if item.get("kind") == kind]
    candidates = [4188] if kind == "backlot" else list(dict.fromkeys(
        [p for p in recorded if isinstance(p, int) and 1024 <= p <= 65535]
        + list(range(requested, min(requested + 101, 65536)))))
    for port in candidates:
        if port in excluded:
            continue
        identity = own_identity(port, kind)
        if identity:
            return port, identity
        try:
            with socket.socket() as sock:
                if os.name == "nt":
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", port))
            return port, None
        except OSError:
            continue
    raise RuntimeError(f"{requested} 附近无可用端口，请指定其他端口；未停止其他程序")


def start(port: int = 4188, publisher: bool = False, publisher_port: int = 8000, no_browser: bool = False) -> dict:
    started = time.monotonic()
    prepared = prepare()
    diagnosed = diagnose()
    specs = [("backlot", "Haike_video", port)]
    if publisher:
        specs.append(("creatorhub", "creatorhub", publisher_port))
    services, owned, used = [], [], set()
    try:
        for kind, repo, requested in specs:
            service_started = time.monotonic()
            selected, existing = choose_port(requested, kind, used)
            used.add(selected)
            if existing:
                identity, reused = existing, True
            else:
                nonce = secrets.token_hex(24)
                # Run the real interpreter, not a venv trampoline, so the handle
                # identifies exactly the child owned by this invocation.
                command = [str(ROOT / "runtime/python/pythonw.exe"), "-s", str(ROOT / "portable/portable.py"),
                           "_serve", "--kind", kind, "--port", str(selected), "--nonce", nonce]
                with (ROOT / f".portable/logs/{kind}.out.log").open("ab") as out, (ROOT / f".portable/logs/{kind}.err.log").open("ab") as err:
                    kwargs = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)} if os.name == "nt" else {"start_new_session": True}
                    process = subprocess.Popen(command, cwd=ROOT / repo, env=environment(repo), stdout=out, stderr=err,
                                               stdin=subprocess.DEVNULL, close_fds=True, **kwargs)
                owned.append(process)
                deadline = time.monotonic() + 90
                identity = None
                while time.monotonic() < deadline:
                    identity = own_identity(selected, kind, nonce)
                    if identity:
                        break
                    if process.poll() is not None:
                        break
                    time.sleep(.25)
                if not identity:
                    raise RuntimeError(f"{kind} 未完成启动，请查看 .portable/logs/{kind}.err.log")
                reused = False
            services.append({"kind": kind, "root": str(ROOT), "port": selected, "pid": identity["pid"],
                             "nonce": identity["nonce"], "reused": reused, "url": f"http://127.0.0.1:{selected}/",
                             "ready_seconds": round(time.monotonic() - service_started, 3)})
        result = {"root": str(ROOT), "services": services, "prepare_seconds": prepared["prepared_seconds"],
                  "diagnose_seconds": diagnosed["diagnose_seconds"], "start_seconds": round(time.monotonic() - started, 3)}
        write_json(ROOT / ".portable/services.json", result)
        write_json(ROOT / ".portable/logs/last-start.json", result)
        for service in services:
            print(("工作台：" if service["kind"] == "backlot" else "发布服务：") + service["url"], flush=True)
        print(f"启动检查耗时 {result['start_seconds']:.2f} 秒；未安装依赖、未启动本地 TTS。", flush=True)
        if not no_browser:
            try:
                if os.name == "nt":
                    os.startfile(services[0]["url"])
                else:
                    import webbrowser
                    webbrowser.open(services[0]["url"])
            except OSError:
                print("无法自动打开浏览器，请复制上面的工作台地址。", flush=True)
        return result
    except Exception:
        # Only processes created by this invocation are touched.
        for process in owned:
            if process.poll() is None:
                process.terminate()
        raise


def serve(kind: str, port: int, nonce: str) -> None:
    repo = "Haike_video" if kind == "backlot" else "creatorhub"
    os.environ.update(environment(repo))
    os.chdir(ROOT / repo)
    sys.path.insert(0, str(ROOT / repo))
    site.addsitedir(str(ROOT / repo / ".venv/Lib/site-packages"))
    # Preload bundled native libraries before importing application modules.
    dll_directory = ROOT / "runtime/msvc"
    if os.name == "nt":
        import ctypes
        dll_cookie = os.add_dll_directory(str(dll_directory))
        dll_handles = [ctypes.WinDLL(str(dll_directory / name)) for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")]
    if kind == "backlot":
        from backlot.server import app
    else:
        from app.main import app
    async def identity():
        return {"kind": kind, "root": str(ROOT.resolve()), "pid": os.getpid(), "nonce": nonce}
    app.add_api_route("/api/portable/identity", identity, methods=["GET"], include_in_schema=False)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="海客视频离线运行包；所有准备均在本地完成")
    parser.add_argument("action", choices=("prepare", "diagnose", "start", "_serve"))
    parser.add_argument("--full", action="store_true", help="完整 SHA256 文件校验")
    parser.add_argument("--port", type=int, default=4188)
    parser.add_argument("--publisher", action="store_true")
    parser.add_argument("--publisher-port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--kind", choices=("backlot", "creatorhub"), default="backlot")
    parser.add_argument("--nonce", default="")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535 or not 1024 <= args.publisher_port <= 65535:
        parser.error("端口须为 1024–65535")
    try:
        if args.action == "_serve":
            if not args.nonce:
                raise RuntimeError("内部启动缺少实例标识，请使用 start")
            serve(args.kind, args.port, args.nonce)
        else:
            with bundle_lock():
                if args.action == "prepare":
                    prepare()
                elif args.action == "diagnose":
                    prepare()
                    diagnose(args.full)
                else:
                    start(args.port, args.publisher, args.publisher_port, args.no_browser)
        return 0
    except Exception as error:
        message = f"操作失败：{error}"
        print(message, file=sys.stderr, flush=True)
        try:
            write_json(ROOT / ".portable/logs/last-error.json", {"action": args.action, "error": str(error), "root": str(ROOT)})
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
