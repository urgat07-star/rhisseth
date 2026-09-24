"use strict";
const fields = ['Название','Название территории','Категория','Остров','Доля суши, %','Тип местности','Состав ландшафта','Дополнительный объект','Проходимость','Защита','Плодородие','Опасность','Основной ресурс','Богатство ресурса','Глубина','Течение','Комментарий','Тип владельца','Владелец'];
const hiddenObjectFields = ['Уровень гекса','Постройка','Дорога','Водная переправа','Объекты гекса'];
const editorFields = [...fields,...hiddenObjectFields];
let rows = [], ownerOptions = {}, csrf = '', editing = null, busy = false;
const selected = new Set(), status = document.querySelector('#admin-status'), form = document.querySelector('#admin-form');
const key = row => `${row.Q},${row.R}`;
async function request(url, options = {}) {
  const response = await fetch(url,{cache:'no-store',...options});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
function mutation(url, payload, method='PUT', revision='') {
  return request(url,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...(revision?{'X-Hex-Revision':revision}:{})},body:JSON.stringify(payload)});
}
function render() {
  const head = document.createElement('tr');
  for (const label of ['Выбрать','Действие','Q','R','Статус данных',...fields,'Имя владельца']) {const th=document.createElement('th');th.textContent=label;head.append(th);}
  document.querySelector('#columns').replaceChildren(head);
  const body = document.querySelector('#rows'); body.replaceChildren();
  const query = document.querySelector('#search').value.toLocaleLowerCase();
  for (const row of rows.filter(r=>Object.values(r).join(' ').toLocaleLowerCase().includes(query))) {
    const tr=document.createElement('tr'), choice=document.createElement('td'), check=document.createElement('input');
    check.type='checkbox'; check.checked=selected.has(key(row)); check.setAttribute('aria-label',`Выбрать Q${row.Q} R${row.R}`);
    check.addEventListener('change',()=>check.checked?selected.add(key(row)):selected.delete(key(row)));choice.append(check);tr.append(choice);
    const action=document.createElement('td'), edit=document.createElement('button');edit.textContent='Редактировать';edit.disabled=busy;edit.addEventListener('click',()=>openEditor(row));action.append(edit);tr.append(action);
    for(const field of ['Q','R','Статус данных',...fields,'Имя владельца']) {const td=document.createElement('td');td.textContent=row[field]||'—';if(field==='Состав ландшафта'&&row[field]){try{td.textContent=JSON.parse(row[field]).map(p=>`${p.name} ${p.percent}%`).join(' / ');}catch{}}tr.append(td);}
    body.append(tr);
  }
}
function openEditor(row) {
  editing=row;form.replaceChildren();document.querySelector('#editor-title').textContent=`Гекс Q${row.Q} · R${row.R}`;
  for(const field of editorFields) {
    const label=document.createElement('label');label.textContent=field;
    let input;
    if (['Категория','Тип владельца','Владелец','Остров','Уровень гекса','Постройка','Дорога','Водная переправа'].includes(field)) input=document.createElement('select');
    else input=document.createElement(field==='Комментарий'?'textarea':'input');
    input.name=field;input.value=row[field]||'';input.maxLength=field==='Название'?200:4000;
    if(field==='Категория'||field==='Тип владельца'||field==='Остров') {
      const options=field==='Категория'?['Суша','Побережье','Море']:field==='Остров'?['Да','Нет']:['Ничейная территория','Игрок','Компьютерное владение'];
      const empty=new Option('Выберите','');input.append(empty);
      options.forEach(v=>input.append(new Option(v,v)));input.value=row[field]||'';
    }
    if(field==='Уровень гекса'){input.append(new Option('Выберите',''));['0 — нет','1 — Лагерь','2 — Поселение','3 — Деревня','4 — Форпост','5 — Крепость','6 — Город','7 — Столица'].forEach((v,i)=>input.append(new Option(v,String(i))));input.value=row[field]||'';}
    if(field==='Постройка'){['','- нет -','Лагерь','Поселение','Деревня','Форпост','Крепость','Город','Столица'].forEach(v=>input.append(new Option(v||'Выберите',v)));input.value=row[field]||'';}
    if(field==='Дорога'){['','Нет','Да'].forEach(v=>input.append(new Option(v||'Выберите',v)));input.value=row[field]||'';}
    if(field==='Водная переправа'){['','Нет','Мост','Переправа'].forEach(v=>input.append(new Option(v||'Выберите',v)));input.value=row[field]||'';}
    label.append(input);
    if(field==='Состав ландшафта') {
      input.type='hidden';
      const container=document.createElement('div');container.id='landscape-parts';
      const addPart=(part={name:'',percent:''})=>{
        const line=document.createElement('div');line.className='landscape-part';
        const name=document.createElement('input'),percent=document.createElement('input'),remove=document.createElement('button');
        name.value=part.name;name.placeholder='Лес, река, озеро…';name.maxLength=100;name.setAttribute('aria-label','Тип ландшафта');
        percent.type='number';percent.min='0.001';percent.max='100';percent.step='any';percent.value=part.percent;percent.setAttribute('aria-label','Доля ландшафта, %');
        remove.type='button';remove.textContent='Убрать';remove.addEventListener('click',()=>line.remove());line.append(name,percent,remove);container.append(line);
      };
      try{if(row[field])JSON.parse(row[field]).forEach(addPart);}catch{}
      const add=document.createElement('button');add.type='button';add.textContent='Добавить часть ландшафта';add.addEventListener('click',()=>addPart());
      const hint=document.createElement('small');hint.textContent='Доли в процентах, сумма 100%. Пустой состав сохраняет обычное описание.';
      label.append(container,add,hint);
    }
    form.append(label);
  }
  const refreshOwners=()=>{
    const type=form.elements.namedItem('Тип владельца').value, input=form.elements.namedItem('Владелец');
    input.replaceChildren(new Option('Нет владельца',''));
    const options=type==='Игрок'?ownerOptions.players:type==='Компьютерное владение'?ownerOptions.territories:[];
    options.forEach(o=>input.append(new Option(`${o.name}${o.kind?' · '+o.kind:''} (ID ${o.id})`,o.id)));
    input.value=row['Владелец']||'';
    input.disabled=type==='Ничейная территория'||type==='Компьютерное владение';
  };
  form.elements.namedItem('Тип владельца').addEventListener('change',refreshOwners);refreshOwners();
  if(row['Тип владельца']==='Компьютерное владение') form.elements.namedItem('Тип владельца').disabled=true;
  const save=document.createElement('button');save.type='submit';save.textContent='Подтвердить изменения';form.append(save);
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='Отмена';cancel.addEventListener('click',()=>document.querySelector('#editor').hidden=true);form.append(cancel);
  document.querySelector('#editor').hidden=false;document.querySelector('#editor').scrollIntoView({behavior:'smooth'});
}
async function reload() { [rows,ownerOptions]=await Promise.all([request('/api/hexes'),request('/api/admin/owners')]);render(); }
form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!editing)return;
  const target=editing,payload=Object.fromEntries(new FormData(form));
  const parts=Array.from(document.querySelectorAll('.landscape-part')).map(line=>({name:line.querySelectorAll('input')[0].value,percent:Number(line.querySelectorAll('input')[1].value)}));
  payload['Состав ландшафта']=parts.length?JSON.stringify(parts):'';
  if(!payload['Категория'])delete payload['Категория'];
  if(target['Тип владельца']==='Компьютерное владение') {delete payload['Тип владельца'];delete payload['Владелец'];}
  else payload['Владелец']=payload['Владелец']||'';
  if(!window.confirm(`Сохранить изменения гекса Q${target.Q} R${target.R}?`))return;
  busy=true;const button=form.querySelector('[type=submit]');button.disabled=true;
  try {await mutation(`/api/hexes/${target.Q}/${target.R}`,payload,'PUT',target._revision);await reload();document.querySelector('#editor').hidden=true;status.textContent='Изменения сохранены';}
  catch(error){status.textContent=error.message;}finally{busy=false;button.disabled=false;render();}
});
document.querySelector('#search').addEventListener('input',render);
document.querySelector('#group-name').addEventListener('click',async()=>{
  if(busy)return;if(!selected.size){status.textContent='Выберите гексы';return;}
  const name=window.prompt('Общее географическое название выбранных гексов:');if(name===null)return;
  if(name.length>200){status.textContent='Название: до 200 символов';return;}
  if(!window.confirm(`Назначить название «${name}» для ${selected.size} гексов?`))return;
  busy=true;let count=0;
  try {for(const coordinate of Array.from(selected)){const [q,r]=coordinate.split(',');await mutation(`/api/hexes/${q}/${r}`,{'Название':name},'PUT',rows.find(r=>key(r)===coordinate)?._revision);count++;}await reload();status.textContent=`Обновлено ${count} гексов`;}
  catch(error){status.textContent=`Обновлено ${count} гексов. ${error.message}`;await reload();}finally{busy=false;}
});
document.querySelector('#group-territory').addEventListener('click',()=>{document.querySelector('#territory-editor').hidden=false;document.querySelector('#territory-editor').scrollIntoView();});
document.querySelector('#cancel-territory').addEventListener('click',()=>document.querySelector('#territory-editor').hidden=true);
document.querySelector('#territory-form').elements.namedItem('id').addEventListener('change',event=>{
  const territory=ownerOptions.territories.find(t=>t.id===event.target.value);if(!territory)return;
  const target=document.querySelector('#territory-form');target.elements.namedItem('name').value=territory.name;target.elements.namedItem('rules').value=territory.rules;
  selected.clear();rows.filter(r=>r['Тип владельца']==='Компьютерное владение'&&r['Владелец']===territory.id).forEach(r=>selected.add(key(r)));render();
});
document.querySelector('#territory-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;const data=Object.fromEntries(new FormData(event.target));
  const payload={name:data.name,rules:data.rules,cells:Array.from(selected).map(c=>c.split(',').map(Number))};if(data.id)payload.id=Number(data.id);
  if(!window.confirm(`Назначить владение «${data.name}» для ${selected.size} гексов?`))return;
  busy=true;const button=event.target.querySelector('[type=submit]');button.disabled=true;
  try{const result=await mutation('/api/admin/territories',payload,'POST');await reload();status.textContent=`${result.kind} сохранено, ID ${result.id}`;document.querySelector('#territory-editor').hidden=true;}
  catch(error){status.textContent=error.message;}finally{busy=false;button.disabled=false;}
});
async function refreshAdminClock() {
  const state=await request('/api/game/clock');
  document.querySelector('#clock-current').textContent=`Сейчас: ${state.label}. Срок хода: ${new Date(state.ends_at).toLocaleString('ru-RU')}`;
  document.querySelector('#clock-form').elements.namedItem('year').value=state.year;
  document.querySelector('#clock-form').elements.namedItem('season').value=state.season;
}
async function loadRaidBalance() {
  const data=await request('/api/admin/game/raid-balance');
  const container=document.querySelector('#raid-balance-rows');container.replaceChildren();
  for(const row of data.rows){
    const form=document.createElement('form');
    const title=document.createElement('strong');title.textContent=`${row.building_level} — ${row.building_name}`;form.append(title);
    for(const [field,label] of [['gold','Золото'],['peasant_percent','Крестьяне, %'],['peasant_nominal','Номинал крестьян'],['morale_penalty','Потеря морали'],['cooldown_turns','Повтор через ходов']]){
      const wrapper=document.createElement('label');wrapper.textContent=label+' ';
      const input=document.createElement('input');input.name=field;input.type='number';input.min='0';input.max=field.includes('percent')||field.includes('morale')||field.includes('cooldown')?'100':'1000000';input.value=row[field];input.required=true;
      wrapper.append(input);form.append(wrapper);
    }
    const save=document.createElement('button');save.type='submit';save.textContent='Сохранить';form.append(save);
    form.addEventListener('submit',async event=>{
      event.preventDefault();const payload=Object.fromEntries([...new FormData(form)].map(([key,value])=>[key,Number(value)]));
      try{await mutation(`/api/admin/game/raid-balance/${row.building_level}`,payload,'PUT');document.querySelector('#raid-status').textContent=`Уровень ${row.building_level}: сохранено`;}
      catch(error){document.querySelector('#raid-status').textContent=error.message;}
    });
    container.append(form);
  }
}
async function loadRiverLinks(){
  const data=await request('/api/admin/game/river-links');const container=document.querySelector('#river-links');container.replaceChildren();
  for(const link of data.links){
    const row=document.createElement('p'),label=document.createElement('span'),remove=document.createElement('button');
    label.textContent=`Q${link.q1} R${link.r1} ↔ Q${link.q2} R${link.r2} `;remove.type='button';remove.textContent='Удалить';
    remove.addEventListener('click',async()=>{try{await mutation('/api/admin/game/river-links',link,'DELETE');await loadRiverLinks();}catch(error){document.querySelector('#river-status').textContent=error.message;}});
    row.append(label,remove);container.append(row);
  }
}
document.querySelector('#river-form').addEventListener('submit',async event=>{
  event.preventDefault();const payload=Object.fromEntries([...new FormData(event.currentTarget)].map(([key,value])=>[key,Number(value)]));
  try{await mutation('/api/admin/game/river-links',payload,'POST');await loadRiverLinks();document.querySelector('#river-status').textContent='Связь сохранена';}
  catch(error){document.querySelector('#river-status').textContent=error.message;}
});
async function loadBaronyResetPreview() {
  const data=await request('/api/admin/game/reset-preview');
  document.querySelector('#barony-reset').dataset.turn=data.turn;
  const missing=data.missing_start_zones.map(item=>`${item.name} (ID ${item.barony_id})`).join(', ');
  const conflicts=data.conflicts.map(item=>`Q${item.q} R${item.r}`).join(', ');
  document.querySelector('#barony-reset-preview').textContent=`Бароний: ${data.baronies}; сейчас гексов игроков: ${data.player_owned_hexes}; стартовых гексов записано: ${data.recorded_start_hexes}. ${missing?'Нет исходной зоны: '+missing+'. ':''}${conflicts?'Конфликты: '+conflicts+'. ':''}${data.unknown_owners.length?'Гексы игроков без баронии: '+data.unknown_owners.join(', ')+'.':''}`;
  document.querySelector('#barony-reset').disabled=!data.ready;
  const baronySelect=document.querySelector('#start-zone-form select');const previous=baronySelect.value;baronySelect.replaceChildren();
  for(const barony of data.barony_list)baronySelect.append(new Option(`${barony.name} (ID ${barony.id}; стартовых гексов: ${barony.start_count})`,barony.id));
  if(data.barony_list.some(item=>String(item.id)===previous))baronySelect.value=previous;
}
document.querySelector('#barony-reset').addEventListener('click',async()=>{
  const button=document.querySelector('#barony-reset');
  if(button.disabled)return;
  const confirmation=window.prompt('Полный тестовый сброс удалит армии, вернёт стартовые зоны, постройки, казну, ресурсы и время. Для подтверждения введите: СБРОСИТЬ ТЕСТ');
  if(confirmation!=='СБРОСИТЬ ТЕСТ')return;
  button.disabled=true;
  try{
    const result=await mutation('/api/admin/game/reset-baronies',{confirmation,expected_turn:Number(button.dataset.turn)},'POST');
    await Promise.all([reload(),refreshAdminClock(),loadBaronyResetPreview()]);
    document.querySelector('#barony-reset-status').textContent=`Сброшено бароний: ${result.baronies}; восстановлено стартовых гексов: ${result.restored_hexes}; удалено генералов: ${result.removed_generals}.`;
  }catch(error){document.querySelector('#barony-reset-status').textContent=error.message;await loadBaronyResetPreview();}
});
document.querySelector('#start-zone-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const baronyId=Number(event.target.elements.namedItem('barony_id').value);
  const cells=[...selected].map(item=>item.split(',').map(Number));
  if(cells.length<2||cells.length>3){document.querySelector('#barony-reset-status').textContent='Выберите 2–3 соседних гекса';return;}
  if(!window.confirm(`Сохранить выбранные ${cells.length} гекса как исходную зону баронии ${baronyId}?`))return;
  try{await mutation(`/api/admin/game/baronies/${baronyId}/start-zone`,{cells},'PUT');await loadBaronyResetPreview();document.querySelector('#barony-reset-status').textContent='Стартовая зона сохранена';}
  catch(error){document.querySelector('#barony-reset-status').textContent=error.message;}
});
document.querySelector('#clock-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.target;
  const year=Number(form.elements.namedItem('year').value), season=form.elements.namedItem('season').value;
  if(!window.confirm(`Установить ${year} год Эры Дракона, ${season}? Это сбросит голоса и срок текущего хода.`))return;
  try{await mutation('/api/admin/game/clock',{year,season},'POST');await refreshAdminClock();document.querySelector('#clock-status').textContent='Дата обновлена';}
  catch(error){document.querySelector('#clock-status').textContent=error.message;}
});
document.querySelector('#clock-reset').addEventListener('click',async()=>{
  if(!window.confirm('Сбросить время к 0 году Эры Дракона, Весне?'))return;
  try{await mutation('/api/admin/game/clock',{reset:true},'POST');await refreshAdminClock();document.querySelector('#clock-status').textContent='Время сброшено';}
  catch(error){document.querySelector('#clock-status').textContent=error.message;}
});
(async()=>{try{const identity=await request('/api/me');if(!identity.can_edit)throw new Error('Доступ только для администрации');csrf=identity.csrf;await reload();if(identity.role==='admin'){document.querySelector('#clock-admin').hidden=false;document.querySelector('#raid-admin').hidden=false;document.querySelector('#river-admin').hidden=false;document.querySelector('#barony-reset-admin').hidden=false;await refreshAdminClock();await loadRaidBalance();await loadRiverLinks();await loadBaronyResetPreview();}status.textContent=`Гексов на карте: ${rows.length}`;}catch(error){status.textContent=error.message;}})();
