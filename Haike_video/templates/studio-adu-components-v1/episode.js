/* Content/clock adapter. Scene, show, camCard, camAt and macWin are upstream ADu. */
window.END=EPISODE.plan.frames/60;
const escapeText=value=>String(value).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
EPISODE.plan.segments.forEach((segment,index)=>{
  const sc=new Scene(segment.start,segment.end,'#0a0a0a',{grid:'gridD',trans:index?'blur':null,td:.35});
  const presenter=camCard(sc.el,240,240,'',true);
  presenter._x=866;presenter._y=195;
  const label=mk(sc.el,`<div class="mono episode-label">海客创作 · ${String(index+1).padStart(2,'0')} / ${String(EPISODE.plan.segments.length).padStart(2,'0')}</div>`,76,102);
  const title=mk(sc.el,`<div class="episode-title">${escapeText(segment.heading)}</div>`,76,357);
  const line=mk(sc.el,'<div class="episode-line"></div>',76,555);
  const quotes=segment.emphasis;
  const panels=quotes.map((quote,i)=>{
    const h=quotes.length===1?570:332;
    const panel=macWin(sc.el,910,h,`<span>${String(i+1).padStart(2,'0')} · ${escapeText(segment.heading)}</span>`);
    panel._x=540;panel._y=quotes.length===1?940:820+(i%2)*395;
    panel._img.style.display='none';
    const body=panel.querySelector('.body');
    body.insertAdjacentHTML('beforeend',`<div class="semantic-body"><div class="semantic-note mono">${segment.layout==='compare'?'原文对照':'口播重点'}</div><div class="semantic-quote ${i===quotes.length-1?'emphasis-blue':''}" style="font-size:${quotes.length>2||quote.length>30?42:51}px">${escapeText(quote)}</div></div>`);
    return panel;
  });
  sc.update=t=>{
    const local=t-segment.start;
    camAt(presenter,t,{x:866,y:195,o:1,s:1});
    show(label,t,segment.start-.55,{d:.55});
    show(title,t,segment.start-.5,{k:'zoom',d:.55});
    show(line,t,segment.start-.4,{k:'left',dist:80,d:.55});
    panels.forEach((panel,i)=>{
      // Use the original source entrance/exit and spring, keeping speech on output time.
      const page=Math.floor(i/2),next=(page+1)*2;
      const begins=page?segment.emphasis_at[page*2]:segment.start+.05;
      const ends=next<quotes.length?segment.emphasis_at[next]:segment.end-.25;
      show(panel,t,begins+(i%2)*.12,{k:i%2?'right':'left',dist:105,d:.6,r:Math.sin(Math.min(local,3)+i)*.6,
        out:ends,od:.25,ox:i%2?65:-65,ob:8});
    });
  };
});
window.OVERLAY=t=>{
  const cue=EPISODE.plan.caption_cues.find(c=>c.startMs/1000<=t&&t<c.endMs/1000);
  document.getElementById('captions').textContent=cue?cue.text:'';
};
