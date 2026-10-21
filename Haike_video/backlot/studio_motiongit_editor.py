"""Existing-media editing through the exact official MotionGit component pack.

This route never generates speech or avatars and never mixes template runtimes.
Planning renders real previews; submission binds the reviewed images and files.
"""
import json
import math
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from backlot import studio_motiongit as motion
from backlot.studio import atomic_private
from backlot.studio_template_registry import digest
from backlot.work_catalog import WorkError,sha


def contract(style):
    config,schema,caps=motion.contracts(style)
    if 'components' not in motion.execution_modes(config):
        raise WorkError('这款模板的组件制作尚未完成本地验收','template_incompatible')
    properties=schema['properties']['timeline']['properties']
    definitions={layer:{p['properties']['control']['const']:p['properties'].get('props',{})
        for p in properties.get(layer,{}).get('items',{}).get('oneOf',[])} for layer in ['segments','overlays']}
    return {'style':style,'layout':config['layout'],'template_ref':motion.template_ref(config),
        'controls':{k:{**caps['controls'][k],'schema':v} for k,v in definitions['segments'].items()},
        'overlays':{k:{**caps['controls'][k],'schema':v} for k,v in definitions['overlays'].items()},
        'transitions':properties['segments']['items']['oneOf'][0]['properties'].get('transition',{}).get('enum',caps.get('transitions',['cut'])),
        'purposes':sorted(motion.PURPOSES)}


def number(value,label):
    if type(value) not in {int,float} or not math.isfinite(value):raise WorkError(label+'需要有效数值')
    return value


def compile_selection(studio,draft,config,schema,caps,duration):
    from backlot.studio_storyboard import bind_script_ranges
    value=draft['input'];captions=value.get('captions',[])
    if not isinstance(captions,list) or not 1<=len(captions)<=3000:raise WorkError('请导入与完整口播对应的SRT字幕')
    cues=[];last=0
    for row in captions:
        if not isinstance(row,dict) or set(row)-{'start','end','text','en'}:raise WorkError('字幕只接受时间、原文和可选翻译')
        a,b=number(row.get('start'),'字幕开始时间'),number(row.get('end'),'字幕结束时间')
        if not last<=a<b<=duration+.02 or not isinstance(row.get('text'),str) or not row['text'].strip():
            raise WorkError('字幕需要按实际口播排列，不能重叠、空白或超出片尾')
        cues.append({'startMs':round(a*1000),'endMs':round(min(b,duration)*1000),'text':row['text'],'clock':'sentence'});last=b
    ranges=bind_script_ranges({'scenes':[{'from_cue':i,'to_cue':i,'script_start':0,'script_end':1} for i in range(len(cues))]},draft,cues,max_units=3000)['scenes']
    for cue,row in zip(cues,ranges):cue['text']=draft['text'][row['script_start']:row['script_end']]
    scenes=value.get('segments',[])
    if not isinstance(scenes,list) or not 1<=len(scenes)<=30:raise WorkError('请配置1至30个本期镜头')
    main_controls={p['properties']['control']['const'] for p in schema['properties']['timeline']['properties']['segments']['items']['oneOf']}
    previous=0;body=[];assets=set()
    def media(item,spec):
        if spec.get('type')=='media':
            if not isinstance(item,dict) or set(item)!={'asset'} or not isinstance(item['asset'],dict):raise WorkError('画面素材须从当前项目上传')
            identity=item['asset'].get('id');studio.asset(identity,draft['id']);assets.add(identity)
            return 'asset:'+identity
        if isinstance(item,dict):return {k:media(v,spec.get('props',{}).get(k,{})) for k,v in item.items()}
        if isinstance(item,list):return [media(v,{'type':spec.get('of'),'props':spec.get('props',{})}) for v in item]
        return item
    for index,scene in enumerate(scenes):
        if not isinstance(scene,dict) or set(scene)-{'id','control','variant','toCue','props','purpose','framing','styleProfile','presenter','transition','chapter','anchorCues'}:raise WorkError('镜头配置包含不支持的字段')
        end=scene.get('toCue');kind=scene.get('control')
        if type(end)is not int or not previous<=end<len(cues) or kind not in main_controls:raise WorkError('每个镜头需要使用主镜头组件，连续、完整地覆盖本期字幕句')
        props=media(scene.get('props',{}),{'type':'object','props':caps['controls'][kind].get('props',{})})
        source=''.join(c['text'] for c in cues[previous:end+1])
        row={'control':kind,'text':source,'from_cue':previous,'to_cue':end,'props':props,
             'anchors':scene.get('anchorCues',[]),'support':[source],'purpose':scene.get('purpose','neutral-emphasis')}
        for key in ['variant','framing','styleProfile','presenter','transition','chapter']:
            if scene.get(key):row[key]=scene[key]
        body.append(row);previous=end+1
    if previous!=len(cues):raise WorkError('最后一个镜头须覆盖口播最后一句，不能遗漏结尾')
    execution={**draft,'input':{'motion':{'style':config['style'],'layout':config['layout'],
        **({'profile':value['profile']} if value.get('profile') else {})},'templateExecution':'components',
        'templateRef':motion.template_ref(config),'music':value.get('music') or {'mode':'none'},'ai':{'materials':[]}}}
    selected=motion.validate_timeline(execution,body,cues,{'duration':duration,'scenes':[{'asset':{'id':i}} for i in assets]},schema,config)
    return execution,cues,selected


