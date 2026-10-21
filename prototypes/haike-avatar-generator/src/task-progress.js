export function taskProgress(task) {
  const p=task.progress||{};
  const steps=p.basis==='steps'&&Number.isFinite(p.completed)&&Number.isFinite(p.total)&&p.total>0;
  const percent=task.status==='completed'?100:!task.provider_wait&&!steps&&Number.isFinite(p.percent)?p.percent:null;
  return {percent,steps:steps?`${p.completed}/${p.total} 步`:null,
    label:percent!==null?`${percent}%`:task.provider_wait?'等待返回':steps?`${p.completed}/${p.total} 步`:task.status==='queued'?'等待开始':task.status==='running'?'处理中':'已停止'};
}
