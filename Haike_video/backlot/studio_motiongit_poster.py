"""The author's poster-kit host has its own CLI and review receipts."""
import copy
import json
import re
from pathlib import Path
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError,sha

# poster-kit-guide.json declares seven expressions integrated with the native
# palette. The remaining library variants are not artistically accepted by the
# author; a generic white-text variant must not be selected on the pale stage.
AUTO_EXPRESSIONS={'kinetic':['wave'],'qa':['flip'],'flow':['chain'],
                  'polaroid':['drop'],'mindmap':['radial'],
                  'checklist':['clipboard'],'cta':['button']}


def schema_adapter(schema,spec):
    """Expose a host envelope without changing the signed public contract."""
    timeline=copy.deepcopy(schema)
    item=timeline['properties']['segments']['items']
    definitions=[]
    for control in spec['controls']:
        row=copy.deepcopy(item);row['properties']['control']={'const':control}
        definitions.append(row)
    timeline['properties']['segments']['items']={'oneOf':definitions}
    return {'type':'object','properties':{'timeline':timeline,'workflow':{'const':'poster-kit'}},
            'required':['timeline','workflow'],'additionalProperties':False}


def arguments(instance,operation,args):
    root=Path(instance);base=['--workflow','poster-kit','--timeline']
    def value(flag):
        values=list(map(str,args))
        if flag not in values:raise WorkError('海报模板缺少运行参数','template_incompatible')
        return values[values.index(flag)+1]
    if operation in {'check-params','plan'}:
        output=[] if operation=='check-params' else ['--out',value('--out')]
        return [*base,str(args[0]),*output,'--language','zh']
    if operation=='prepare':return [*base,'@vault','--plan',str(root/'plan'),'--out',str(root/'project'),'--language','zh']
    if operation=='preview':return [*base,'@vault','--plan',str(root/'plan'),'--out',str(root/'project/host-preview'),'--times',value('--times'),'--language','zh']
    if operation=='render':return [*base,'@vault','--plan',str(root/'plan'),'--preview-review',str(root/'project/host-preview'),'--out',value('--out'),'--language','zh']
    return list(args)


def plan_info(instance):
    root=Path(instance);path=root/'plan/host-plan.json'
    report=json.loads(path.read_text())
    result=json.loads(report['result']) if isinstance(report['result'],str) else report['result']
    parameters=(root/report['parameter']).resolve()
    if report.get('workflow')!='poster-kit' or not parameters.is_relative_to(root.resolve()) or not parameters.is_file() or sha(parameters)!=report['parametersSha256']:
        raise WorkError('海报计划与冻结参数不一致','template_mismatch')
    value=json.loads(parameters.read_text())
    if result['duration']!=value['duration'] or len(result['segments'])!=len(value['segments']):
        raise WorkError('海报计划时长或镜头数不一致','template_mismatch')
    return {'workflow':'poster-kit','duration':value['duration'],'segments':value['segments'],
            'plan_path':path,'parameter_path':parameters}


def review_plan(instance):
    path=plan_info(instance)['plan_path'];value=json.loads(path.read_text());value['reviewed']=True
    atomic_private(path,value)


def content_layout(timeline):
    """Use the observed host's portrait content region beside its own face port."""
    value=copy.deepcopy(timeline)
    if value.get('layout')=='portrait' and value.get('presenter',{}).get('src'):
        for row in value['segments']:
            if 'area' not in row:
                # The poster's slam/split title includes an entry translation.
                # Reserve that motion inside the content zone, rather than
                # clipping text or relaxing the measured safety check.
                row['area']=({'x':100,'y':445,'w':800,'h':680} if row['control']=='title'
                             else {'x':100,'y':445,'w':880,'h':680} if row['control']=='kinetic'
                             else {'x':60,'y':445,'w':960,'h':680})
            props=row.get('props',{})
            if row['control']=='title' and len(props.get('line1',''))>12 and not props.get('line2'):
                cuts=[m.end() for m in re.finditer('[，、：；]',props['line1']) if m.end()<=12]
                if cuts:
                    at=cuts[-1];text=props['line1']
                    props.update(line1=text[:at],line2=text[at:])
        value.setdefault('captionPosition',{'bottomRatio':.34,'leftRatio':.08,'rightRatio':.16})
    value.update(narrationLayout='balanced',narrationVisualMode='follow-speech')
    return value


def preview_receipt(instance):
    root=Path(instance);project=root/'project';directory=project/'host-preview'
    path=directory/'preview-review.json';value=json.loads(path.read_text());info=plan_info(instance)
    plan=json.loads(info['plan_path'].read_text())
    if value.get('workflow')!='poster-kit' or value.get('parametersSha256')!=plan['parametersSha256'] or value.get('inputFiles')!=plan['inputFiles']:
        raise WorkError('海报预览不属于当前输入','template_mismatch')
    stills={}
    for name,identity in value['files'].items():
        file=(directory/name).resolve()
        if not file.is_relative_to(directory.resolve()) or not file.is_file() or sha(file)!=identity:
            raise WorkError('海报预览文件已改变','template_mismatch')
        if file.suffix=='.png':stills[str(file.relative_to(project.resolve()))]=identity
    geometry=json.loads((directory/'geometry.json').read_text())
    blocking=[hit for row in geometry.get('violations',[]) for hit in row.get('hits',[])
              if not (hit.get('kind')=='safe-edge' and hit.get('text','').strip() in {'“','”','「','」','‘','’'})]
    if blocking:
        raise WorkError('海报内容区的文字或人物安全区未通过，请调整对应镜头，原声保留','template_incompatible')
    if not stills:raise WorkError('海报没有真实预览画面','template_incompatible')
    receipt={'schema':'haike-poster-preview/1','reviewed':False,'stills':stills,
             'host_review_sha256':sha(path),'parameters_sha256':plan['parametersSha256']}
    atomic_private(project/'preview.json',receipt)
    return project


def approve_preview(instance):
    root=Path(instance);path=root/'project/host-preview/preview-review.json'
    # Outer inspection is bound to this exact inner receipt and all real stills.
    outer=json.loads((root/'project/preview.json').read_text())
    if outer['host_review_sha256']!=sha(path):
        raise WorkError('海报原生预览回执已改变','template_mismatch')
    value=json.loads(path.read_text())
    if value.get('reviewed') is True:return
    value['reviewed']=True;atomic_private(path,value)
    outer['host_review_sha256']=sha(path);atomic_private(root/'project/preview.json',outer)