def compile_overlays(studio,draft,schema,caps,cues):
    from jsonschema import Draft202012Validator
    definitions={p['properties']['control']['const']:p for p in schema['properties']['timeline']['properties'].get('overlays',{}).get('items',{}).get('oneOf',[])}
    source=draft['input'].get('overlays',[])
    if not isinstance(source,list) or len(source)>30:raise WorkError('最多配置30个叠加效果')
    def media(value,spec):
        if spec.get('type')=='media':
            if not isinstance(value,dict) or set(value)!={'asset'} or not isinstance(value['asset'],dict):raise WorkError('叠加素材须从本项目上传')
            identity=value['asset'].get('id');studio.asset(identity,draft['id']);return 'asset:'+identity
        if isinstance(value,dict):return {k:media(v,spec.get('props',{}).get(k,{})) for k,v in value.items()}
        if isinstance(value,list):return [media(v,{'type':spec.get('of'),'props':spec.get('props',{})}) for v in value]
        return value
    result=[]
    for item in source:
        if not isinstance(item,dict) or set(item)-{'id','control','fromCue','toCue','props','variant','anchorCues'}:raise WorkError('叠加效果字段无效')
        kind=item.get('control');a,b=item.get('fromCue'),item.get('toCue')
        if kind not in definitions or type(a)is not int or type(b)is not int or not 0<=a<=b<len(cues):raise WorkError('叠加效果需要本期真实句界')
        row={'control':kind,'t0':cues[a]['startMs']/1000,'t1':cues[b]['endMs']/1000,
            'props':media(item.get('props',{}),{'type':'object','props':caps['controls'][kind].get('props',{})})}
        if item.get('variant'):row['variant']=item['variant']
        anchors=item.get('anchorCues',[])
        if not isinstance(anchors,list) or any(type(i)is not int or not a<=i<=b for i in anchors):raise WorkError('叠加动作需要本段真实句界')
        if anchors:row['cues']=[cues[i]['startMs']/1000 for i in anchors]
        if row['t1']-row['t0']<caps['controls'][kind]['minDur']:raise WorkError('叠加效果的实际句间时长不足原动作窗口')
        if list(Draft202012Validator(definitions[kind]).iter_errors(row)):raise WorkError('叠加效果参数不符合原包要求，请检查必填项、数量和文字长度')
        result.append(row)
    return result


