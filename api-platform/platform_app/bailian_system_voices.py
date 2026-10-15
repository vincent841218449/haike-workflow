"""Frozen official presets; no supplier calls or credentials are needed to browse."""
import json
from pathlib import Path

CATALOGUE = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
MODEL = CATALOGUE['model']
TARGET_MODEL = CATALOGUE['target_model']


def identity(voice):
    return 'voice_bailian_cv3_' + voice


def presets():
    return [{**v, 'id': identity(v['voice'])} for v in CATALOGUE['voices']]


def public_items(production_ready):
    return [{k:v for k,v in {
        **item, 'scope':'system', 'provider':'阿里百炼', 'model':MODEL,
        'target_model':TARGET_MODEL, 'status':'ready', 'production_ready':production_ready,
        'sample_status':'succeeded' if item['sample_url'] else 'unavailable',
        'sample_kind':'official', 'preview_ready':bool(item['sample_url']),
        'source':CATALOGUE['source'],
    }.items() if k != 'voice'} for item in presets()]
