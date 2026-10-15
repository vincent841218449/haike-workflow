import {useEffect, useRef, useState} from 'react';
import {ArrowRight, CheckCircle2, Download, Upload} from 'lucide-react';
import {api} from './studio-api.js';
import {Button, Notice} from './ui.jsx';

// Completed versions and their review gates live inside creation tasks.
export function TaskVideo({workId, initialVersion, onUpdate, onVersionChange}) {
  const [work,setWork]=useState(null), [version,setVersion]=useState('');
  const [error,setError]=useState(''), [message,setMessage]=useState(''), [busy,setBusy]=useState(false);
  const [fields,setFields]=useState({});
  const [engineering,setEngineering]=useState(false);
  const cover=useRef(null);
  useEffect(()=>{
    let live=true;setWork(null);setError('');setMessage('');
    api(`/api/works/${encodeURIComponent(workId)}`).then(w=>{
      if(!live)return;
      setWork(w);setVersion(w.versions.some(v=>v.version_id===initialVersion)?initialVersion:w.versions.at(-1)?.version_id||'');
      const d=w.materials.at(-1)?.data||{};
      setFields({...d,title:d.title||w.title,desc:d.desc||'',topics:d.topics||'',rights_confirmed:['owned','confirmed'].includes(d.source_rights_status)});
    }).catch(e=>live&&setError(e.message));
    return()=>{live=false;};
  },[workId,initialVersion]);
  async function confirm(){
    setBusy(true);setError('');
    try{const w=await api(`/api/works/${workId}/confirm`,{revision:work.revision,version_id:version,evidence:'用户在创作任务中选择此版本用于准备发布'});setWork(w);setMessage('已选择此版本用于准备发布。');onUpdate?.();}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function chooseCover(e){
    const f=e.target.files?.[0];e.target.value='';if(!f)return;
    setBusy(true);setError('');
    try{const r=await fetch(`/api/studio/works/${workId}/cover-upload`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});const v=await r.json();if(!r.ok)throw new Error(v.detail||'封面未能上传');setFields(old=>({...old,cover_path:v.path}));}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function save(e){
    e.preventDefault();setBusy(true);setError('');
    try{setWork(await api(`/api/studio/works/${workId}/materials`,{...fields,revision:work.revision}));setMessage('发布资料已保存，可以到日历选择账号与时间。');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const media=work?.versions.find(v=>v.version_id===version)?.media;
  const mediaUrl=`/api/works/${encodeURIComponent(workId)}/media?version=${encodeURIComponent(version)}`;
  const engineeringUrl=`/api/works/${encodeURIComponent(workId)}/engineering?version=${encodeURIComponent(version)}`;
  useEffect(()=>{let live=true;setEngineering(false);if(version)fetch(engineeringUrl,{method:'HEAD'}).then(r=>live&&setEngineering(r.ok)).catch(()=>{});return()=>{live=false;};},[engineeringUrl,version]);
  const approved=work?.final_version_id===version;
  return <section className="task-video" aria-label="成片播放与下载">
    <Notice message={error} error/><Notice message={message}/>
    {!work?!error&&<p role="status" className="helper">正在加载成片…</p>:<>
      <div className="task-video-toolbar"><label>观看版本<select aria-label="观看版本" value={version} disabled={busy} onChange={e=>{setVersion(e.target.value);setMessage('');onVersionChange?.(e.target.value);}}>{work.versions.map((v,i)=><option key={v.version_id} value={v.version_id}>版本 {i+1}{v.version_id===work.final_version_id?' · 已确认':i===work.versions.length-1?' · 最新版本':''}</option>)}</select></label><span>{media?.width} × {media?.height}{media?.duration?` · ${Number(media.duration).toFixed(1)}秒`:''}</span></div>
      <video key={version} controls preload="metadata" className="sample-video task-video-player" src={mediaUrl}/>
      <p className="helper">视频可以直接播放、下载。需要发布时，再选择用于发布的版本。</p>
      <div className="task-video-actions"><Button href={mediaUrl} download={`${work.title}.mp4`}><Download size={16}/>下载视频</Button>{engineering&&<Button href={engineeringUrl} download={`${work.title}-可编辑工程.zip`}><Download size={16}/>下载工程</Button>}{approved?<span className="task-reviewed"><CheckCircle2 size={17}/>已选为发布版本</span>:<Button loading={busy} disabled={!version} onClick={confirm}>使用此版本准备发布</Button>}<Button href={`/tasks?work=${encodeURIComponent(workId)}`} variant="text" className="task-video-permalink">成片链接<ArrowRight size={14}/></Button></div>
      {approved&&<details className="task-publish-details"><summary>发布资料与排期</summary><form className="studio-form" onSubmit={save}><label>发布标题<input required maxLength={80} value={fields.title||''} onChange={e=>setFields({...fields,title:e.target.value})}/></label><label>详情<textarea required maxLength={2000} rows={3} value={fields.desc||''} onChange={e=>setFields({...fields,desc:e.target.value})}/></label><label>话题<input value={fields.topics||''} onChange={e=>setFields({...fields,topics:e.target.value})}/></label><Button disabled={busy} onClick={()=>cover.current.click()}><Upload size={16}/>{fields.cover_path?'更换封面（已上传）':'上传发布封面（3:4）'}</Button><input hidden ref={cover} type="file" accept="image/png,image/jpeg" onChange={chooseCover}/><label className="checkbox-row"><input type="checkbox" checked={!!fields.rights_confirmed} onChange={e=>setFields({...fields,rights_confirmed:e.target.checked})}/>已确认人物、声音和素材的使用范围</label><div className="button-row"><Button type="submit" loading={busy}>保存发布资料</Button><Button href={`/calendar?work=${workId}`} variant="primary">安排日历<ArrowRight size={16}/></Button></div></form></details>}
    </>}
  </section>;
}
