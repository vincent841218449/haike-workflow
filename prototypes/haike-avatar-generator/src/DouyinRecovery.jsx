import {useState} from 'react';
import {api} from './studio-api.js';
import {Button,Dialog,Notice} from './ui.jsx';
import {toggleDouyinSelection,douyinSelectionRequest} from './douyin-selection-model.js';
import './douyin-recovery.css';

export function DouyinRecovery({job,onJob}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[items,setItems]=useState(null),[selected,setSelected]=useState([]),[rights,setRights]=useState(false);
  if(!['failed','awaiting_human'].includes(job?.status)||!/抖音/.test(job.stage))return null;
  async function task(fn){setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="douyin-recovery"><p className="helper">选择你有权使用的素材；AI会分析实际画面，决定是否采用及适合的分镜。已生成的配音和字幕保留。</p><div className="action-buttons"><Button variant="primary" disabled={busy} onClick={()=>task(async()=>{const r=await api(`/api/studio/ai/jobs/${job.job_id}/douyin-candidates`);setItems(r.items);setSelected([]);setRights(false);})}>选择素材，交给AI分析</Button>{/登录|网络/.test(job.stage)&&<><Button disabled={busy} onClick={()=>task(async()=>{await api('/api/studio/ai/douyin/login',{confirmed:true});setNotice('已打开项目专用抖音窗口，请在该窗口自行登录，再点击“我已登录并继续”。');})}>打开抖音登录窗口</Button><Button disabled={busy} onClick={()=>task(async()=>{await api('/api/studio/ai/douyin/login-confirmed',{confirmed:true});onJob(await api(`/api/production-queue/jobs/${job.job_id}/retry`,{}));})}>我已登录并继续</Button></>}<Button disabled={busy} onClick={()=>task(async()=>{onJob(await api(`/api/studio/ai/jobs/${job.job_id}/skip-douyin`,{confirmed:true}));})}>跳过抖音，使用免费素材</Button></div><Notice message={error} error/><Notice message={notice}/>
    {items&&<Dialog title="选择抖音素材，交给AI分析" description="可多选，最多10份。你确认使用权，AI判断内容是否适合并安排分镜；不会强制使用每一份素材。" busy={busy} onClose={()=>setItems(null)} footer={<><label className="checkbox-row douyin-rights-confirmation"><input type="checkbox" disabled={!selected.length||busy} checked={rights} onChange={e=>setRights(e.target.checked)}/>我有权使用所选素材，并同意AI分析及用于本次制作</label><span className="helper">已选 {selected.length} / 10 份</span><Button disabled={busy} onClick={()=>setItems(null)}>返回</Button><Button variant="primary" disabled={busy||!selected.length||!rights} onClick={()=>task(async()=>{onJob(await api(`/api/studio/ai/jobs/${job.job_id}/authorize-douyin`,douyinSelectionRequest(selected,rights)));setItems(null);})}>确认授权，AI选材并继续</Button></>}>
      {items.length?items.map(item=><article key={item.id} className="ai-material-item"><label className="checkbox-row"><input type="checkbox" name="douyin-candidate" value={item.id} checked={selected.includes(item.id)} onChange={()=>{try{setSelected(toggleDouyinSelection(selected,item.id));setRights(false);setError('');}catch(e){setError(e.message);}}}/>{item.title}</label><p className="helper">{item.author}</p><Button href={`https://www.douyin.com/video/${encodeURIComponent(item.id)}`} target="_blank" rel="noreferrer">查看原视频</Button></article>):<p className="helper">还没有候选素材。先完成登录并恢复搜索，也可以跳过抖音使用Pexels。</p>}
      <Notice message={error} error/>
    </Dialog>}
  </div>;
}
