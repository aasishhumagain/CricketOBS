(() => {
  const buttons=[...document.querySelectorAll('[data-scene]')];
  const label=document.getElementById('on-air-scene'), error=document.getElementById('scene-error');
  function render(s) { const scene=s.broadcast.page || 'score'; document.getElementById('overlay-style').value=s.broadcast.overlay_style || 'classic'; buttons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.scene===scene)));label.textContent=scene==='hidden'?'Graphics hidden':'On air: '+(buttons.find(button=>button.dataset.scene===scene)?.textContent || scene); }
  buttons.forEach(button=>button.onclick=async()=>{ button.disabled=true;error.textContent='';try{const response=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set_scene',page:button.dataset.scene})});if(!response.ok)throw new Error('Unable to change the overlay scene');render(await response.json());}catch(e){error.textContent=e.message;}finally{button.disabled=false;} });
  document.getElementById('overlay-style').onchange=async event=>{
    const select=event.target;select.disabled=true;error.textContent='';
    try {const response=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set_overlay_style',overlay_style:select.value})});if(!response.ok)throw new Error('Unable to change the visual style');render(await response.json());}catch(e){error.textContent=e.message;}finally{select.disabled=false;}
  };
  window.addEventListener('match-state',event=>render(event.detail));
  // Roster uses its own editor; subscribe here for scene state on that page.
  if(!document.body.dataset.page) {
    let retry=500;
    function connect(){const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');ws.onopen=()=>retry=500;ws.onmessage=event=>{try{render(JSON.parse(event.data));}catch{error.textContent='Unable to read overlay state';}};ws.onerror=()=>ws.close();ws.onclose=()=>{label.textContent='Offline - reconnecting';setTimeout(connect,retry);retry=Math.min(retry*2,10000);};}connect();
  }
})();
