fetch('/api/me',{cache:'no-store'}).then(response=>response.ok?response.json():null).then(identity=>{
  if(identity?.role==='admin')document.querySelectorAll('[data-admin-only]').forEach(link=>link.hidden=false);
}).catch(()=>{});
