import { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, ChevronLeft, ChevronRight, CircleAlert, Clock3, Film, ListChecks, LoaderCircle, Pause, Play, Plus, RefreshCw, Square, Sparkles } from 'lucide-react';
import { api } from './studio-api.js';
import { Button, Dialog, EmptyState, Heading, Notice } from './ui.jsx';
import './tasks.css';

const TYPES = [['all', '全部任务'], ['graphic', '图文视频'], ['avatar', '数字人口播'], ['motion', '动效口播']];
const STATES = [['all', '全部'], ['active', '制作中'], ['queued', '排队中'], ['needs_action', '需处理'], ['failed', '失败'], ['completed', '已完成'], ['cancelled', '已取消']];
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
  const modalTrigger = useRef(null);
  useEffect(() => {
    const url = new URL(location.href);
    url.searchParams.set('status', view.status); url.searchParams.set('type', view.type);
    if (selected) url.searchParams.set('task', selected); else url.searchParams.delete('task');
    history.replaceState(null, '', url);
  }, [view, selected]);
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
  const inspect = (task, event) => { modalTrigger.current = event.currentTarget; setSelected(task.id); };
  const close = () => { setSelected(null); setPending(null); requestAnimationFrame(() => modalTrigger.current?.focus()); };
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
  return <main className="workspace creation-tasks">
    <Heading title="创作任务" helper="查看真实制作进度、处理异常，完成后到作品页审核。">
      <Button variant="primary" href="/avatar?new=1"><Plus size={17}/>新建创作</Button>
    </Heading>
    <section className="creation-overview surface" aria-label="制作概况">
      <div className="creation-overview-lead"><div className="creation-overview-icon"><ListChecks size={25}/></div><div><span className="creation-eyebrow">CREATION TASKS</span><h2>{counts ? `${counts.active} 个任务正在排队或制作` : '正在读取制作任务'}</h2><p>在本机持续制作，关闭页面后仍可回来查看进度。</p></div></div>
      <div className="creation-totals">{[['completed', '已完成'], ['failed', '失败'], ['needs_action', '需处理']].map(([key, label]) => <div key={key}><strong>{counts?.[key] ?? '—'}</strong><span>{label}</span></div>)}</div>
    </section>
    <div className="creation-toolbar"><div className="creation-types" role="group" aria-label="创作类型">{TYPES.map(([key, label]) => <button key={key} className={view.type === key ? 'active' : ''} aria-pressed={view.type === key} onClick={() => filter({ type: key })}>{label}</button>)}</div><button className="text-button" disabled={loading} onClick={() => setRefresh(v => v + 1)}><RefreshCw size={15}/>{loading ? '读取中…' : '刷新任务'}</button></div>
    <div className="creation-statuses" role="group" aria-label="任务状态">{STATES.map(([key, label]) => <button key={key} className={view.status === key ? 'active' : ''} aria-pressed={view.status === key} onClick={() => filter({ status: key })}>{label}{counts && <small>{counts[key]}</small>}</button>)}</div>
    <div className="creation-live"><span className={`creation-live-dot ${error ? 'offline' : ''}`}/>{error ? '连接暂时中断 · 保留上次结果' : '自动更新制作状态'}{updated && <span>更新于 {updated.toLocaleTimeString('zh-CN', { hour12: false })}</span>}</div>
    <Notice message={error} error/><Notice message={message}/>
    {loading && !data ? <div className="creation-loading" role="status"><LoaderCircle className="task-spin" size={22}/>正在读取创作任务…</div> : !tasks.length ? <EmptyState title={view.status === 'all' && view.type === 'all' ? '还没有创作任务' : '当前筛选下没有任务'} action={<Button href="/avatar">开始制作<ArrowRight size={16}/></Button>}>提交制作后，进度和结果会保存在这里。</EmptyState> : <section className="creation-list" aria-label="创作任务列表">{tasks.map(task => <article className={`creation-row surface state-${task.status}`} key={task.id}>
      <div className="creation-row-icon">{task.type === 'motion' ? <Sparkles size={21}/> : <Film size={21}/>}</div>
      <div className="creation-row-body"><span className={`creation-kind kind-${task.type}`}>{task.type_label}</span><h2><button onClick={event => inspect(task, event)}>{task.title}</button></h2><p className="creation-stage">{task.stage}</p><div className="creation-row-meta"><span>提交于 {time(task.created_at)}</span>{task.queue_position && <span>当前排在第 {task.queue_position} 位</span>}</div>{task.error && task.error !== task.stage && <p className="creation-row-error"><CircleAlert size={14}/>{task.error}</p>}</div>
      <div className="creation-row-state"><span className={`creation-state ${task.status}`}><StateIcon task={task}/>{task.status_label}</span><Progress task={task}/></div>
      <Button className="creation-details" onClick={event => inspect(task, event)} aria-label={`查看任务：${task.title}`}>查看详情<ChevronRight size={16}/></Button>
    </article>)}</section>}
    {pagination && pagination.total > pagination.limit && <nav className="creation-pagination" aria-label="任务分页"><Button disabled={!view.offset} onClick={() => setView(v => ({ ...v, offset: Math.max(0, v.offset - 30) }))}><ChevronLeft size={15}/>上一页</Button><span>第 {Math.floor(view.offset / 30) + 1} 页 · 共 {pagination.total} 个任务</span><Button disabled={!pagination.has_more} onClick={() => setView(v => ({ ...v, offset: v.offset + 30 }))}>下一页<ChevronRight size={15}/></Button></nav>}
    {selected && <Dialog title="创作任务详情" onClose={close} busy={busy}>
      {detail ? <><div className="creation-detail-header"><span className={`creation-state ${detail.task.status}`}><StateIcon task={detail.task}/>{detail.task.status_label}</span><span className="creation-kind">{detail.task.type_label}</span></div><h3 className="creation-detail-title">{detail.task.title}</h3><p className="creation-stage">{detail.task.stage}</p><Progress task={detail.task}/><Notice error message={detail.task.error}/><Notice message={detail.task.notice}/>
        <dl className="creation-detail-times"><div><dt>提交制作</dt><dd>{time(detail.task.created_at)}</dd></div><div><dt>开始制作</dt><dd>{time(detail.task.started_at)}</dd></div><div><dt>最近更新</dt><dd>{time(detail.task.updated_at)}</dd></div>{detail.task.queue_position && <div><dt>排队位置</dt><dd>第 {detail.task.queue_position} 位</dd></div>}</dl>
        <details className="creation-history"><summary>制作记录 <small>{detail.events.length} 条</small></summary><ol>{detail.events.map(e => <li key={e.id}><span>{e.stage || stateLabels[e.to] || '状态已保存'}</span><time>{time(e.at)}</time></li>)}</ol></details>
        <div className="creation-detail-actions">{detail.task.work_url && <Button variant="primary" href={detail.task.work_url}>查看与审核成片<ArrowRight size={16}/></Button>}<Button href={detail.task.edit_url}>返回制作项目<ArrowRight size={16}/></Button>{detail.task.actions.retry && <Button disabled={busy} onClick={() => act(detail.task, 'retry')}><Play size={16}/>继续原任务</Button>}{detail.task.actions.pause && <Button disabled={busy} onClick={() => act(detail.task, 'pause')}><Pause size={16}/>暂停排队</Button>}{detail.task.actions.resume && <Button disabled={busy} onClick={() => act(detail.task, 'resume')}><Play size={16}/>继续排队</Button>}{detail.task.actions.cancel && <Button disabled={busy} onClick={() => act(detail.task, 'cancel')}><Square size={14}/>取消后续制作</Button>}</div>
      </> : !detailError && <p role="status">正在读取原任务…</p>}
      <Notice message={detailError} error/>
    </Dialog>}
    {pending && <Dialog title="取消后续制作" busy={busy} onClose={() => setPending(null)}><p>将停止「{pending.title}」后续尚未执行的制作步骤。</p><p className="helper">已经提交的供应商调用会继续核对结果及费用，已完成的素材和成片会保留。</p><Notice message={detailError} error/><div className="modal-actions"><Button disabled={busy} onClick={() => setPending(null)}>返回</Button><Button variant="primary" loading={busy} onClick={cancel}>确认取消</Button></div></Dialog>}
  </main>;
}
