"""Official examples must never change executable identities or readiness."""
import json
from pathlib import Path
from urllib.parse import urlparse

from backlot import studio_motiongit_samples as samples
from backlot.studio_template_names import MOTIONGIT_CATALOG


def test_all_official_portrait_identities_have_distinct_author_examples():
    rows = json.loads(Path(samples.__file__).with_suffix('.json').read_text())['templates']
    assert {r['template_id'] for r in rows} == {s for s, _, layout in MOTIONGIT_CATALOG if layout == 'portrait'}
    assert len(rows) == len({r['video'] for r in rows}) == len({r['cover'] for r in rows}) == 7
    for row in rows:
        assert row['ratio'] == '9:16'
        assert row['url'].startswith('https://motiongit.com/@adunext/' + row['template_id'] + '?')
        for field in ('video', 'cover'):
            url = urlparse(row[field])
            assert url.scheme == 'https' and url.netloc == 'media.openaicut.com' and not url.query
        assert row['video'].endswith('.mp4') and '-card.mp4' not in row['video']
        public = samples.official_sample(row['template_id'])
        assert public['official_sample'] and public['sample_language'] == 'zh'
        assert not {'template_ref', 'supported', 'automatic_ready', 'validated_execution_modes'} & public.keys()
    assert samples.official_sample('unknown') == {}


def test_pending_templates_show_real_examples_without_enabling_production(monkeypatch):
    from backlot import studio_motiongit, studio_template_registry
    monkeypatch.setattr(studio_motiongit, 'configuration', lambda: {})
    rows = studio_template_registry.pending_packages('portrait')
    assert len(rows) == 7
    assert all(r['official_sample'] and r['demo'].startswith('https://media.openaicut.com/') for r in rows)
    assert not any(r['supported'] for r in rows)
