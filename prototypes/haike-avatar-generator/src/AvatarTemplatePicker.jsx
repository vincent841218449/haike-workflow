import {useEffect,useState} from 'react';
import {ArrowLeft, Check, Layers, Play, Search} from 'lucide-react';
import {Button,Dialog,Field,Notice,EmptyState} from './ui.jsx';
import {TEMPLATES} from './generator-model.js';
import {api} from './studio-api.js';
import './template-picker.css';
import {filterTemplateCards,nativeTemplateCards} from './template-library.js';
import {TemplateCover,TemplateSample} from './TemplateSample.jsx';

export function AvatarTemplatePicker({templateId,motion,selectedName,onChoose,disabled=false}) {
  const [open,setOpen]=useState(false),[catalog,setCatalog]=useState(null),[layout,setLayout]=useState(motion?.layout||'portrait'),[error,setError]=useState('');
  const [tab,setTab]=useState('basic'),[preview,setPreview]=useState(null),[search,setSearch]=useState(''),[reload,setReload]=useState(0);
  useEffect(()=>{if(!open||tab!=='motion')return;let live=true;setCatalog(null);setError('');api(`/api/studio/motion/catalog?layout=${layout}`).then(v=>live&&setCatalog(v)).catch(e=>live&&setError(e.message));return()=>{live=false;};},[open,tab,layout,reload]);
  const selected=TEMPLATES.find(t=>t.id===templateId);
  const choose=t=>{onChoose(t.choice);setOpen(false);setPreview(null);};
  const basic=TEMPLATES.map(t=>({...t,image:`${import.meta.env.BASE_URL}assets/${t.poster}`,demo:t.sample?`${import.meta.env.BASE_URL}assets/${t.sample}`:null,choice:{templateId:t.id,motion:null,templateRef:null},selected:!motion&&t.id===templateId}));
  const styles=nativeTemplateCards(catalog,layout,motion);
  const cards=filterTemplateCards(tab==='basic'?basic:styles,search);
  const loading=tab==='motion'&&!catalog&&!error;
  return <><div className="avatar-template-choice creation-template-entry"><div className="creation-template-identity"><span className="creation-template-icon"><Layers size={20}/></span><div><small>口播模板</small><strong>{motion?selectedName||'正在读取所选模板…':selected?.name}</strong><p className="helper">{motion?(motion.layout==='portrait'?'9:16':'16:9'):selected?.ratio} · 切换模板保留文案、声音和素材</p></div></div><Button disabled={disabled} onClick={()=>{setPreview(null);setSearch('');setLayout(motion?.layout||'portrait');setOpen(true);setTab(motion?'motion':'basic');}}>选择模板<Layers size={16}/></Button></div>
    {open&&<Dialog className="avatar-template-dialog" title={preview?preview.name:'选择口播模板'} description={preview?'先看效果，再选择适合这条内容的版式。':'选一个喜欢的效果，系统自动编排，无需逐镜编辑。'} wide onClose={()=>setOpen(false)} footer={preview?<><Button onClick={()=>setPreview(null)}><ArrowLeft size={16}/>返回模板库</Button><Button variant="primary" onClick={()=>choose(preview)}>{preview.selected?'继续使用':'使用此模板'}<Check size={16}/></Button></>:<><span className="helper">切换模板会保留已填写内容</span><Button onClick={()=>setOpen(false)}>返回制作</Button></>}>
      {preview?<TemplateSample key={preview.id} template={preview}/>:<>
        <div className="template-library-toolbar"><div className="sound-tabs" role="group" aria-label="模板分类"><button className={tab==='basic'?'active':''} aria-pressed={tab==='basic'} onClick={()=>{setTab('basic');setSearch('');}}>基础口播 · 3款</button><button className={tab==='motion'?'active':''} aria-pressed={tab==='motion'} onClick={()=>{setTab('motion');setSearch('');}}>ADu 动效模板</button></div>{tab==='motion'&&<Field label="画幅"><select value={layout} onChange={e=>setLayout(e.target.value)}><option value="portrait">竖屏 9:16</option><option value="landscape">横屏 16:9</option></select></Field>}</div>
        <div className="template-library-search"><Search size={17} aria-hidden="true"/><Field label="搜索模板"><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索名称或效果，如：仪器台、分屏、纸面"/></Field><span role="status">{loading?'读取中…':`${cards.length} 款可选`}</span></div>
        {tab==='motion'&&error&&<Notice message={error} error><Button onClick={()=>setReload(v=>v+1)}>重新读取模板</Button></Notice>}
        <div className="online-template-grid" aria-busy={loading}>{cards.map(t=><article key={t.id} className={`online-template-card ${t.selected?'selected':''}`}>
          <button className="online-template-cover" onClick={()=>setPreview(t)} aria-label={`预览${t.name}`}><TemplateCover key={t.id} template={t}/><span className="online-template-ratio">{t.ratio}</span><span className="online-template-play"><Play size={15}/>{t.demo?'播放样片':'预览版式'}</span>{t.selected&&<span className="online-template-selected"><Check size={13}/>当前使用</span>}</button>
          <div className="online-template-copy">{t.sourceLabel&&<span className="template-source-label">{t.sourceLabel}</span>}<strong>{t.name}</strong><p>{t.description}</p><Button aria-label={`${t.selected?'继续使用':'使用模板'}：${t.name}`} variant={t.selected?'secondary':'primary'} onClick={()=>choose(t)}>{t.selected?'继续使用':'使用模板'}{t.selected&&<Check size={14}/>}</Button></div>
        </article>)}</div>
        {!loading&&!error&&!cards.length&&<EmptyState title="没有找到匹配模板" action={<Button onClick={()=>setSearch('')}>清除搜索</Button>}>换个名称试试，或切换模板分类和画幅。</EmptyState>}
        {tab==='motion'&&(catalog?.pending_packages||[]).map(p=><div className="notice" key={p.id}><strong>{p.name}</strong><p>{p.reason}</p><a href={p.url} target="_blank" rel="noreferrer">前往官方模板页</a></div>)}
        {loading&&<p className="helper" role="status">正在读取本机可用模板…</p>}
        <p className="helper template-library-note">{tab==='motion'?'使用作者的原生引擎制作；样片中的动作会按本期原文与素材自动安排，不兼容时保留输入，不会自动换风格。':'固定版式，适合直接开始口播制作。'} 无需逐镜审核。</p>
      </>}
    </Dialog>}
  </>;
}
