/* Release review 2026-09-18 (0.0.2): Edit hex metadata and connected territories with server-side revision checks.
 * Details: docs/releases/0.0.2-changes-2026-09-18.md. */
"use strict";
const fields = ['Название','Название территории','Категория','Остров','Доля суши, %','Тип местности','Состав ландшафта','Дополнительный объект','Проходимость','Защита','Плодородие','Опасность','Основной ресурс','Богатство ресурса','Глубина','Течение','Комментарий','Тип владельца','Владелец'];
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
  for(const field of fields) {
    const label=document.createElement('label');label.textContent=field;
    let input;
    if (['Категория','Тип владельца','Владелец','Остров'].includes(field)) input=document.createElement('select');
    else input=document.createElement(field==='Комментарий'?'textarea':'input');
    input.name=field;input.value=row[field]||'';input.maxLength=field==='Название'?200:4000;
    if(field==='Категория'||field==='Тип владельца'||field==='Остров') {
      const options=field==='Категория'?['Суша','Побережье','Море']:field==='Остров'?['Да','Нет']:['Ничейная территория','Игрок','Компьютерное владение'];
      const empty=new Option('Выберите','');input.append(empty);
      options.forEach(v=>input.append(new Option(v,v)));input.value=row[field]||'';
    }
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
(async()=>{try{const identity=await request('/api/me');if(!identity.can_edit)throw new Error('Доступ только для администрации');csrf=identity.csrf;await reload();status.textContent=`Гексов на карте: ${rows.length}`;}catch(error){status.textContent=error.message;}})();
