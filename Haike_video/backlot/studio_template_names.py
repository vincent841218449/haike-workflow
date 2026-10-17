"""Stable upstream names shared by selection, execution and task receipts."""

NAMES = {
    '01-A': '原片节奏', '01-B': '连续形变', '01-C': '纵深舞台',
    '01-D': '杂志分屏', '01-E': '节拍字效', '02-A': '纸面天平',
    '02-B': '纸面聚合', '03-A': '多屏展陈', '04-A': '仪器台演示',
    '05-A': '角色与物件接力', '06-A': '原生竖屏',
    'motiongit-612': '科技控制台 · 口播讲解 · 竖屏',
}


def name(style, fallback=None):
    return NAMES.get(style, fallback or style)


def label(style, fallback=None):
    title = name(style, fallback)
    return f'{style} · {title}' if style in NAMES and not style.startswith('motiongit-') else title


# Public author catalog observed 2026-10-17. A listing is never an installation.
MOTIONGIT_CATALOG = [
    ('385712','酷炫科技风 · 口播讲解','portrait'),
    ('vibrant-poster-portrait','活力海报 · 口播讲解 · 竖屏','portrait'),
    ('vibrant-poster','活力海报 · 口播讲解','landscape'),
    ('template-05-native-portrait','鲜色角色 · 叙事讲解 · 竖屏','portrait'),
    ('template-05-native','鲜色角色 · 叙事讲解','landscape'),
    ('template-04-dark-console-portrait','科技控制台 · 口播讲解 · 竖屏','portrait'),
    ('template-04-dark-console','科技控制台 · 口播讲解','landscape'),
    ('template-03-native-portrait','深色立体 · 多屏展陈 · 竖屏','portrait'),
    ('template-03-native','深色立体 · 多屏展陈','landscape'),
    ('template-02-expanded-portrait','纸面透视 · 口播讲解 · 竖屏','portrait'),
    ('template-02-expanded','纸面透视 · 口播讲解','landscape'),
    ('template-01-integrated-portrait','现代图文 · 口播讲解 · 竖屏','portrait'),
    ('template-01-integrated','现代图文 · 口播讲解','landscape'),
]
