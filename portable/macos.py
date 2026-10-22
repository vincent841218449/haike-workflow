"""Mac adapter for the bundled launcher; original Windows entry stays intact."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser

import portable as bundle

ROOT = bundle.ROOT
CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
DEFAULT_PORT = 4188


def browser_path() -> Path:
    browsers = sorted((ROOT / 'Haike_video/remotion-composer/node_modules/.remotion').glob('**/chrome-headless-shell'))
    return next((p for p in browsers if p.is_file() and os.access(p, os.X_OK)), CHROME)


def environment(repo: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    paths = [ROOT / 'runtime/macos/bin', ROOT / 'runtime/hyperframes/node_modules/.bin',
             Path.home() / '.local/bin', Path('/usr/bin'), Path('/bin'), Path('/usr/sbin')]
    if repo:
        paths.insert(0, ROOT / repo / '.venv/bin')
    env['PATH'] = os.pathsep.join(map(str, paths)) + os.pathsep + env.get('PATH', '')
    env.pop('PYTHONHOME', None)
    env['PYTHONPATH'] = str(ROOT / repo) if repo else ''
    if repo == 'copy_skill/copy_skill-main':
        env['PYTHONPATH'] = str(ROOT / repo / 'src')
    ffmpeg, ffprobe = (str(ROOT / 'runtime/macos/bin' / tool) for tool in ('ffmpeg', 'ffprobe'))
    browser = str(browser_path())
    env.update(VIDEOHUB_ROOT=str(ROOT), PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1',
               FFMPEG_BINARY=ffmpeg, FFPROBE_BINARY=ffprobe, REMOTION_BROWSER_EXECUTABLE=browser,
               HYPERFRAMES_BROWSER_PATH=browser, PRODUCER_HEADLESS_SHELL_PATH=browser,
               HYPERFRAMES_FFMPEG_PATH=ffmpeg, HYPERFRAMES_FFPROBE_PATH=ffprobe,
               HYPERFRAMES_NO_TELEMETRY='1', HYPERFRAMES_NO_AUTO_INSTALL='1', HYPERFRAMES_NO_UPDATE_CHECK='1',
               PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               BACKLOT_DETACHED='1')
    adu = ROOT / 'runtime/adu-motion-video'
    if (adu / 'scripts/pipeline.py').is_file():
        env['HAIKE_ADU_ROOT'] = str(adu)
    env['NO_PROXY'] = ','.join(filter(None, (env.get('NO_PROXY', ''), 'localhost,127.0.0.1,::1')))
    return env


def prepare() -> dict:
    started = time.monotonic()
    for repo in bundle.REPOS:
        if not (ROOT / repo / '.venv/bin/python').is_file():
            raise RuntimeError(f'Mac Python 环境缺失：{repo}/.venv/bin/python')
    for relative in ('.portable/logs', 'Haike_video/content/episodes', 'Haike_video/content/library',
                     'Haike_video/content/templates', 'Haike_video/projects', 'Haike_video/renders',
                     'Haike_video/cache', 'Haike_video/temp', 'Haike_video/work', 'creatorhub/data'):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)
    for source, target in (('Haike_video/.env.example', 'Haike_video/.env.local'),
                           ('creatorhub/config.example.yaml', 'creatorhub/config.yaml')):
        if not (ROOT / target).exists():
            shutil.copyfile(ROOT / source, ROOT / target)
    default_config = ROOT / 'copy_skill/copy_skill-main/config/content_intelligence.json'
    config_path = default_config.with_name('content_intelligence.local.json')
    if not config_path.exists():
        shutil.copyfile(default_config, config_path)
    config = bundle.read_json(config_path)
    if not isinstance(config, dict):
        raise RuntimeError('CopySkill 配置无法读取，未覆盖')
    backup = ROOT / '.portable/content_intelligence.windows.json'
    if not backup.exists():
        shutil.copyfile(config_path, backup)
    config.setdefault('media_tools', {}).update(ffmpeg='../../runtime/macos/bin/ffmpeg', ffprobe='../../runtime/macos/bin/ffprobe')
    jobs = config.setdefault('jobs', {})
    jobs['lock_root'] = '.locks'
    jobs.setdefault('material_replication', {}).setdefault('episode_research_pack', {})['consumer_root'] = '../../Haike_video'
    visual = jobs.setdefault('trusted_account_news', {}).setdefault('visual_ocr', {})
    visual.update(ffmpeg_path='../../runtime/macos/bin/ffmpeg', ffprobe_path='../../runtime/macos/bin/ffprobe')
    config.setdefault('media_crawler', {}).update(root='third_party/MediaCrawler',
        python='third_party/MediaCrawler/.venv/bin/python', chrome_path=str(CHROME))
    bundle.write_json(config_path, config)
    result = {'root': str(ROOT), 'platform': 'macos-arm64', 'prepared_seconds': round(time.monotonic()-started, 3),
              'local_tts': 'optional_not_started'}
    bundle.write_json(ROOT / '.portable/prepared-macos.json', result)
    return result


def diagnose() -> dict:
    started = time.monotonic()
    env = environment()
    checks = []
    for repo, imports in [('Haike_video', 'fastapi,uvicorn,cv2,PIL,oss2'),
                          ('copy_skill/copy_skill-main', 'douyin_intelligence,cv2,rapidocr,faster_whisper'),
                          ('creatorhub', 'fastapi,uvicorn,sqlmodel,patchright,curl_cffi')]:
        checks.append((repo, [str(ROOT / repo / '.venv/bin/python'), '-c', f'import {imports}']))
    checks += [('Node', [shutil.which('node', path=env['PATH']) or 'node', '--version']),
               ('FFmpeg', [env['FFMPEG_BINARY'], '-version']), ('FFprobe', [env['FFPROBE_BINARY'], '-version']),
               ('渲染浏览器', [str(browser_path()), '--version'])]
    rows = []
    for label, command in checks:
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        rows.append({'name': label, 'ok': completed.returncode == 0})
        if completed.returncode:
            bundle.write_text(ROOT / '.portable/logs/diagnose-macos-error.log', completed.stderr)
            raise RuntimeError(f'{label} 体检失败，见 .portable/logs/diagnose-macos-error.log')
        print(f'[PASS] {label}', flush=True)
    result = {'ok': True, 'root': str(ROOT), 'checks': rows, 'diagnose_seconds': round(time.monotonic()-started, 3),
              'optional': ['Qwen3-TTS 未安装', '云服务 Key 未配置', '平台账号未登录', 'MediaCrawler 未启用', '中转仅 mock']}
    bundle.write_json(ROOT / '.portable/logs/diagnose-macos.json', result)
    return result


def choose_port(requested: int, kind: str, excluded: set[int]):
    if kind == 'backlot' and requested != DEFAULT_PORT:
        raise RuntimeError('工作台入口统一为4188，请使用本项目启动器')
    state = bundle.read_json(ROOT / '.portable/services.json', {})
    recorded = [s['port'] for s in state.get('services', []) if s.get('kind') == kind]
    candidates = [DEFAULT_PORT] if kind == 'backlot' else list(dict.fromkeys(recorded + list(range(requested, min(requested+101, 65536)))))
    for port in candidates:
        if port in excluded:
            continue
        identity = bundle.own_identity(port, kind)
        if identity:
            return port, identity
        try:
            with socket.socket() as sock:
                # Match uvicorn's Unix socket behavior so TIME_WAIT does not move the service.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', port))
            return port, None
        except OSError:
            continue
    raise RuntimeError(f'{requested} 端口已被其他服务占用，请释放该端口后重试；未启动其他端口')


def start(port: int, publisher: bool, publisher_port: int, no_browser: bool) -> dict:
    started = time.monotonic()
    prepare()
    specs = [('backlot', 'Haike_video', port)]
    if publisher:
        specs.append(('creatorhub', 'creatorhub', publisher_port))
    services, processes, used = [], [], set()
    try:
        for kind, repo, requested in specs:
            selected, identity = bundle.choose_port(requested, kind, used)
            used.add(selected)
            reused = bool(identity)
            if not identity:
                nonce = secrets.token_hex(24)
                command = [str(ROOT / repo / '.venv/bin/python'), str(Path(__file__).resolve()),
                           '_serve', '--kind', kind, '--port', str(selected), '--nonce', nonce]
                with (ROOT / f'.portable/logs/{kind}.out.log').open('ab') as out, (ROOT / f'.portable/logs/{kind}.err.log').open('ab') as err:
                    process = subprocess.Popen(command, cwd=ROOT / repo, env=environment(repo), stdin=subprocess.DEVNULL,
                                               stdout=out, stderr=err, close_fds=True, start_new_session=True)
                processes.append(process)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    identity = bundle.own_identity(selected, kind, nonce)
                    if identity or process.poll() is not None:
                        break
                    time.sleep(.25)
                if not identity:
                    raise RuntimeError(f'{kind} 未启动，见 .portable/logs/{kind}.err.log')
            services.append({'kind': kind, 'root': str(ROOT), 'port': selected, 'pid': identity['pid'],
                'nonce': identity['nonce'], 'reused': reused, 'url': f'http://127.0.0.1:{selected}/'})
        result = {'root': str(ROOT), 'services': services, 'start_seconds': round(time.monotonic()-started, 3)}
        bundle.write_json(ROOT / '.portable/services.json', result)
        bundle.write_json(ROOT / '.portable/logs/last-start-macos.json', result)
        for service in services:
            print(('工作台：' if service['kind'] == 'backlot' else '发布面板：') + service['url'], flush=True)
        if not no_browser:
            webbrowser.open(services[0]['url'])
        return result
    except Exception:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        raise


def stop() -> None:
    state = bundle.read_json(ROOT / '.portable/services.json', {})
    for service in state.get('services', []):
        identity = bundle.own_identity(service['port'], service['kind'], service['nonce'])
        if identity and identity['pid'] == service['pid']:
            os.kill(identity['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    with socket.socket() as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind(('127.0.0.1', service['port']))
                    break
                except OSError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError(f"{service['kind']} 尚未退出，请查看日志后重试")
            print(f"已停止本项目 {service['kind']} (PID {identity['pid']})")
    bundle.write_json(ROOT / '.portable/services.json', {'root': str(ROOT), 'services': []})


def main() -> int:
    parser = argparse.ArgumentParser(description='海客工作流 Mac 本地启动器')
    parser.add_argument('action', choices=['prepare', 'diagnose', 'start', 'stop', '_serve'])
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--publisher-port', type=int, default=8000)
    parser.add_argument('--publisher', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--kind', choices=['backlot', 'creatorhub'], default='backlot')
    parser.add_argument('--nonce', default='')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 1024 <= args.publisher_port <= 65535:
        parser.error('端口须为 1024–65535')
    bundle.environment = environment
    bundle.choose_port = choose_port
    try:
        if args.action == '_serve':
            if not args.nonce:
                raise RuntimeError('缺少启动实例标识')
            bundle.serve(args.kind, args.port, args.nonce)
        else:
            with bundle.bundle_lock():
                if args.action == 'prepare': prepare()
                elif args.action == 'diagnose': prepare(); diagnose()
                elif args.action == 'stop': stop()
                else: start(args.port, args.publisher, args.publisher_port, args.no_browser)
        return 0
    except Exception as error:
        print(f'操作失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
