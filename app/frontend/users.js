/* Release review 2026-09-18 (0.0.2): Administrator account search, role/password changes, and confirmed deletion.
 * Details: docs/releases/0.0.2-changes-2026-09-18.md. */
'use strict';
const $ = s => document.querySelector(s);
const labels = {admin:'Администраторы',moderator:'Модераторы',user:'Пользователи'};
let csrf='', page=1, selected=null, loading=false;
async function api(url, options={}) {
  const response=await fetch(url,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...options.headers}});
  const result=await response.json();
  if(!response.ok) throw new Error(result.error || 'Не удалось выполнить запрос');
  return result;
}
async function load() {
  if(loading) return;
  loading=true; $('#status').textContent='Загрузка…'; $('#prev').disabled=$('#next').disabled=true;
  try {
    const data=await api('/api/admin/users?'+new URLSearchParams({q:$('#query').value,role:$('#role').value,page}));
    $('#rows').replaceChildren();
    for(const user of data.users) {
      const row=document.createElement('tr');
      for(const value of [user.id,user.login,user.email,labels[user.role]]) {
        const cell=document.createElement('td');cell.textContent=value;row.append(cell);
      }
      const cell=document.createElement('td'),button=document.createElement('button');
      button.textContent='Редактировать';button.setAttribute('aria-label','Редактировать '+user.login);
      button.onclick=()=>{selected=user;$('#edit').reset();for(const key of ['login','email','role']) $('#edit').elements[key].value=user[key];$('#edit-error').textContent='';$('#editor').showModal();};
      cell.append(button);row.append(cell);$('#rows').append(row);
    }
    $('#count').textContent=`Страница ${page} · Всего: ${data.total}`;
    $('#prev').disabled=page<=1;$('#next').disabled=page*50>=data.total;
    $('#status').textContent=data.users.length?'':'Пользователи не найдены';
  } catch(error) {$('#status').textContent=error.message;}
  finally {loading=false;}
}
$('#search').onsubmit=event=>{event.preventDefault();if(!loading){page=1;load();}};
$('#prev').onclick=()=>{page--;load();};$('#next').onclick=()=>{page++;load();};
$('#cancel').onclick=()=>$('#editor').close();
$('#delete').onclick=async()=>{
  if(!selected || !confirm(`Удалить пользователя «${selected.login}»? Его аккаунт, сеансы и барония будут удалены, а его гексы станут нейтральными.`)) return;
  $('#delete').disabled=true; $('#edit-error').textContent='';
  try {const result=await api('/api/admin/users/'+selected.id,{method:'DELETE'}); $('#editor').close(); await load(); $('#status').textContent=`Пользователь удалён. Освобождено гексов: ${result.released_hexes}.`;}
  catch(error){$('#edit-error').textContent=error.message;}
  finally{$('#delete').disabled=false;}
};
$('#editor').addEventListener('close',()=>{$('#edit').elements.password.value='';$('#edit').elements.password_confirm.value='';});
$('#edit').onsubmit=async event=>{
  event.preventDefault();$('#save').disabled=true;$('#edit-error').textContent='';
  const payload=Object.fromEntries(new FormData($('#edit')));
  payload.expected={login:selected.login,email:selected.email,role:selected.role};
  try {const result=await api('/api/admin/users/'+selected.id,{method:'PATCH',body:JSON.stringify(payload)});$('#editor').close();if(result.reauthenticate){location.href='/index.php';return;}await load();$('#status').textContent='Изменения сохранены';}
  catch(error){$('#edit-error').textContent=error.message;}
  finally{$('#save').disabled=false;}
};
$('#logout').onclick=async()=>{const response=await fetch('/logout',{method:'POST',body:new URLSearchParams({csrf})});if(response.ok)location.href='/index.php';else $('#status').textContent='Не удалось выйти';};
(async()=>{try{const me=await api('/api/me');csrf=me.csrf;await load();}catch(error){$('#status').textContent=error.message;}})();
