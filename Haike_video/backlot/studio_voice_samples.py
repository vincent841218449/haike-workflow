"""Persistent, versioned cache for the seven public system auditions."""
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from backlot.work_catalog import WorkError

MAX_BYTES = 5 * 1024 * 1024
_guard = threading.Lock()
_locks = {}
_recent = {}
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='voice-audition')


def preset(voice_id):
    from backlot.studio_voices import _system_catalogue
    return next((v for v in _system_catalogue().presets() if v['id'] == voice_id), None)


def _location(studio, voice):
    url = urlsplit(voice['sample_url'])
    suffix = Path(url.path).suffix.lower()
    if url.scheme != 'https' or url.hostname != 'help-static-aliyun-doc.aliyuncs.com' or suffix not in {'.mp3', '.wav'}:
        raise WorkError('系统试听地址不可用，请联系管理员核对')
    version = hashlib.sha256(voice['sample_url'].encode()).hexdigest()[:16]
    path = studio.private / 'voice-library/system-samples' / (voice['id'] + '-' + version + suffix)
    return path, version


def _audio(data):
    return data.startswith(b'ID3') or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224) or (data.startswith(b'RIFF') and data[8:12] == b'WAVE')


def _cached(path):
    if path.is_symlink() or not path.is_file() or not 12 <= path.stat().st_size <= MAX_BYTES:
        return False
    with path.open('rb') as stream:
        return _audio(stream.read(16))


def describe(studio, voice):
    path, version = _location(studio, voice)
    return {'sample_url': '/api/studio/voices/' + voice['id'] + '/sample?v=' + version,
            'sample_cached': _cached(path)}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download(url):
    # Only frozen public catalogue URLs reach here; never attach an account Key.
    with build_opener(_NoRedirect()).open(Request(url), timeout=15) as response:
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_BYTES:
            raise ValueError('sample too large')
        data = response.read(MAX_BYTES + 1)
    if not 12 <= len(data) <= MAX_BYTES or not _audio(data):
        raise ValueError('invalid audio sample')
    return data


def sample(studio, voice_id):
    voice = preset(voice_id)
    if not voice:
        raise WorkError('未找到这个系统音色')
    path, _ = _location(studio, voice)
    with _guard:
        lock = _locks.setdefault(str(path), threading.Lock())
    with lock:
        if _cached(path):
            return path
        if path.is_symlink():
            raise WorkError('试听文件路径不可用')
        temporary = None
        try:
            data = _download(voice['sample_url'])
            if not 12 <= len(data) <= MAX_BYTES or not _audio(data):
                raise ValueError('invalid audio sample')
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
            temporary.write_bytes(data)
            temporary.chmod(0o600)
            temporary.replace(path)
        except Exception:
            raise WorkError('试听音频暂未加载完成，请稍后重试；已缓存的试听仍可播放') from None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    return path


def _warm(studio, voice_id):
    try:
        sample(studio, voice_id)
    except WorkError:
        pass  # Playback can retry; a failed warm-up never interrupts browsing.


def prefetch(studio, items):
    for item in items:
        voice = preset(item['id']) if item.get('sample_kind') == 'official' else None
        if not voice:
            continue
        path, _ = _location(studio, voice)
        if _cached(path):
            continue
        key = str(path)
        with _guard:
            if time.monotonic() - _recent.get(key, -60) < 60:
                continue
            _recent[key] = time.monotonic()
        _pool.submit(_warm, studio, voice['id'])
