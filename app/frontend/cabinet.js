"use strict";
let csrf = '', state = null, busy = false, abandoningId = null;
const status = document.querySelector('#cabinet-status');
const dialog = document.querySelector('#abandon-dialog');
const defaults = ['#b51f24','#2355aa','#257346','#50545b','#dec78a'];

async function api(path, method='GET', body) {
  const response = await fetch(path,{method,cache:'no-store',headers:body ? {'Content-Type':'application/json','X-CSRF-Token':csrf} : {},body:body ? JSON.stringify(body) : undefined});
  if (response.status === 401) { location.href='/index.php'; throw new Error('Требуется вход'); }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
function lineList(element, items) {
  element.replaceChildren();
  for (const [term,value] of items) {
    const line=document.createElement('div'), dt=document.createElement('dt'), dd=document.createElement('dd');
    dt.textContent=term; dd.textContent=value ?? 'Нет данных'; line.append(dt,dd); element.append(line);
  }
}
function statCard(title, entries) {
  const card=document.createElement('section'), heading=document.createElement('h3'), dl=document.createElement('dl');
  heading.textContent=title; lineList(dl,entries); card.append(heading,dl); return card;
}
function hexValue(row,field) {
  if (field==='Состав ландшафта' && row[field]) {
    try {
      const parts=JSON.parse(row[field]);
      if (Array.isArray(parts)) return parts.map(part=>`${part.name}: ${part.percent}%`).join(' / ');
    } catch {}
    return 'Нет данных';
  }
  return row[field] === '' ? 'Нет данных' : row[field] ?? 'Нет данных';
}
function selectTab(name,focus=false) {
  const buttons=[...document.querySelectorAll('[role=tab]')];
  if (!buttons.some(button=>!button.hidden && button.id===`tab-${name}`)) name=state && !state.barony ? 'settings' : 'barony';
  buttons.forEach(button=>{
    const selected=button.id===`tab-${name}`;
    button.setAttribute('aria-selected',String(selected)); button.tabIndex=selected ? 0 : -1;
    document.getElementById(button.getAttribute('aria-controls')).hidden=!selected;
    if (selected && focus) button.focus();
  });
}
const tabs=[...document.querySelectorAll('[role=tab]')];
tabs.forEach(button=>{
  button.addEventListener('click',()=>{ location.hash=button.id.replace('tab-',''); selectTab(button.id.replace('tab-','')); });
  button.addEventListener('keydown',event=>{
    const visible=tabs.filter(tab=>!tab.hidden), index=visible.indexOf(button);
    let next;
    if (event.key==='ArrowRight') next=(index+1)%visible.length;
    if (event.key==='ArrowLeft') next=(index+visible.length-1)%visible.length;
    if (event.key==='Home') next=0;
    if (event.key==='End') next=visible.length-1;
    if (next!==undefined) { event.preventDefault(); location.hash=visible[next].id.replace('tab-',''); selectTab(visible[next].id.replace('tab-',''),true); }
  });
});
window.addEventListener('hashchange',()=>selectTab(location.hash.slice(1)));
selectTab(location.hash.slice(1));

function renderCabinet() {
  document.querySelector('#user-status').textContent=state.account.login;
  const account=document.querySelector('#account-form');
  account.elements.login.value=state.account.login; account.elements.email.value=state.account.email;
  const barony=state.barony;
  tabs.forEach(button=>button.hidden=!barony && button.id!=='tab-settings');
  document.querySelector('#barony-settings').hidden=!barony;
  if (!barony) history.replaceState(null,'','#settings');
  selectTab(location.hash.slice(1));
  document.querySelector('#barony-summary').hidden=!barony;
  document.querySelector('#barony-content').hidden=!barony;
  document.querySelector('#no-barony').hidden=Boolean(barony);
  if (!barony) return;
  document.querySelector('#barony-name-form').elements.name.value=barony.name;
  document.querySelector('#cabinet-name').textContent=barony.name;
  document.querySelector('#cabinet-title').textContent=barony.title;
  const currentCrest=state.crests.includes(barony.crest)
    ? barony.crest
    : barony.crest.replace(/\.png$/i,'.webp');
  document.querySelector('#cabinet-crest').src=`crests/${currentCrest}`;
  document.querySelector('#cabinet-cells').textContent=barony.hexes.map(row=>`Q${row.Q} R${row.R}`).join(' · ') || 'Нет принадлежащих вам гексов';
  const stats=barony.statistics;
  document.querySelector('#barony-totals').replaceChildren(statCard('Владение',[['Гексов',stats.hex_count],['Островных гексов',stats.islands],['Гексов с объектами',stats.objects]]));
  for (const [id,key] of [['category-stats','categories'],['landscape-stats','landscapes'],['resource-stats','resources']]) {
    const entries=Object.entries(stats[key]); lineList(document.getElementById(id),entries.length ? entries : [['Описание','Нет данных']]);
  }
  document.querySelector('#rating-stats').replaceChildren(...Object.entries(stats.ratings).map(([field,value])=>statCard(field,[['Среднее',value.mean===null ? null : `${value.mean} / ${value.maximum}`],['Диапазон',value.min===null ? null : `${value.min}–${value.max}`],['Известно гексов',value.known],['Нет данных',value.missing]])));
  document.querySelector('#barony-hexes').replaceChildren(...barony.hexes.map(row=>{
    const details=document.createElement('details'), summary=document.createElement('summary'), dl=document.createElement('dl');
    summary.textContent=`${row['Название'] || 'Гекс'} · Q${row.Q} R${row.R}`;
    lineList(dl,state.hex_fields.map(field=>[field,hexValue(row,field)]));
    details.append(summary,dl); return details;
  }));
  document.querySelector('#crest-color').value=barony.color;
  const list=document.querySelector('#crest-list'); list.replaceChildren();
  state.crests.forEach((crest,index)=>{
    const label=document.createElement('label'), input=document.createElement('input'), img=document.createElement('img');
    input.type='radio'; input.name='crest'; input.value=crest; input.required=true; input.checked=crest===currentCrest;
    img.src=`crests/${crest}`; img.alt=`Герб ${index+1}`; label.append(input,img); list.append(label);
    input.addEventListener('change',()=>document.querySelector('#crest-color').value=defaults[index % defaults.length]);
  });
  if (!list.querySelector('input:checked')) list.querySelector('input')?.click();
}
async function loadCabinet() { state=await api('/api/cabinet'); renderCabinet(); }
async function action(form,handler) {
  if (busy) return;
  busy=true; const button=form.querySelector('[type=submit]'); button.disabled=true; status.textContent='Сохранение…';
  try { await handler(); } catch(error) { status.textContent=error.message; }
  finally { busy=false; button.disabled=false; }
}
document.querySelector('#account-form').addEventListener('submit',event=>{
  event.preventDefault(); const form=event.currentTarget;
  action(form,async()=>{
    const data=Object.fromEntries(new FormData(form)); data.expected={...state.account};
    const result=await api('/api/cabinet/account','PATCH',data); csrf=result.csrf; state.account=result.account;
    form.elements.current_password.value=''; form.elements.password.value=''; form.elements.password_confirm.value='';
    document.querySelector('#user-status').textContent=result.account.login;
    status.textContent='Аккаунт сохранён. Остальные сеансы входа завершены.';
  });
});
document.querySelector('#barony-name-form').addEventListener('submit',event=>{
  event.preventDefault(); const form=event.currentTarget;
  action(form,async()=>{
    await api('/api/cabinet/barony/name','PATCH',{barony_id:state.barony.id,name:form.elements.name.value,expected_name:state.barony.name});
    await loadCabinet(); status.textContent='Название баронии сохранено.';
  });
});
document.querySelector('#crest-form').addEventListener('submit',event=>{
  event.preventDefault(); const form=event.currentTarget;
  action(form,async()=>{
    await api('/api/cabinet/barony/crest','PATCH',{barony_id:state.barony.id,crest:form.querySelector('input[name=crest]:checked').value,color:document.querySelector('#crest-color').value});
    await loadCabinet(); status.textContent='Герб и цвет баронии сохранены.';
  });
});
document.querySelector('#refresh-cabinet').addEventListener('click',async()=>{
  if (busy) return;
  try { await loadCabinet(); status.textContent='Статистика обновлена.'; } catch(error) { status.textContent=error.message; }
});
function checkAbandon() {
  document.querySelector('#confirm-abandon').disabled=busy || document.querySelector('#abandon-confirmation').value!==state?.barony?.name || !document.querySelector('#abandon-confirmed').checked;
}
document.querySelector('#open-abandon').addEventListener('click',()=>{
  if (busy || !state.barony) return;
  abandoningId=state.barony.id;
  document.querySelector('#abandon-name').textContent=state.barony.name;
  document.querySelector('#abandon-form').reset(); document.querySelector('#abandon-status').textContent='';
  checkAbandon(); dialog.showModal(); document.querySelector('#abandon-confirmation').focus();
});
document.querySelector('#abandon-confirmation').addEventListener('input',checkAbandon);
document.querySelector('#abandon-confirmed').addEventListener('change',checkAbandon);
document.querySelector('#cancel-abandon').addEventListener('click',()=>{ if (!busy) dialog.close(); });
dialog.addEventListener('cancel',event=>{ if (busy) event.preventDefault(); });
document.querySelector('#abandon-form').addEventListener('submit',async event=>{
  event.preventDefault(); checkAbandon();
  if (document.querySelector('#confirm-abandon').disabled) return;
  busy=true; checkAbandon();
  try {
    const result=await api('/api/cabinet/barony','DELETE',{barony_id:abandoningId,confirmation:document.querySelector('#abandon-confirmation').value,confirmed:document.querySelector('#abandon-confirmed').checked});
    state.barony=null; renderCabinet(); dialog.close();
    status.textContent=`Вы отказались от баронии. Освобождено гексов: ${result.released_hexes}.`;
  } catch(error) { document.querySelector('#abandon-status').textContent=error.message; }
  finally { busy=false; checkAbandon(); }
});
document.querySelector('#logout').addEventListener('click',async()=>{
  if (busy) return;
  const response=await fetch('/logout',{method:'POST',body:new URLSearchParams({csrf})});
  if (response.ok) location.href='/index.php'; else status.textContent='Не удалось выйти. Обновите страницу и повторите попытку.';
});
(async()=>{
  try { const identity=await api('/api/me'); csrf=identity.csrf; await loadCabinet(); status.textContent=''; }
  catch(error) { status.textContent=error.message; }
})();
