"""Public auditions persist locally; account-owned audio keeps its private contract."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import studio_voice_samples as cache, studio_voices
from backlot.studio import Studio
from backlot.studio_api import router
from backlot.work_catalog import WorkError

SAMPLE = b'ID3' + b'\0' * 1024


@pytest.fixture
def cached_studio(tmp_path, monkeypatch):
    studio = Studio(tmp_path / 'projects')
    voice = studio_voices._system_catalogue().presets()[0]
    downloads = []
    def download(url):
        downloads.append(url)
        return SAMPLE
    monkeypatch.setattr(cache, '_download', download)
    return studio, voice, downloads


def test_parallel_replays_and_recreated_studio_reuse_one_persistent_file(cached_studio):
    studio, voice, downloads = cached_studio
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda _: studio_voices.sample(studio, voice['id']), range(8)))
    assert len(downloads) == 1 and len(set(paths)) == 1
    assert paths[0].read_bytes() == SAMPLE
    assert paths[0].stat().st_mode & 0o777 == 0o600
    restored = Studio(studio.projects_root)
    assert studio_voices.sample(restored, voice['id']) == paths[0]
    assert len(downloads) == 1 and cache.describe(restored, voice)['sample_cached']


def test_http_replay_range_and_revalidation_need_no_gateway_call(cached_studio, monkeypatch):
    studio, voice, downloads = cached_studio
    monkeypatch.setattr(studio, 'client', lambda *args: pytest.fail('Public cached auditions must not query the gateway'))
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    client = TestClient(app)
    url = cache.describe(studio, voice)['sample_url']
    assert url.startswith('/api/studio/voices/') and '?v=' in url
    first = client.get(url)
    assert first.status_code == 200 and first.content == SAMPLE
    assert first.headers['content-type'] == 'audio/mpeg'
    assert 'immutable' in first.headers['cache-control'] and 'public' in first.headers['cache-control']
    partial = client.get(url, headers={'Range': 'bytes=0-8'})
    assert partial.status_code == 206 and partial.content == SAMPLE[:9]
    assert client.get(url, headers={'If-None-Match': first.headers['etag']}).status_code == 304
    assert len(downloads) == 1


@pytest.mark.parametrize('body', [b'<html>remote error</html>', b'ID3' + b'\0' * cache.MAX_BYTES])
def test_failed_download_does_not_poison_cache_and_can_be_retried(cached_studio, monkeypatch, body):
    studio, voice, _ = cached_studio
    monkeypatch.setattr(cache, '_download', lambda _: body)
    with pytest.raises(WorkError, match='暂未加载'):
        cache.sample(studio, voice['id'])
    assert not cache.describe(studio, voice)['sample_cached']
    monkeypatch.setattr(cache, '_download', lambda _: SAMPLE)
    assert cache.sample(studio, voice['id']).read_bytes() == SAMPLE
    assert not list((studio.private / 'voice-library/system-samples').glob('*.tmp'))


def test_unknown_presets_and_non_catalogue_hosts_never_download(cached_studio):
    studio, voice, downloads = cached_studio
    with pytest.raises(WorkError, match='未找到'):
        cache.sample(studio, '../../private')
    with pytest.raises(WorkError, match='地址不可用'):
        cache.describe(studio, {**voice, 'sample_url': 'https://127.0.0.1/private.mp3'})
    assert downloads == []


def test_upstream_sample_revision_changes_local_immutable_url(cached_studio):
    studio, voice, _ = cached_studio
    cache.sample(studio, voice['id'])
    changed = {**voice, 'sample_url': voice['sample_url'].replace('.mp3', '-new.mp3')}
    assert cache.describe(studio, voice)['sample_cached']
    assert not cache.describe(studio, changed)['sample_cached']
    assert cache.describe(studio, voice)['sample_url'] != cache.describe(studio, changed)['sample_url']


def test_prefetch_is_nonblocking_deduplicated_and_bounded_to_public_presets(cached_studio, monkeypatch):
    studio, voice, _ = cached_studio
    queued = []
    class Pool:
        def submit(self, fn, *args): queued.append(args)
    monkeypatch.setattr(cache, '_pool', Pool())
    items = [{**voice, 'sample_kind': 'official'}, {'id': 'voice_private', 'scope': 'personal'}]
    cache.prefetch(studio, items); cache.prefetch(studio, items)
    assert queued == [(studio, voice['id'])]


def test_personal_audio_response_stays_private(cached_studio, monkeypatch):
    studio, _, _ = cached_studio
    target = studio.private / 'personal.wav'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'RIFFprivate')
    monkeypatch.setattr(studio_voices, 'sample', lambda *args: target)
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    response = TestClient(app).get('/api/studio/voices/voice_personal/sample')
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['content-type'] == 'audio/wav'
