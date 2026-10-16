const PURPOSES = {
  '01-A':'观点递进、案例与结论，文字和画面错峰出现',
  '01-B':'同一主题连续展开，保留物件变形和过渡动作',
  '01-C':'人物与内容前后分层，适合演示和重点讲解',
  '01-D':'图文分栏与跨栏交接，适合多段信息讲解',
  '01-E':'关键词与实体随口播回应，突出表达重点',
  '02-A':'纸面透视与平衡动作，适合有插图的概念讲解',
  '02-B':'资料聚合与卡片堆叠，适合分类、清单和交付展示',
  '03-A':'多屏、作品墙与重点放大，适合录屏和作品展示',
  '04-A':'深色控制台的固定编舞，适合有明确步骤或输入关系的内容',
  '05-A':'角色、物件与接力动作，适合有明确参与者的叙事',
  '06-A':'鲜色竖屏与大字强调，适合步骤、意图和要点讲解',
  'motiongit-612':'深色仪器台；按内容使用完整包中的原生编舞或官方组件',
};

export function nativeTemplateCards(catalog, layout, motion) {
  // A capability in the professional tool is not automatically a one-click template.
  // Quick TPL has no full-template reference or automatic semantic director.
  return (catalog?.styles || []).filter(s => s.supported &&
    ['adu-legacy','motiongit'].includes(s.template_ref?.runtime) && s.template_ref?.fingerprint).map(s => ({
    ...s, image:s.preview, demo:s.demo,
    description:PURPOSES[s.id] || s.scope,
    sourceLabel:s.template_ref.runtime==='motiongit'?`MotionGit · v${s.template_ref.version || s.selection?.split('@')[1]}`:'ADu · 原生镜头组',
    sourceDetail:s.template_ref.runtime==='motiongit'?s.scope:`${s.groups.length} 个原生镜头组 · ${s.selection}`,
    ratio:layout==='portrait'?'9:16':'16:9',
    choice:{templateId:'avatar-safe-circle-v1', motion:{style:s.id,layout}, templateRef:s.template_ref, templatePolicy:'strict'},
    selected:motion?.style===s.id&&motion?.layout===layout,
  }));
}

export function filterTemplateCards(cards, search) {
  const query=search.trim().toLocaleLowerCase();
  return cards.filter(t=>!query || [t.name,t.id,t.family,t.description,t.sourceLabel].join(' ').toLocaleLowerCase().includes(query))
    .sort((a,b)=>Number(b.selected)-Number(a.selected));
}
