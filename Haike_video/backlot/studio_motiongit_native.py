"""Compile the delivered native recipe schema without replacing its choreography."""
from jsonschema import Draft202012Validator

from backlot.work_catalog import WorkError


def validate(draft,segments,cues,storyboard,schema,recipes):
    definitions={p['properties']['recipe']['const']:p for p in schema['properties']['segments']['oneOf'][0]['items']['oneOf']}
    contracts={r['id']:r for r in recipes}
    if not isinstance(segments,list) or not 1<=len(segments)<=30: raise WorkError('原生组需要完整分段','template_incompatible')
    normalized=[];previous=0;text='';cursor=0;used=set()
    known={s['asset']['id'] for s in storyboard['scenes']}
    for item in segments:
        if not isinstance(item,dict) or set(item)-{'recipe','text','from_cue','to_cue','inputs','assets','anchors','support','facts'}:
            raise WorkError('原生组配置格式无效','template_incompatible')
        recipe=item.get('recipe');source=item.get('text');a=item.get('from_cue');b=item.get('to_cue')
        if recipe not in definitions or type(a) is not int or type(b) is not int or a!=previous or not a<=b<len(cues) or not isinstance(source,str) or not source.strip():
            raise WorkError('原生组没有完整引用本期文案和时钟','template_incompatible')
        previous=b+1;text+=source
        end=round((storyboard['duration'] if b==len(cues)-1 else cues[b+1]['startMs']/1000)*60)
        anchors=item.get('anchors')
        if not isinstance(anchors,dict) or any(type(i) is not int or not a<=i<=b or cues[i].get('clock')!='word' for i in anchors.values()):
            raise WorkError('原生组动作需要当前段落的真实词级落点','template_incompatible')
        support=item.get('support')
        if not isinstance(support,list) or not support or any(not isinstance(q,str) or not q.strip() or q not in source for q in support):
            raise WorkError('原生组缺少显示内容的原文依据','template_incompatible')
        actual=item.get('facts',{});expected=contracts.get(recipe,{}).get('cardinality',{})
        if not isinstance(actual,dict) or set(actual)!=set(expected): raise WorkError('原生数量没有真实原文依据','template_incompatible')
        for key,bounds in expected.items():
            entities=actual[key]
            if not isinstance(entities,list): raise WorkError('数量必须引用实际实体，不能填写模板最小值','template_incompatible')
            names=[]
            for fact in entities:
                if not isinstance(fact,dict) or set(fact)!={'name','quote'} or not isinstance(fact['name'],str) or not fact['name'].strip() or not isinstance(fact['quote'],str) or fact['name'] not in fact['quote'] or fact['quote'] not in source:
                    raise WorkError('原生实体与本段原文不符','template_incompatible')
                names.append(fact['name'])
            if len(set(names))!=len(names) or not bounds['min']<=len(names)<=bounds['max']:
                raise WorkError('原生模板的真实数量不匹配，不能凑步骤或人物','template_incompatible')
        def media(value,key=''):
            if isinstance(value,str) and value.startswith('asset:'):
                if value[6:] not in known: raise WorkError('原生组引用了本期之外的素材','template_incompatible')
                used.add(value[6:])
            elif key in {'path','reaction','inputThumbnail','outputThumbnail'} and isinstance(value,str):
                raise WorkError('原生媒体只能引用本期素材编号','template_incompatible')
            elif isinstance(value,dict):
                for k,v in value.items():media(v,k)
            elif isinstance(value,list):
                for v in value:media(v,key)
        media(item.get('inputs',{}));media(item.get('assets',{}))
        result={'recipe':recipe,'durationFrames':end-cursor,'inputs':item.get('inputs',{}),
                'anchors':{role:max(0,cues[i]['startMs']/1000-cursor/60) for role,i in anchors.items()}}
        if item.get('assets'):result['assets']=item['assets']
        validator=Draft202012Validator({**definitions[recipe],'$defs':schema.get('$defs',{})})
        errors=list(validator.iter_errors(result))
        if errors: raise WorkError('原生组不符合真实参数合同：'+errors[0].message[:250],'template_incompatible')
        normalized.append(result);cursor=end
    if text!=draft['text'] or previous!=len(cues): raise WorkError('原生组未完整保留原文','template_incompatible')
    required={m['id'] for m in draft['input'].get('ai',{}).get('materials',[]) if m.get('mode')=='must'}
    if required-used:raise WorkError('原生组遗漏必须使用的素材','template_incompatible')
    return {'workflow':'native','segments':normalized,'evidence':segments}
