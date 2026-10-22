"""Choose official media layouts by editorial role, preserving clocks and sources."""
import copy
import math

from backlot.work_catalog import WorkError

POLICY = 'dominant-footage-v1'
ROLES = {'footage','screenshot','product','evidence','logo'}


def framing(value):
    if not isinstance(value,dict) or set(value)-{'role','focus'} or not isinstance(value.get('role'),str) or value['role'] not in ROLES:
        raise WorkError('请按实际画面区分情境素材、截图、产品和证据','template_incompatible')
    focus=value.get('focus',{'x':.5,'y':.5})
    if not isinstance(focus,dict) or set(focus)!={'x','y'} or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in focus.values()):
        raise WorkError('素材取景焦点需要真实画面内的位置','template_incompatible')
    return {'role':value['role'],'focus':focus}


def kit_layout(segments,controls):
    """Use the author's large portrait control; no patch to protected animation."""
    result=copy.deepcopy(segments);policies={};decisions=[]
    for index,scene in enumerate(result):
        value=scene.pop('$framing',None)
        if value is None:continue  # Frozen historical inputs retain their old recipe.
        value=framing(value);footage=value['role']=='footage';original=scene['control']
        if footage and original=='media':
            props=scene['props']
            if props.get('callouts'):raise WorkError('情境素材需要大画面，局部标注请安排独立镜头','template_incompatible')
            item={'src':props['src']}
            if len(props.get('title','').replace('*',''))>20:
                raise WorkError('大画面说明超过模板上限，请忠实精简后重新编排','template_incompatible')
            if props.get('title'):item['caption']=props['title']
            if 'sourceStart' in props:item['sourceStart']=props['sourceStart']
            scene.update(control='kenburns',variant='zoom',props={'items':[item]})
        if footage and scene['control']=='kenburns':
            if scene['t1']-scene['t0']<controls['kenburns']['minDur']:
                raise WorkError('大画面素材镜头过短，请按原声合并相邻语义段','template_incompatible')
            # parallax intentionally shrinks the foreground; narration footage is primary.
            scene['variant']='zoom';scene['presenter']='hide'
        def bind(value,spec):
            if spec.get('type')=='media' and isinstance(value,str):
                policy={'role':'photo' if footage else framing_value['role'],
                        'fit':'cover' if footage else 'contain','focus':framing_value['focus']}
                if value in policies and policies[value]!=policy:raise WorkError('同一素材的取景要求冲突，请分别安排素材实例','template_incompatible')
                policies[value]=policy
            elif isinstance(value,dict):
                for key,item in value.items():bind(item,spec.get('props',{}).get(key,{}))
            elif isinstance(value,list):
                for item in value:bind(item,{'type':spec.get('of'),'props':spec.get('props',{})})
        framing_value=value
        bind(scene['props'],{'type':'object','props':controls[scene['control']]['props']})
        decisions.append({'segment':index,'role':value['role'],'from_control':original,'control':scene['control'],
                          'presenter':scene.get('presenter'),'focus':value['focus']})
    return result,policies,{'policy':POLICY,'decisions':decisions}
