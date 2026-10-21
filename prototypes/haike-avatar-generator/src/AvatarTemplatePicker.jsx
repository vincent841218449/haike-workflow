import {useEffect,useState} from 'react';
import {ArrowLeft,Check,Layers,Play,Search} from 'lucide-react';
import {Button,Dialog,Field,Notice,EmptyState} from './ui.jsx';
import {TEMPLATES} from './generator-model.js';
import {api} from './studio-api.js';
import {filterTemplateCards,verticalTemplateCards} from './template-library.js';
import {TemplateCover,TemplateSample} from './TemplateSample.jsx';
import './template-picker.css';

export function AvatarTemplatePicker({templateId,motion,selectedName,onChoose,disabled=false}) {
  const [open,setOpen]=useState(false),[catalog,setCatalog]=useState(null),[error,setError]=useState('');
  const [preview,setPreview]=useState(null),[search,setSearch]=useState(''),[reload,setReload]=useState(0);
  useEffect(()=>{if(!open)return;let live=true;setCatalog(null);setError('');api('/api/studio/motion/catalog?layout=portrait').then(v=>live&&setCatalog(v)).catch(e=>live&&setError(e.message));return()=>{live=false;};},[open,reload]);
  const cards=filterTemplateCards(verticalTemplateCards(catalog,motion),search),loading=!catalog&&!error;
  const choose=t=>{if(!t.selectable)return;onChoose(t.choice);setOpen(false);setPreview(null);};
  const name=motion?selectedName||'正在读取所选模板…':TEMPLATES.find(t=>t.id===templateId)?.name||'选择竖屏模板';
  return <><div className="avatar-template-choice creation-template-entry"><div className="creation-template-identity"><span className="creation-template-icon"><Layers size={20}/></span><div><small>口播模板</small><strong>{name}</strong><p className="helper">9:16 · 切换模板保留文案、声音和素材</p></div></div><Button disabled={disabled} onClick={()=>{setPreview(null);setSearch('');setOpen(true);}}>选择模板<Layers size={16}/></Button></div>
    {open&&<Dialog className="avatar-template-dialog" title={preview?preview.name:'选择竖屏模板'} description={preview?'官方模板效果与本期内容分开展示。':'9:16 · 已验收版本可制作；新版能力逐项验证'} wide onClose={()=>setOpen(false)} footer={preview?<><Button onClick={()=>setPreview(null)}><ArrowLeft size={16}/>返回模板库</Button><Button variant="primary" disabled={!preview.selectable} onClick={()=>choose(preview)}>{preview.selectable?(preview.selected?'继续使用':'使用此模板'):'制作能力验证中'}{preview.selectable&&<Check size={16}/>}</Button></>:<><span className="helper">切换模板保留已填写内容与历史成片</span><Button onClick={()=>setOpen(false)}>返回制作</Button></>}>
      {preview?<TemplateSample key={preview.id} template={preview}/>:<>
        <div className="template-library-search"><Search size={18} aria-hidden="true"/><Field label="搜索模板"><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索官方名称或历史名称，如：科技控制台、04-A"/></Field><span role="status">{loading?'读取中…':`${cards.length} 款模板`}</span></div>
        {error&&<Notice message={error} error><Button onClick={()=>setReload(v=>v+1)}>重新读取</Button></Notice>}
        <div className="online-template-grid" aria-busy={loading}>{cards.map(t=><article key={t.id} className={`online-template-card ${t.selected?'selected':''} ${t.selectable?'':'validation-pending'}`}>
          <button className="online-template-cover" onClick={()=>setPreview(t)} aria-label={`预览${t.name}`}><TemplateCover key={t.id} template={t}/><span className="online-template-ratio">9:16</span><span className="online-template-play"><Play size={15}/>{t.demo?'播放样片':'查看模板'}</span>{t.selected&&<span className="online-template-selected"><Check size={13}/>当前使用</span>}</button>
          <div className="online-template-copy"><span className="template-source-label">{t.sourceLabel}</span><strong>{t.name}</strong><p>{t.description}</p><Button aria-label={`${t.selectable?'使用模板':'验证中'}：${t.name}`} disabled={!t.selectable} variant={t.selected?'secondary':'primary'} onClick={()=>choose(t)}>{t.selectable?(t.selected?'继续使用':'使用模板'):'制作能力验证中'}{t.selected&&<Check size={14}/>}</Button></div>
        </article>)}</div>
        {!loading&&!error&&!cards.length&&<EmptyState title="没有找到匹配模板" action={<Button onClick={()=>setSearch('')}>清除搜索</Button>}>换个官方名称或历史名称试试。</EmptyState>}
        {loading&&<p className="helper" role="status">正在读取模板版本与实际接入状态…</p>}
        <p className="helper template-library-note">只有完成本地制作验收的版本才开放选择。原生组、组件、素材槽与字幕按各自合同验证；历史工程继续绑定原包。</p>
      </>}
    </Dialog>}
  </>;
}
