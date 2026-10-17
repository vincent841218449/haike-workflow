import {useState} from 'react';
import {Notice} from './ui.jsx';

export function TemplateCover({template}) {
  const [imageFailed,setImageFailed]=useState(false),[videoFailed,setVideoFailed]=useState(false);
  if(template.external_preview_url&&!template.image&&!template.demo)return <span className="template-cover-unavailable">{template.name}<br/>点击查看官方样片</span>;
  if(template.image&&!imageFailed)return <img src={template.image} alt={`${template.name}版式参考`} loading="lazy" referrerPolicy="no-referrer" onError={()=>setImageFailed(true)}/>;
  if(template.demo&&!videoFailed)return <video src={`${template.demo}#t=0.1`} preload="metadata" muted playsInline aria-label={`${template.name}样片封面`} onError={()=>setVideoFailed(true)}/>;
  return <span className="template-cover-unavailable">封面暂不可用<br/>可查看模板说明后选择</span>;
}

export function TemplateSample({template}) {
  const [failed,setFailed]=useState(false),[loaded,setLoaded]=useState(false);
  return <div className="template-online-preview">
    {template.demo ? <video className="sample-video" controls autoPlay playsInline preload="metadata"
      src={template.demo} poster={template.image} aria-label={`${template.name}模板样片`}
      onLoadedData={()=>setLoaded(true)} onError={()=>setFailed(true)}/> : template.image?<img src={template.image} alt={`${template.name} · 布局参考`}/>:null}
    {template.external_preview_url&&!template.demo&&<><a className="button" href={template.external_preview_url} target="_blank" rel="noreferrer">在官网播放原版样片</a><p className="helper">作者官网限制跨站嵌入，原版样片在官方页面播放。</p></>}
    {template.demo&&!loaded&&!failed&&<p className="helper" role="status">正在载入样片，可先看封面或直接选择模板。</p>}
    <Notice error message={failed?'样片暂时无法播放。可以返回模板库重新打开，已填写的内容会保留。':''}/>
    <p className="helper">{template.demo||template.external_preview_url?'样片用于了解模板效果，制作时使用你的文案、人物与素材；按真实口播时长编排。':'这是布局示意，制作时替换为你的文案、人物与素材。'}</p>
    {template.sourceLabel&&<div className="template-source-detail"><strong>{template.sourceLabel}</strong><p>{template.description}</p><details><summary>模板来源与制作方式</summary><p>{template.sourceDetail}</p><p>锁定所选版本，由原生引擎编排和渲染；系统自动检查内容、素材和动作时长，不兼容时保留输入，不自动换成其他模板。</p></details></div>}
  </div>;
}
