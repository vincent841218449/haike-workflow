import {useRef, useState} from 'react';
import {CheckCircle2, Film, ImagePlus, LoaderCircle, Plus, Trash2} from 'lucide-react';
import {Notice} from './ui.jsx';
import {AI_DEFAULTS} from './AiMaterials.jsx';
import {materialSelection} from './avatar-creation-model.js';

export function AvatarMaterials({value, onChange, onFiles, busy, uploading}) {
  const file = useRef(null), [error, setError] = useState(''), [dragging, setDragging] = useState(false);
  const ai = {...AI_DEFAULTS, ...value};
  const materials = ai.materials;
  const change = next => {setError('');onChange({...ai, enabled: true, materials: next});};
  async function choose(files) {
    if (busy) return;
    setError('');
    try {
      const selected = materialSelection(files, materials.length);
      if (selected.length) await onFiles(selected);
    } catch (err) {setError(err.message);}
  }
  return <div className="avatar-materials">
    <div className={`creation-material-drop ${dragging?'dragging':''}`} onDragOver={e=>{e.preventDefault();if(!busy&&materials.length<4)setDragging(true);}} onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget))setDragging(false);}} onDrop={e=>{e.preventDefault();setDragging(false);choose(e.dataTransfer.files);}}>
      <button type="button" className="material-drop-button" disabled={busy||materials.length>=4} onClick={()=>file.current.click()}><span className="material-drop-icon">{uploading ? <LoaderCircle size={24} className="spinner"/> : <ImagePlus size={25}/>}</span><span><strong>{uploading ? `正在上传 ${uploading.completed + 1} / ${uploading.total}` : materials.length>=4 ? '素材已添加完整' : '点击上传，或把素材拖到这里'}</strong><small>{uploading ? uploading.name : '图片或视频均可 · 可一次选择多份 · 每份最多80 MB'}</small></span><span className="material-drop-action"><Plus size={15}/>{materials.length} / 4</span></button>
    </div>
    {materials.length > 0 && <>
      <div className="creation-material-grid">{materials.map(m=><article className="creation-material-card" key={m.id}>
        <div className="creation-material-thumb">{m.kind==='image' ? <img src={m.url} alt="已上传的图片素材"/> : m.url ? <video src={m.url} preload="metadata" muted playsInline aria-label="已上传的视频素材"/> : <Film size={24}/>}<span>{m.kind==='image'?'图片':'视频'}</span></div>
        <div className="creation-material-caption"><strong title={m.name}>{m.name}</strong><small><CheckCircle2 size={11}/>已保存</small></div>
        <button type="button" className="icon-button material-remove" disabled={busy} aria-label={`移除素材${m.name}`} onClick={()=>change(materials.filter(x=>x.id!==m.id))}><Trash2 size={15}/></button>
      </article>)}</div>
      <label className="checkbox-row material-consent"><input type="checkbox" disabled={busy} checked={materials.every(m=>m.rights_confirmed)} onChange={e=>change(materials.map(m=>({...m, rights_confirmed:e.target.checked})))}/>我有权使用以上素材，并同意用于 AI 分析和视频制作</label>
    </>}
    {!materials.length && <p className="helper material-optional">没有素材也能制作，系统会根据文案自动安排画面。</p>}
    <input ref={file} hidden multiple type="file" accept=".jpg,.jpeg,.png,.mp4,.mov" aria-label="视频素材文件" onChange={e=>{choose(e.target.files);e.target.value='';}}/>
    <Notice message={error} error/>
  </div>;
}
