import {useRef, useState} from 'react';
import {ArrowRight, Check, ImagePlus, ListChecks, LoaderCircle, Mic2, Play, RefreshCw, Upload, X} from 'lucide-react';
import {Button} from './ui.jsx';
import {SpeechRateControl} from './SpeechRateControl.jsx';

export function CreationStep({number, title, helper, children, action, className='', field, ready, optional=false, error}) {
  return <section id={`creation-${field}`} data-avatar-field={field} className={`input-step creation-step ${ready ? 'is-ready' : ''} ${error ? 'has-error' : ''} ${className}`} aria-labelledby={`step-${number}`} aria-describedby={error?`error-${field}`:undefined} tabIndex={-1}>
    <header className="creation-step-heading"><span className="step-number" aria-hidden="true">{ready ? <Check size={14}/> : number}</span><div className="creation-step-copy"><h2 id={`step-${number}`}>{title}<span className={`creation-field-tag ${ready?'ready':''}`}>{ready ? '已就绪' : optional ? '可选' : '必填'}</span></h2><p className="helper">{helper}</p></div>{action}</header>
    <div className="creation-step-content">{children}</div>
    {error && <p className="creation-field-error" id={`error-${field}`} role="alert">{error}</p>}
  </section>;
}

export function PreparationStrip({state}) {
  const links=[...state.fields,...state.missing.filter(v=>v.id==='materials')];
  return <nav className="creation-preparation" aria-label="制作准备"><div><ListChecks size={17}/><strong role="status">{state.message}</strong></div><div className="preparation-links">{links.map(field => <a key={field.id} href={`#creation-${field.id}`} className={field.ready ? 'ready' : ''}>{field.ready && <Check size={12}/>} {field.label}</a>)}</div></nav>;
}

export function AvatarVoiceField({voice, loading, ready, error, fallback, onChooseFallback, onChoose, onAudition, rate=1, onRateChange}) {
  const previewOnly = voice?.production_ready === false;
  return <div className="creation-voice-field">
    <div className="creation-voice-identity"><span className="voice-mark"><Mic2 size={22}/></span><div><strong>{loading ? '正在读取音色…' : voice?.name || '选择配音音色'}</strong><small>{previewOnly ? '官方示例 · 当前仅支持试听' : voice ? !ready ? '当前配音连接尚未就绪' : voice.scope === 'personal' ? '个人音色 · 可用于制作' : '当前可用配音' : '选好声音后，系统自动生成口播'}</small></div>{voice && <span className={`creation-voice-badge ${previewOnly||!ready?'preview':''}`}>{previewOnly ? '仅试听' : !ready ? '待连接' : '已选择'}</span>}</div>
    <div className="creation-voice-actions"><Button disabled={!voice || voice.preview_ready === false || loading} onClick={onAudition}><Play size={15}/>试听</Button><Button disabled={loading} onClick={onChoose}>{voice ? '更换音色' : '选择音色'}<ArrowRight size={15}/></Button></div>
    {error ? <p className="helper creation-voice-warning" role="alert">{error}</p> : previewOnly ? <p className="helper creation-voice-warning">这款音色的制作服务尚未接通，选择已保留。{fallback && <button type="button" onClick={onChooseFallback}>使用当前可用配音</button>}</p> : <p className="helper creation-voice-help">{voice?.production_hint || (voice?.preview_ready === false ? '当前音色暂不支持单独试听；也可在更多设置中使用已有录音。' : '可以先试听，再选一个适合这条视频的声音。')}</p>}
    <SpeechRateControl value={rate} onChange={onRateChange}/>
  </div>;
}

export function AvatarPortraitField({value, url, onFile, onRemove, busy, invalid}) {
  const file = useRef(null), [dragging, setDragging] = useState(false);
  const choose = selected => {if (selected && !busy) onFile(selected);};
  return <div className={`creation-portrait ${value ? 'has-portrait' : ''} ${dragging ? 'dragging' : ''}`} onDragOver={e=>{e.preventDefault();if(!busy)setDragging(true);}} onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget))setDragging(false);}} onDrop={e=>{e.preventDefault();setDragging(false);choose(e.dataTransfer.files[0]);}}>
    {value ? <><img src={url} alt="已选择的数字人图片"/><div className="creation-portrait-copy"><strong title={value.name}>{value.name}</strong><small>人物照片已就绪</small><Button disabled={busy} onClick={()=>file.current.click()}><RefreshCw size={14}/>更换图片</Button></div><button type="button" className="icon-button portrait-remove" disabled={busy} aria-label="移除人物图片" onClick={onRemove}><X size={15}/></button></> : <button type="button" className="portrait-drop-target" disabled={busy} aria-invalid={invalid || undefined} aria-describedby="portrait-upload-hint" onClick={()=>file.current.click()}><span><ImagePlus size={25}/></span><strong>点击上传，或拖入人物照片</strong><small id="portrait-upload-hint">JPG / PNG · 10 MB以内<br/>清晰正脸，至少256 × 256像素</small><span className="portrait-upload-cta"><Upload size={14}/>上传图片</span></button>}
    <input hidden ref={file} type="file" accept="image/jpeg,image/png" aria-label="人物图片文件" onChange={e=>{choose(e.target.files?.[0]);e.target.value='';}}/>
  </div>;
}

export function SubmissionStatus({phase, uncertain}) {
  if (!phase && !uncertain) return null;
  return <div className={`creation-submit-status ${uncertain?'uncertain':''}`} role="status" aria-live="polite">{uncertain ? <RefreshCw size={18}/> : <LoaderCircle size={18} className="spinner"/>}<div><strong>{uncertain ? '正在等待原提交的确切结果' : phase}</strong><p>{uncertain ? '文案和素材已经保存。恢复原提交会继续核对同一任务。' : '系统会自动安排声音、画面和字幕，提交成功后进入创作任务。'}</p></div></div>;
}