def plan(studio,draft):
    from backlot.studio_motion import source_video,source_metadata
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    style=draft['input'].get('style','');contract(style);config,schema,caps=motion.contracts(style);config={**config,'style':style}
    if draft['input'].get('motionLayout')!=config['layout']:raise WorkError('当前模板与所选画幅不同，请选择对应的原包')
    duration=source_metadata(studio,draft)['duration']
    execution,cues,selected=compile_selection(studio,draft,config,schema,caps,duration)
    overlays=compile_overlays(studio,draft,schema,caps,cues)
    video,audio=source_video(studio,draft);identity=uuid4().hex
    folder=studio.projects_root/draft['id']/'renders'/('studio-'+str(draft['revision']))
    instance=folder/('motiongit-'+identity);folder.mkdir(parents=True,exist_ok=True)
    if audio is None:
        audio=folder/('source-voice-'+identity+'.wav');ffmpeg,_=resolve_ffmpeg_pair()
        result=subprocess.run([ffmpeg,'-v','error','-i',str(video),'-map','0:a:0','-c:a','pcm_s16le','-ar','48000',str(audio)],capture_output=True,timeout=180)
        if result.returncode:raise WorkError('口播音轨无法读取，原视频已保留')
    motion.make_plan(studio,execution,instance,video,audio,cues,selected,overlays=overlays)
    motion.preview_instance(instance);info=motion.plan_info(instance)
    preview=instance/'project/preview.json';data=json.loads(preview.read_text());stills=motion.preview_stills(data)
    def time_key(name):
        match=re.search(r't_([0-9.]+)\.png$',name)
        return float(match[1]) if match else float('inf')
    stills=dict(sorted(stills.items(),key=lambda item:time_key(item[0])))
    snapshot={'draft':draft,'execution':execution,'video':str(video),'video_sha256':sha(video),
        'audio':str(audio),'audio_sha256':sha(audio),'instance':instance.name,
        'preview_sha256':sha(preview),'stills':stills,'request':motion.freeze_job(studio,execution,folder,instance)}
    destination=studio.projects_root/draft['id']/'assets/motion-plans'/identity
    atomic_private(destination/'motiongit-snapshot.json',snapshot)
    return {'id':identity,'revision':draft['revision'],'cost_micros':0,
        'report':{'ready':True,'status':'ready','durationFrames':round(info['duration']*60),'selectedStyle':style,
            'missing':[],'blocking':[],'template_ref':motion.template_ref(config),'execution':'components'},
        'previews':[f'/api/studio/drafts/{draft["id"]}/motiongit-preview/{identity}/{i}' for i in range(len(stills))]}


def snapshot(studio,draft_id,plan_id):
    if not isinstance(plan_id,str) or not re.fullmatch('[a-f0-9]{32}',plan_id):raise WorkError('模板检查编号无效')
    path=studio.projects_root/draft_id/'assets/motion-plans'/plan_id/'motiongit-snapshot.json'
    if not path.is_file():raise WorkError('请先检查当前模板与素材')
    return json.loads(path.read_text())


def preview_file(studio,draft_id,plan_id,index):
    saved=snapshot(studio,draft_id,plan_id);names=list(saved['stills'])
    if not 0<=index<len(names):raise WorkError('预览图片不存在')
    root=studio.projects_root/draft_id/'renders'/saved['request']['render_id']/saved['instance']/'project'
    path=(root/names[index]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or sha(path)!=saved['stills'][names[index]]:
        raise WorkError('实际预览已改变，请重新检查','template_mismatch')
    return path


def freeze(studio,draft,plan_id,confirmed):
    if confirmed is not True:raise WorkError('请核对实际预览、完整台词及素材后确认')
    saved=snapshot(studio,draft['id'],plan_id)
    if saved['draft']!=draft:raise WorkError('内容已改变，请重新检查','template_mismatch')
    if sha(Path(saved['video']))!=saved['video_sha256'] or sha(Path(saved['audio']))!=saved['audio_sha256']:
        raise WorkError('口播来源已改变，请重新检查','template_mismatch')
    request=saved['request'];folder=studio.projects_root/draft['id']/'renders'/request['render_id'];instance=folder/saved['instance']
    for name,identity in request['files'].items():
        path=(instance/name).resolve()
        if not path.is_relative_to(instance.resolve()) or not path.is_file() or sha(path)!=identity:raise WorkError('模板输入或计划已改变，请重新检查','template_mismatch')
    if sha(instance/'project/preview.json')!=saved['preview_sha256']:raise WorkError('预览已改变，请重新检查','template_mismatch')
    for i in range(len(saved['stills'])):preview_file(studio,draft['id'],plan_id,i)
    atomic_private(instance/'visual-review.json',{'approved':True,'issues':[],'preview_sha256':saved['preview_sha256'],
        'scope':'user-confirmed actual preview and manual component configuration; continuous output review pending','listened':False})
    return request
