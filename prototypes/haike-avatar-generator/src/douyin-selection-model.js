export function toggleDouyinSelection(selected, id) {
  if (selected.includes(id)) return selected.filter(value => value !== id);
  if (selected.length >= 10) throw new Error('一次最多选择10份素材，由AI分析是否采用。');
  return [...selected, id];
}

export function douyinSelectionRequest(selected, rights) {
  if (!rights || !Array.isArray(selected) || !selected.length || selected.length > 10 || new Set(selected).size !== selected.length) {
    throw new Error('请选择素材并确认拥有所选素材的使用权。');
  }
  return {video_ids:[...selected], rights_confirmed:true};
}
