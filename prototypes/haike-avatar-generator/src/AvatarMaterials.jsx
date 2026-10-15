import {useRef, useState} from 'react';
import {ImagePlus, Trash2} from 'lucide-react';
import {Button, Notice} from './ui.jsx';
import {AI_DEFAULTS} from './AiMaterials.jsx';

export function AvatarMaterials({value, onChange, onFile, busy}) {
  const file = useRef(null), [error, setError] = useState('');
  const ai = {...AI_DEFAULTS, ...value};
  const materials = ai.materials;
  const change = next => onChange({...ai, enabled: true, materials: next});
  return <div className="avatar-materials">
    <Button className="material-upload" disabled={busy || materials.length >= 4} onClick={()=>file.current.click()}><ImagePlus size={19}/>上传图片 / 视频<span>{materials.length}/4</span></Button>
    <p className="helper">可选，每份最多80 MB。系统根据文案自动安排素材和分镜。</p>
    {materials.length > 0 && <>
      <div className="compact-material-list">{materials.map(m=><div className="compact-material" key={m.id}>
        {m.kind==='image' ? <img src={m.url} alt=""/> : <ImagePlus size={20}/>}
        <span title={m.name}>{m.name}</span>
        <Button disabled={busy} aria-label={`移除素材${m.name}`} onClick={()=>change(materials.filter(x=>x.id!==m.id))}><Trash2 size={15}/></Button>
      </div>)}</div>
      <label className="checkbox-row"><input type="checkbox" disabled={busy} checked={materials.every(m=>m.rights_confirmed)} onChange={e=>change(materials.map(m=>({...m, rights_confirmed:e.target.checked})))}/>我有权使用以上素材，并同意用于 AI 分析和视频制作</label>
    </>}
    <input ref={file} hidden type="file" accept=".jpg,.jpeg,.png,.mp4,.mov" aria-label="视频素材文件" onChange={async e=>{
      const selected=e.target.files?.[0]; e.target.value=''; if(!selected)return;
      setError(''); try{await onFile(selected);}catch(err){setError(err.message);}
    }}/>
    <Notice message={error} error/>
  </div>;
}
