export function nativeTemplateCards(catalog, layout, motion) {
  return (catalog?.styles || []).filter(s => s.supported).map(s => ({
    ...s, image:s.preview, demo:s.demo,
    description:s.id.startsWith('motiongit-')?s.scope:`${s.groups.length}个原生镜头组 · ${s.status==='candidate'?'候选模板，本期自动检查':'按原生动作编排'}`,
    ratio:layout==='portrait'?'9:16':'16:9',
    choice:{templateId:'avatar-safe-circle-v1', motion:{style:s.id,layout}, templateRef:s.template_ref||null, templatePolicy:'strict'},
    selected:motion?.style===s.id&&motion?.layout===layout,
  }));
}
