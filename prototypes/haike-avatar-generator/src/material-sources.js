export const MATERIAL_SEARCH_SCHEMA='haike-material-search/1';
export function selectedSources(ai={}) {
  return ai.material_search?.providers || [];
}
export function changeSource(ai={},provider,enabled) {
  const providers=selectedSources(ai).filter(p=>p!==provider);
  if(enabled)providers.push(provider);
  if(!providers.length) {
    const {material_search,...ownOnly}=ai;
    return {...ownOnly,enabled:true,allow_images:false,skip_douyin:true};
  }
  return {...ai,enabled:true,allow_images:false,skip_douyin:!providers.includes('douyin'),
    material_search:{schema:MATERIAL_SEARCH_SCHEMA,providers,max_scenes:ai.material_search?.max_scenes||4}};
}
