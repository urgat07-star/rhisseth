"use strict";
/**
 * Личный кабинет: аккаунт, барония, армия, крестьяне и дипломатия.
 * После успешных мутаций соответствующее состояние перечитывается из API.
 */
let csrf = '', state = null, armyState = {generals:[],catalogue:[],general_catalogue:[]}, busy = false, abandoningId = null, selectedGeneralId = null;
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
/** Заполняет семантический список `<dl>` парами «название — значение». */
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
/** Переключает ARIA-вкладки и при клавиатурной навигации переносит фокус. */
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

/** Отображает данные аккаунта и баронии из загруженного состояния. */
function renderCabinet() {
  document.querySelector('#account-form input[name="login"]')?.setAttribute('minlength','2');
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
  const economy=state.economy||{gold:0,food:0,population:0,resources:{}};
  document.querySelector('#economy-gold').textContent=economy.gold;
  document.querySelector('#economy-food').textContent=economy.food;
  document.querySelector('#economy-population').textContent=economy.population;
  document.querySelector('#barony-totals').replaceChildren(statCard('Владение',[['Гексов',stats.hex_count],['Островных гексов',stats.islands],['Гексов с объектами',stats.objects]]));
  for (const [id,key] of [['category-stats','categories'],['landscape-stats','landscapes']]) {
    const entries=Object.entries(stats[key]); lineList(document.getElementById(id),entries.length ? entries : [['Описание','Нет данных']]);
  }
  lineList(document.querySelector('#resource-stats'),Object.entries(economy.resources).map(([name,value])=>[
    name,`На складе: ${value.quantity}${value.annual_growth>0?` · ⬆ +${value.annual_growth}/год`:''}`]));
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
async function loadArmy() { armyState=await api('/api/cabinet/army'); renderArmy(); }
async function loadDiplomacy() {
  const data=await api('/api/cabinet/diplomacy');
  const list=document.querySelector('#captive-generals');list.replaceChildren();
  if(!data.captives.length){const empty=document.createElement('p');empty.textContent='Пленных генералов нет.';list.append(empty);return;}
  for(const general of data.captives){
    const card=document.createElement('article');card.className='general-card';
    const crestName=general.mine?general.captor_crest:general.owner_crest;
    if(crestName&&/^[a-zA-Z0-9_-]+\.(?:webp|png)$/.test(crestName)){
      const crest=document.createElement('img');crest.src=`crests/${crestName}`;crest.alt=general.mine?'Герб пленившей баронии':'Герб баронии пленного генерала';card.append(crest);
    }
    const content=document.createElement('div');
    const title=document.createElement('h3');title.textContent=general.name;
    const detail=document.createElement('p');detail.textContent=`Уровень ${general.level}, опыт ${general.experience}, бонус атаки ${general.attack_bonus}, бонус защиты ${general.defense_bonus}. ${general.mine?'Пленён в '+general.captor_barony:'Из баронии '+general.owner_barony}.`;
    content.append(title,detail);card.append(content);
    if(general.mine){const button=document.createElement('button');button.type='button';button.textContent='Выкупить за 100 золотых';button.disabled=data.gold<100;
      button.addEventListener('click',async()=>{try{await api(`/api/cabinet/diplomacy/generals/${general.id}/ransom`,'POST',{});await Promise.all([loadDiplomacy(),loadArmy()]);status.textContent='Генерал выкуплен.';}catch(error){status.textContent=error.message;}});card.append(button);}
    list.append(card);
  }
}
async function loadPeasants(){
  const data=await api('/api/cabinet/peasants');
  document.querySelector('#peasant-reserve').textContent=`В столичном резерве: ${data.reserve}`;
  const list=document.querySelector('#peasant-hexes');list.replaceChildren();
  data.hexes.forEach(cell=>{const item=document.createElement('li');item.textContent=`Q${cell.q} R${cell.r}: ${cell.quantity}`;list.append(item);});
}
document.querySelector('#peasant-transfer-form').addEventListener('submit',async event=>{
  event.preventDefault();const data=Object.fromEntries([...new FormData(event.currentTarget)].map(([key,value])=>[key,Number(value)]));
  try{await api('/api/cabinet/peasants/transfer','POST',data);await loadPeasants();document.querySelector('#peasant-transfer-status').textContent='Крестьяне направлены на гекс.';}
  catch(error){document.querySelector('#peasant-transfer-status').textContent=error.message;}
});
const resourceNames={gold:'золото',food:'еда',wood:'дерево',cloth:'ткань',bronze:'бронза',leather:'кожа',iron:'железо',horse:'лошади'};
function missingCost(cost){return Object.entries(cost||{}).filter(([code,amount])=>(code==='gold'?armyState.gold:Number(armyState.inventory?.[code]||0))<amount).map(([code,amount])=>`${resourceNames[code]||code}: ${amount-(code==='gold'?armyState.gold:Number(armyState.inventory?.[code]||0))}`);}
function costText(cost){const entries=Object.entries(cost||{});return entries.length?entries.map(([code,amount])=>`${amount} ${resourceNames[code]||code}`).join(' · '):'Цена не установлена';}
function hireCard(item,kind,missing,onHire){
  const card=document.createElement('article');card.className=`hire-card${missing.length?' unavailable':''}`;
  const figure=document.createElement('div');figure.className='hire-card-figure';
  const img=document.createElement('img');img.src=item.image_path;img.alt=item.name;figure.append(img);
  if(kind==='unit'){
    const defense=document.createElement('span');defense.className='hire-card-stat hire-card-defense';defense.textContent=item.defense;defense.title=`Защита: ${item.defense}`;
    const attack=document.createElement('span');attack.className='hire-card-stat hire-card-attack';attack.textContent=item.attack;attack.title=`Атака: ${item.attack}`;
    figure.append(defense,attack);
  }
  const title=document.createElement('h3');title.textContent=item.name;
  const stats=document.createElement('p');stats.className='hire-card-stats';stats.textContent=kind==='general'
    ?`Жизни ${item.health} · атака ${item.attack} · защита ${item.defense} · инициатива ${item.initiative} · скорость ${item.speed}`
    :`Жизни ${item.health} · атака ${item.attack} · защита ${item.defense} · броня ${item.armor} · дальность ${item.attack_range}`;
  const price=document.createElement('p');price.className='hire-card-price';price.textContent=costText(kind==='general'?{gold:armyState.general_price}:item.cost);
  const reason=document.createElement('p');reason.className='hire-card-missing';reason.textContent=missing.length?`Не хватает: ${missing.join(' · ')}`:'Доступен для найма';
  const button=document.createElement('button');button.type='button';button.className='save';button.textContent=kind==='general'?'Нанять генерала':item.upgrade_from_name?`Улучшить из «${item.upgrade_from_name}»`:'Нанять юнита';button.disabled=missing.length>0;button.addEventListener('click',()=>onHire(button));
  card.append(figure,title,stats,price,reason,button);return card;
}
/** Перестраивает карточки генералов и доступные действия армии. */
function renderArmy() {
  const list=document.querySelector('#generals-list'); list.replaceChildren();
  document.querySelector('#army-gold').textContent=`Казна: ${armyState.gold} золотых`;
  const inventory=document.querySelector('#inventory-stats');inventory.replaceChildren();
  for(const [name,value] of Object.entries(armyState.inventory||{}).map(([code,quantity])=>[({food:'Еда',wood:'Дерево',cloth:'Ткань',bronze:'Бронза',leather:'Кожа',iron:'Железо',horse:'Лошади'})[code]||code,quantity])){
    const term=document.createElement('dt'),definition=document.createElement('dd');term.textContent=name;definition.textContent=value;inventory.append(term,definition);
  }
  if (!armyState.generals.length) { const empty=document.createElement('p'); empty.textContent='Генералы пока не наняты.'; list.append(empty); }
  armyState.generals.forEach(general=>{
    const card=document.createElement('article'); card.className='general-card'; card.tabIndex=0;
    const img=document.createElement('img'); img.src=general.icon; img.alt=`Генерал ${general.name}`;
    const info=document.createElement('div'), title=document.createElement('h3'), count=document.createElement('p');
    title.textContent=general.name; count.textContent=`${general.status==='captive'?'В плену · ':general.status==='recovering'?'Восстанавливается · ':''}Уровень ${general.level} · опыт ${general.experience} · атака ${general.attack} · защита ${general.defense} · юнитов ${general.units.length} из 5`; info.append(title,count);
    const fire=document.createElement('button'); fire.type='button'; fire.className='danger-button'; fire.textContent='Уволить';fire.hidden=general.status==='captive';
    fire.addEventListener('click',async event=>{event.stopPropagation();if(!confirm(`Уволить генерала ${general.name} и расформировать его отряд?`))return;await api(`/api/cabinet/army/generals/${general.id}`,'DELETE',{});await loadArmy();});
    const open=()=>openGeneral(general.id); card.addEventListener('click',open); card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}});
    card.append(img,info,fire); list.append(card);
  });
  const catalogue=document.querySelector('#general-catalogue');catalogue.replaceChildren();
  (armyState.general_catalogue||[]).forEach(general=>{
    const missing=[];
    if(armyState.generals.length>=10)missing.push('достигнут предел 10 генералов');
    missing.push(...missingCost({gold:armyState.general_price}));
    catalogue.append(hireCard(general,'general',missing,async()=>{
      if(busy)return;busy=true;
      try{await api('/api/cabinet/army/generals','POST',{catalog_id:general.id});await loadArmy();status.textContent=`Генерал нанят. Потрачено: ${armyState.general_price} золотых.`;}
      catch(error){status.textContent=`Найм не выполнен: ${error.message}`;}finally{busy=false;}
    }));
  });
}
function openGeneral(id) {
  const general=armyState.generals.find(item=>item.id===id); if(!general)return; selectedGeneralId=id;
  document.querySelector('#general-title').textContent=`Армия: ${general.name}`;
  document.querySelector('#general-count').textContent=`Состав: ${general.units.length} из 5`;
  const units=document.querySelector('#general-units'); units.replaceChildren();
  general.units.forEach(unit=>{
    const card=document.createElement('article'), img=document.createElement('img'), info=document.createElement('div'), remove=document.createElement('button');
    img.src=unit.image_path; img.alt=unit.name; const strong=document.createElement('strong'),small=document.createElement('small');strong.textContent=unit.name;small.textContent=`${unit.troop_type} · жизни ${unit.current_health}/${unit.max_health} · атака ${unit.attack} · защита ${unit.defense} · дальность ${unit.attack_range} · скорость ${unit.speed}`;info.append(strong,small);
    remove.type='button'; remove.textContent='Удалить'; remove.addEventListener('click',async()=>{await api(`/api/cabinet/army/generals/${id}/units/${unit.assignment_id}`,'DELETE',{});await loadArmy();openGeneral(id);});
    card.append(img,info,remove); units.append(card);
  });
  const openHire=document.querySelector('#open-unit-hire');openHire.hidden=general.status!=='active';
  const generalDialog=document.querySelector('#general-dialog'); if(!generalDialog.open)generalDialog.showModal();
}
document.querySelector('#close-general').addEventListener('click',()=>document.querySelector('#general-dialog').close());
function openUnitHire(generalId) {
  const general=armyState.generals.find(item=>item.id===generalId);if(!general)return;
  selectedGeneralId=generalId;
  const catalogue=document.querySelector('#unit-hire-catalogue');catalogue.replaceChildren();document.querySelector('#unit-hire-status').textContent=`Отряд «${general.name}»: ${general.units.length} из 5`;
  armyState.catalogue.forEach(unit=>{
    const missing=missingCost(unit.cost);
    if(unit.upgrade_from_unit_id&&!general.units.some(existing=>existing.id===unit.upgrade_from_unit_id))missing.push(`нужен юнит «${unit.upgrade_from_name}»`);
    if(!unit.upgrade_from_unit_id&&general.units.length>=5)missing.push('в армии нет свободного места');
    catalogue.append(hireCard(unit,'unit',missing,async button=>{
      button.disabled=true;
      document.querySelector('#unit-hire-status').textContent=unit.upgrade_from_unit_id
        ?`Улучшаем «${unit.upgrade_from_name}» до «${unit.name}»…`
        :`Нанимаем «${unit.name}»…`;
      try{
        const result=await api(`/api/cabinet/army/generals/${generalId}/units`,'POST',{unit_id:unit.id});
        await loadArmy();openGeneral(generalId);openUnitHire(generalId);
        const message=result.upgraded
          ?`«${unit.upgrade_from_name}» улучшен до «${unit.name}». Списано: ${costText(unit.cost)}.`
          :`Юнит «${unit.name}» нанят. Списано: ${costText(unit.cost)}.`;
        document.querySelector('#unit-hire-status').textContent=message;status.textContent=message;
      }
      catch(error){document.querySelector('#unit-hire-status').textContent=`Найм не выполнен: ${error.message}`;button.disabled=false;}
    }));
  });
  const hireDialog=document.querySelector('#unit-hire-dialog');if(!hireDialog.open)hireDialog.showModal();
}
document.querySelector('#open-unit-hire').addEventListener('click',()=>openUnitHire(selectedGeneralId));
document.querySelector('#close-unit-hire').addEventListener('click',()=>document.querySelector('#unit-hire-dialog').close());
document.querySelector('#close-unit-hire-action').addEventListener('click',()=>document.querySelector('#unit-hire-dialog').close());
/** Блокирует форму на время мутации и единообразно выводит результат. */
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
  try { const identity=await api('/api/me'); csrf=identity.csrf; await Promise.all([loadCabinet(),loadArmy(),loadDiplomacy(),loadPeasants()]); status.textContent=''; }
  catch(error) { status.textContent=error.message; }
})();
