import { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, ChevronLeft, ChevronRight, CircleAlert, Clock3, Film, ListChecks, LoaderCircle, Pause, Play, Plus, RefreshCw, Square, Sparkles } from 'lucide-react';
import { TaskVideo } from './TaskVideo.jsx';
import { api } from './studio-api.js';
import { Button, Dialog, EmptyState, Heading, Notice } from './ui.jsx';
import './tasks.css';

const TYPES = [['all', '全部任务'], ['graphic', '图文视频'], ['avatar', '数字人口播'], ['motion', '动效口播']];
const STATES = [['all', '全部'], ['active', '生产中'], ['queued', '排队中'], ['needs_action', '需处理'], ['failed', '失败'], ['completed', '已完成'], ['scheduled', '已排期'], ['cancelled', '已取消']];
const time = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—';
const stateLabels = { queued: '排队中', running: '制作中', paused: '已暂停', failed: '制作失败', completed: '制作完成', cancelled: '已取消', awaiting_human: '等待确认', ambiguous: '结果待核对' };
const initialView = () => {
  const q = new URLSearchParams(location.search);
  return { status: STATES.some(([s]) => s === q.get('status')) ? q.get('status') : 'all',
    type: TYPES.some(([s]) => s === q.get('type')) ? q.get('type') : 'all', offset: 0 };
};
function Progress({ task }) {
  const p = task.progress, known = p.percent !== null;
  return <div className="creation-progress">
    <div className={`creation-progress-track ${known ? '' : 'indeterminate'}`} role="progressbar" aria-label={`${task.title}制作进度`} aria-valuemin={0} aria-valuemax={100} {...(known ? { 'aria-valuenow': p.percent } : { 'aria-valuetext': task.stage })}>
      <span style={known ? { width: `${p.percent}%` } : undefined}/>
    </div>
    <span className="creation-progress-value">{known ? `${p.percent}%` : task.status === 'queued' ? '等待开始' : task.status === 'running' ? '处理中' : '已停止'}</span>
    {p.basis === 'steps' && <small>{p.completed}/{p.total} 步</small>}
  </div>;
}
function StateIcon({ task }) {
  const Icon = task.status === 'completed' ? CheckCircle2 : task.status === 'running' ? LoaderCircle : ['failed', 'ambiguous'].includes(task.status) ? CircleAlert : Clock3;
  return <Icon size={16} className={task.status === 'running' ? 'task-spin' : ''}/>;
}
export function CreationTasks() {
  const [view, setView] = useState(initialView), [data, setData] = useState(null), [error, setError] = useState('');
  const [loading, setLoading] = useState(true), [refresh, setRefresh] = useState(0), [updated, setUpdated] = useState(null);
  const [selected, setSelected] = useState(() => new URLSearchParams(location.search).get('task'));
  const [detail, setDetail] = useState(null), [detailError, setDetailError] = useState(''), [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [legacyWork, setLegacyWork] = useState(() => new URLSearchParams(location.search).get('work'));
  const modalTrigger = useRef(null);
  useEffect(() => {
    const url = new URL(location.href); url.pathname = '/tasks';
    if (legacyWork && !selected) url.searchParams.set('work', legacyWork); else url.searchParams.delete('work');
    url.searchParams.set('status', view.status); url.searchParams.set('type', view.type);
    if (selected) url.searchParams.set('task', selected); else url.searchParams.delete('task');
    history.replaceState(null, '', url);
  }, [view, selected, legacyWork]);
  useEffect(() => {
    let live = true, controller, inFlight = false;
    setLoading(true); setData(null);
    const load = async () => {
      if (inFlight || document.hidden) return;
      inFlight = true; controller = new AbortController();
      try {
        const params = new URLSearchParams({ ...view, limit: 30 });
        const response = await fetch(`/api/studio/tasks?${params}`, { signal: controller.signal });
        if (!response.ok) throw new Error('暂时无法读取创作任务，稍后会自动重试。');
        const next = await response.json();
        if (live) { setData(next); setError(''); setUpdated(new Date()); }
      } catch (e) { if (live && e.name !== 'AbortError') setError(e.message); }
      finally { inFlight = false; if (live) setLoading(false); }
    };
    load(); const timer = setInterval(load, 3000);
    window.addEventListener('focus', load); document.addEventListener('visibilitychange', load);
    return () => { live = false; clearInterval(timer); controller?.abort(); window.removeEventListener('focus', load); document.removeEventListener('visibilitychange', load); };
  }, [view, refresh]);
  useEffect(() => {
    if (!selected) { setDetail(null); setDetailError(''); return; }
    let live = true, inFlight = false;
    setDetail(null); setDetailError('');
    const load = async () => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try { const next = await api(`/api/studio/tasks/${encodeURIComponent(selected)}`); if (live) { setDetail(next); setDetailError(''); } }
      catch (e) { if (live) setDetailError(e.message); }
      finally { inFlight = false; }
    };
    load(); const timer = setInterval(load, 3000);
    return () => { live = false; clearInterval(timer); };
  }, [selected, refresh]);
  const filter = patch => setView(old => ({ ...old, ...patch, offset: 0 }));
  const inspect = (task, event) => { modalTrigger.current = event.currentTarget; setLegacyWork(null); setSelected(task.id); };
  const close = () => { setLegacyWork(null); setSelected(null); setPending(null); requestAnimationFrame(() => modalTrigger.current?.focus()); };
  async function act(task, action) {
    if (action === 'cancel') { setPending(task); return; }
    setBusy(true); setDetailError('');
    try {
      await api(`/api/production-queue/jobs/${encodeURIComponent(task.id)}/${action}`, {});
      setMessage(action === 'retry' ? '正在继续原任务，已完成的调用和素材会保留。' : action === 'pause' ? '排队任务已暂停。' : '任务已恢复排队。');
      setRefresh(v => v + 1);
    } catch (e) { setDetailError(e.message); }
    finally { setBusy(false); }
  }
  async function cancel() {
    setBusy(true); setDetailError('');
    try { await api(`/api/production-queue/jobs/${encodeURIComponent(pending.id)}/cancel`, {}); setPending(null); setMessage('已请求停止后续制作，实际结果将继续显示在原任务中。'); setRefresh(v => v + 1); }
    catch (e) { setDetailError(e.message); }
    finally { setBusy(false); }
  }
  const tasks = data?.tasks || [], counts = data?.counts, pagination = data?.pagination;
  const completion = counts?.all ? Math.round(counts.completed / counts.all * 100) : 0;
  const historyContent = detail && <><dl className="creation-detail-times"><div><dt>提交制作</dt><dd>{time(detail.task.created_at)}</dd></div><div><dt>开始制作</dt><dd>{time(detail.task.started_at)}</dd></div><div><dt>最近更新</dt><dd>{time(detail.task.updated_at)}</dd></div>{detail.task.queue_position && <div><dt>排队位置</dt><dd>第 {detail.task.queue_position} 位</dd></div>}</dl><ol className="creation-history-list">{detail.events.map(e => <li key={e.id}><span>{e.stage || stateLabels[e.to] || '状态已保存'}</span><time>{time(e.at)}</time></li>)}</ol></>;
  return <main className="workspace creation-tasks">
    <header className="tasks-welcome"><div><h2>你好，创作者</h2><p>AI 驱动创意，轻松打造短视频</p></div><div className="tasks-welcome-stats"><div><ListChecks size={21}/><span>创作总数<strong>{counts?.all ?? '—'} 条</strong></span></div><div><Sparkles size={21}/><span>制作中<strong>{counts?.active ?? '—'} 条</strong></span></div></div></header>
    <section className="tasks-content">
    <header className="tasks-page-heading"><div><span className="creation-eyebrow">CREATION TASKS</span><h1>创作任务</h1><p>查看视频制作进度、处理异常，预览和下载成片。</p></div><Button variant="primary" href="/avatar?new=1"><Plus size={17}/>新建创作</Button></header>
    <section className="creation-overview" aria-label="制作概况"><div className="creation-overview-icon"><Sparkles size={25}/></div><div className="creation-overview-copy"><span className="creation-eyebrow">VIDEO CREATION</span><h2>{counts ? `已完成 ${counts.completed} 条视频制作` : '正在读取制作任务'}</h2><p>{counts ? `共 ${counts.all} 个任务，排队 / 生产中 ${counts.active} 个，需处理 ${counts.needs_action} 个，失败 ${counts.failed} 个` : '提交后自动排队，制作进度会持续更新'}</p></div><div className="creation-overview-progress"><div role="progressbar" aria-label="任务完成比例" aria-valuemin={0} aria-valuemax={100} aria-valuenow={completion}><span style={{width:`${completion}%`}}/></div><strong>{counts ? `${counts.completed} / ${counts.all}` : '—'}</strong></div></section>
    <div className="creation-toolbar"><div className="creation-types" role="group" aria-label="创作类型">{TYPES.map(([key, label]) => <button key={key} className={view.type === key ? 'active' : ''} aria-pressed={view.type === key} onClick={() => filter({ type: key })}>{label}</button>)}</div><button className="text-button" disabled={loading} onClick={() => setRefresh(v => v + 1)}><RefreshCw size={15}/>{loading ? '读取中…' : '刷新'}</button></div>
    <div className="creation-statuses" role="group" aria-label="任务状态">{STATES.map(([key, label]) => <button key={key} className={view.status === key ? 'active' : ''} aria-pressed={view.status === key} onClick={() => filter({ status: key })}>{label}{counts && <small>{counts[key]}</small>}</button>)}</div>
    <div className="creation-live"><span className={`creation-live-dot ${error ? 'offline' : ''}`}/>{error ? '连接暂时中断 · 保留上次结果' : '自动更新制作状态'}{updated && <span>更新于 {updated.toLocaleTimeString('zh-CN', { hour12: false })}</span>}</div>
    <Notice message={error} error/><Notice message={message}/>
    {loading && !data ? <div className="creation-loading" role="status"><LoaderCircle className="task-spin" size={22}/>正在读取创作任务…</div> : !tasks.length ? <EmptyState title={view.status === 'all' && view.type === 'all' ? '还没有创作任务' : '当前筛选下没有任务'} action={<Button onClick={()=>filter({status:'all',type:'all'})}>查看全部任务</Button>}>提交制作后，进度和视频会保存在这里。<a href="/avatar?new=1">开始新创作<ArrowRight size={14}/></a></EmptyState> : <section className="creation-list" aria-label="创作任务列表">{tasks.map(task => <article className={`creation-row state-${task.status}`} key={task.id}>
      <div className="creation-row-body"><span className={`creation-kind kind-${task.type}`}>{task.type_label}</span><h2><button aria-label={`查看任务文案：${task.title}`} onClick={event => inspect(task, event)}>{task.excerpt || task.title}</button></h2><p className="creation-stage">{task.template_name ? `${task.template_name} · ` : ''}{task.stage}</p><div className="creation-row-meta"><span>提交制作：{time(task.created_at)}</span>{task.queue_position && <span>当前排在第 {task.queue_position} 位</span>}</div>{task.error && task.error !== task.stage && <p className="creation-row-error"><CircleAlert size={14}/>{task.error}</p>}</div>
      <span className="creation-ratio" aria-label={`画幅 ${task.ratio || '待确定'}`}>{task.ratio || '—'}</span>
      <span className={`creation-state ${task.status}`}><StateIcon task={task}/>{task.status_label}</span><Progress task={task}/>
      <button className="creation-details" onClick={event => inspect(task, event)} aria-label={`${task.work_id?'查看视频':'查看任务'}：${task.title}`}><ChevronRight size={21}/></button>
    </article>)}</section>}
    {pagination && pagination.total > pagination.limit && <nav className="creation-pagination" aria-label="任务分页"><Button disabled={!view.offset} onClick={() => setView(v => ({ ...v, offset: Math.max(0, v.offset - 30) }))}><ChevronLeft size={15}/>上一页</Button><span>第 {Math.floor(view.offset / 30) + 1} 页 · 共 {pagination.total} 个任务</span><Button disabled={!pagination.has_more} onClick={() => setView(v => ({ ...v, offset: v.offset + 30 }))}>下一页<ChevronRight size={15}/></Button></nav>}
    </section>
    {selected && <Dialog title={detail?.task.title || '创作任务详情'} wide={!!detail?.task.work_id} onClose={close} busy={busy}>
      {detail ? <><div className="creation-detail-header"><span className={`creation-state ${detail.task.status}`}><StateIcon task={detail.task}/>{detail.task.status_label}</span><span className="creation-kind">{detail.task.type_label}</span>{detail.task.ratio && <span className="creation-ratio">{detail.task.ratio}</span>}</div><p className="creation-stage">{detail.task.stage}</p>{!detail.task.work_id&&<Progress task={detail.task}/>}<Notice error message={detail.task.error}/><Notice message={detail.task.notice}/>
        {detail.task.work_id&&<TaskVideo key={detail.task.work_id} workId={detail.task.work_id} initialVersion={detail.task.version_id} onUpdate={()=>setRefresh(v=>v+1)}/>}
        <details className="creation-history" open={detail.task.work_id?undefined:true}><summary>制作详情与记录 <small>{detail.events.length} 条</small></summary>{historyContent}</details>
        <div className="creation-detail-actions"><Button href={detail.task.edit_url}>返回制作项目<ArrowRight size={16}/></Button>{detail.task.actions.retry && <Button disabled={busy} onClick={() => act(detail.task, 'retry')}><Play size={16}/>继续原任务</Button>}{detail.task.actions.pause && <Button disabled={busy} onClick={() => act(detail.task, 'pause')}><Pause size={16}/>暂停排队</Button>}{detail.task.actions.resume && <Button disabled={busy} onClick={() => act(detail.task, 'resume')}><Play size={16}/>继续排队</Button>}{detail.task.actions.cancel && <Button disabled={busy} onClick={() => act(detail.task, 'cancel')}><Square size={14}/>取消后续制作</Button>}</div>
      </> : !detailError && <p role="status">正在读取任务详情…</p>}<Notice message={detailError} error/>
      {pending&&<div className="creation-cancel-confirm"><p>停止后续制作？已提交的模型调用仍会保留，实际费用以调用明细为准。</p><Button disabled={busy} onClick={()=>setPending(null)}>继续等待</Button><Button variant="danger" disabled={busy} onClick={cancel}>确认停止后续制作</Button></div>}
    </Dialog>}
    {!selected&&legacyWork&&<Dialog title="查看视频" wide onClose={close}><TaskVideo workId={legacyWork} onUpdate={()=>setRefresh(v=>v+1)}/></Dialog>}
  </main>;
}
