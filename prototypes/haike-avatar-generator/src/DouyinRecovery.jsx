import {useState} from 'react';
import {api} from './studio-api.js';
import {Button,Notice} from './ui.jsx';
import {douyinRecoveryNeeded} from './douyin-selection-model.js';

export function DouyinRecovery({job,onJob}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  if(!douyinRecoveryNeeded(job))return null;
  async function task(fn){setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="douyin-recovery"><p className="helper">AI自动分析抖音素材并安排合适的画面，已生成的配音和字幕保留。</p><div className="action-buttons">
    {/登录|网络/.test(job.stage)&&<><Button disabled={busy} onClick={()=>task(async()=>{await api('/api/studio/ai/douyin/login',{confirmed:true});setNotice('已打开项目专用抖音窗口，请在该窗口自行登录，再点击“我已登录并继续”。');})}>打开抖音登录窗口</Button><Button disabled={busy} onClick={()=>task(async()=>{await api('/api/studio/ai/douyin/login-confirmed',{confirmed:true});onJob(await api(`/api/production-queue/jobs/${job.job_id}/retry`,{}));})}>我已登录并继续</Button></>}
    <Button variant="primary" disabled={busy} onClick={()=>task(async()=>{onJob(await api(`/api/production-queue/jobs/${job.job_id}/retry`,{}));})}>继续自动选材</Button>
    <Button disabled={busy} onClick={()=>task(async()=>{onJob(await api(`/api/studio/ai/jobs/${job.job_id}/skip-douyin`,{confirmed:true}));})}>跳过抖音，使用免费素材</Button>
  </div><Notice message={error} error/><Notice message={notice}/></div>;
}
