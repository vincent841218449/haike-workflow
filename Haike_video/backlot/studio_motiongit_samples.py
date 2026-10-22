"""Public author examples, independent of private executable package versions.

URLs are the media CDN used by the official Chinese catalog/detail players.
No proxy, media download, account key or test presenter is involved.
"""
import json
from pathlib import Path


def official_sample(template_id):
    data = json.loads(Path(__file__).with_suffix('.json').read_text())
    row = next((r for r in data['templates'] if r['template_id'] == template_id), None)
    if not row:
        return {}
    return {'name': row['name'], 'display_name': row['name'], 'official_name': row['name'],
            'preview': row['cover'], 'demo': row['video'],
            'official_sample': True, 'sample_language': 'zh',
            'sample_catalog_date': data['checked_at'],
            'external_preview_url': row['url'],
            'preview_basis': 'MotionGit 官网中文原版案例；展示作者样片编舞。制作使用你选择的已验收版本、文案、音色与人物，版本以制作信息为准。'}
