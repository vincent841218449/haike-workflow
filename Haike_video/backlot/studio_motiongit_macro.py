"""Compile public .motion macro contracts; the signed runner owns choreography."""
import hashlib
import math
import re
from backlot.studio_motion_director import compile_evidence, validate_semantics
from backlot.work_catalog import WorkError


def groups(guide):
    result = {}
    for row in guide.get('groups', []):
        # Retained basic expressions are a distinct extension; they cannot stand
        # in for the template's authored main tour under a native selection.
        if re.match(r'^\d{2}-X:', row.get('id','')): continue
        profile = row.get('profile', {})
        if not profile.get('intents'): continue
        result[row['id']] = {
            'id': row['id'], 'fields': [{k:v for k,v in field.items() if k in {'id','type','label','required','maxChars','maxItems','minItems','min','max','inputPath'}} for field in row.get('slots', [])],
            'intents': profile['intents'], 'phases': profile.get('requiredPhases', []),
            'counts': profile.get('cardinality', {}), 'cueRoles': profile.get('cueRoles', {}),
            'duration': {'minFrames':row.get('minFrames',1)}, 'effects':profile.get('effects',[]),
        }
    return result


def validate(draft, segments, cues, storyboard, guide):
    contracts = groups(guide)
    if not isinstance(segments,list) or not 1 <= len(segments) <= 30:
        raise WorkError('原生镜头组需要完整分段', 'template_incompatible')
    cursor = 0; text = ''; normalized = []; used = set()
    known = {m['asset']['id'] for m in storyboard['scenes']}
    for item in segments:
        if not isinstance(item,dict) or set(item)-{'group','text','from_cue','to_cue','values','anchors','semantics'}:
            raise WorkError('原生镜头组参数格式无效', 'template_incompatible')
        group = contracts.get(item.get('group'))
        a,b = item.get('from_cue'),item.get('to_cue')
        if not group or type(a) is not int or type(b) is not int or a != cursor or not a <= b < len(cues):
            raise WorkError('原生镜头组没有连续覆盖真实时钟', 'template_incompatible')
        source = item.get('text')
        if not isinstance(source,str) or not source.strip(): raise WorkError('镜头原文不能为空','template_incompatible')
        validate_semantics(source,group,item.get('semantics'))
        start = 0 if a == 0 else cues[a]['startMs']/1000
        end = storyboard['duration'] if b == len(cues)-1 else cues[b+1]['startMs']/1000
        if round((end-start)*60) < group['duration']['minFrames']:
            raise WorkError('原生完整动作窗口超出当前口播段落','template_incompatible')
        values = item.get('values',{}); fields = {f['id']:f for f in group['fields']}
        if not isinstance(values,dict) or set(values)-fields.keys():raise WorkError('引用了所选模板外的参数','template_incompatible')
        for key,value in values.items():
            field = fields[key]
            if field['type'] in {'text','dynamicText'}:
                if not isinstance(value,str):raise WorkError('模板文字格式无效','template_incompatible')
            elif field['type']=='number':
                if type(value) not in {int,float} or not math.isfinite(value):raise WorkError('模板数值格式无效','template_incompatible')
            elif field['type']=='talk':
                raise WorkError('人物必须由本期口播母版绑定，不能另填示例路径','template_incompatible')
            elif field['type']!='talk':
                if not isinstance(value,dict) or set(value)-{'asset','offset','entityId'} or value.get('asset') not in known:
                    raise WorkError('原生镜头只接受本期真实素材编号','template_incompatible')
                if 'offset' in value and (type(value['offset']) not in {int,float} or not 0<=value['offset']<=600):
                    raise WorkError('素材起点无效','template_incompatible')
                used.add(value['asset'])
        anchors=item.get('anchors',{})
        if not isinstance(anchors,dict) or set(anchors)-set(group['cueRoles'].values()) or any(type(i)is not int or not a<=i<=b or cues[i].get('clock')!='word' for i in anchors.values()):
            raise WorkError('原生动作需要本段真实词级落点','template_incompatible')
        normalized.append({**item,'start':start,'end':end,
            'resolved_anchors':{role:{'at':cues[i]['startMs']/1000-start} for role,i in anchors.items()}})
        cursor=b+1;text+=source
    if text!=draft['text'] or cursor!=len(cues):raise WorkError('原生镜头组遗漏或改写原文','template_incompatible')
    required={m['id'] for m in draft['input'].get('ai',{}).get('materials',[]) if m.get('mode')=='must'}
    if required-used:raise WorkError('原生镜头组遗漏必须使用的素材','template_incompatible')
    return {'workflow':'macro','segments':normalized}


def params(draft, selection, guide, media, duration):
    contracts=groups(guide); identity=hashlib.sha256(draft['text'].encode()).hexdigest()
    rows=[];units=[];cursor=0
    for index,s in enumerate(selection['segments']):
        group=contracts[s['group']];slots={}
        for key,value in s.get('values',{}).items():
            if isinstance(value,dict):
                slots[key]={'path':media[value['asset']],**{k:v for k,v in value.items() if k!='asset'}}
            else:slots[key]=value
        semantics,source_units,_=compile_evidence(s['text'],group,s['semantics'],identity[:16],cursor,slots)
        units.extend(source_units);cursor+=len(s['text'])
        rows.append({'id':f'segment-{index+1}','text':s['text'],
            'durationFrames':round(s['end']*60)-round(s['start']*60),**semantics,
            'anchors':s['resolved_anchors'],
            'candidates':{s['group']:{'slots':slots}}})
    return {'schema':'adu-auto-brief/1','brand':'海客科技','fps':60,'layout':draft['input']['motion']['layout'],
        'narrationDuration':duration,'segments':rows,'allowedStyles':sorted({s['group'].split(':')[0] for s in selection['segments']}),
        'stylePolicy':'coherent-first','repairPolicy':{'mode':'off'},'fontPolicy':'preferred',
        'contentEvidence':{'schema':'adu-content-evidence/1','text':draft['text'],'textSha256':identity,
            'sourceKind':'user-confirmed-transcript','units':units,'assets':[]}}
