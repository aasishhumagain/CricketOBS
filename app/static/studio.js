const $ = id => document.getElementById(id);
let state, teams = [], initialized = false, xiKey = '', retry = 500;
const text = (id, value) => { if ($(id)) $(id).textContent = value; };
function image(url, alt, className) {
  const img = document.createElement('img');
  img.src = url; img.alt = alt; img.className = className;
  // Bound intrinsic dimensions before the image or stylesheet finishes loading.
  img.width = className === 'team-logo' ? 96 : 64;
  img.height = className === 'team-logo' ? 96 : 76;
  img.style.objectFit = 'contain';
  img.referrerPolicy = 'no-referrer';
  img.onerror = () => { const fallback = document.createElement('span'); fallback.className = 'image-fallback'; fallback.textContent = alt; img.replaceWith(fallback); };
  return img;
}
function options(select, items, value) {
  if (!select) return;
  select.replaceChildren(...items.map(item => { const option = document.createElement('option'); option.value = item; option.textContent = item; return option; }));
  select.value = value;
}
function render(s) {
  const teamsChanged = state && JSON.stringify(state.teams) !== JSON.stringify(s.teams);
  if (teamsChanged) initialized = false;
  state = s;
  if (s.broadcast.squads) teams = s.broadcast.squads;
  window.dispatchEvent(new CustomEvent('match-state', {detail:s}));
  const b = s.broadcast, current = s.current;
  text('match-label', s.teams.join(' vs '));
  const seconds = Math.max(0, b.match_start_seconds);
  text('countdown', String(Math.floor(seconds / 60)).padStart(2,'0') + ':' + String(seconds % 60).padStart(2,'0'));
  text('timer-state', s.running ? 'Countdown running' : seconds === 0 ? 'Ready to start' : 'Paused');
  text('score', current.runs + ' / ' + current.wickets);
  text('score-detail', current.team + ' | ' + current.overs + ' / ' + s.max_overs + ' overs');
  text('commentary', s.result || s.commentary);
  document.querySelectorAll('[data-outcome]').forEach(button => button.disabled = s.complete);
  document.querySelectorAll('[data-team]').forEach(el => el.textContent = b.teams[el.dataset.team].full_name);
  document.querySelectorAll('[data-short]').forEach(el => el.textContent = b.teams[el.dataset.short].short_name);
  document.querySelectorAll('[data-logo]').forEach(el => {
    const team = b.teams[el.dataset.logo];
    if (el.dataset.source === team.logo && el.childNodes.length) return;
    el.dataset.source = team.logo;
    el.replaceChildren(team.logo ? image(team.logo, team.full_name + ' logo', 'team-logo') : document.createTextNode(team.short_name));
  });
  const toss = b.toss;
  text('toss-summary', toss.winner ? toss.winner + ' | ' + toss.side + ' | ' + (toss.decision || 'Bat') + ' first' : 'No toss saved');
  if (!initialized) {
    if ($('team-a')) { options($('team-a'), teams.map(t=>t.name), s.teams[0]); options($('team-b'), teams.map(t=>t.name), s.teams[1]); $('match-overs').value = s.max_overs; }
    if ($('stream-title')) { $('stream-title').value = b.stream_title; $('timer-seconds').value = seconds; $('background-style').value = b.background; if (!$('background-style').value) $('background-style').selectedIndex = 0; }
    if ($('toss-winner')) { options($('toss-winner'), s.teams, toss.winner || s.teams[0]); $('toss-side').value = toss.side; $('toss-decision').value = toss.decision || 'Bat'; }
    initialized = true;
  }
  if ($('squad-a')) {
    const key = JSON.stringify([s.teams, b.playing_xi, b.squads]);
    if (key !== xiKey) {
      xiKey = key;
      for (const [index, side] of ['a','b'].entries()) {
        const squad = teams.find(t=>t.name === s.teams[index]);
        $('squad-'+side).replaceChildren(...(squad?.players || []).map(player => {
          const label = document.createElement('label'); label.className = 'item xi-player';
          const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.name = 'xi-'+side; checkbox.value = player.name; checkbox.checked = (b.playing_xi['team_'+side] || []).includes(player.name);
          checkbox.onchange = () => updateCount(side);
          const name = document.createElement('span'); name.textContent = player.name + (player.captain ? ' (C)' : '');
          label.append(checkbox); if (player.photo_url) label.append(image(player.photo_url, player.name + ' portrait', 'player-photo')); label.append(name); return label;
        }));
        updateCount(side);
      }
    }
  }
}
function selected(side) { return [...document.querySelectorAll('input[name="xi-'+side+'"]:checked')].map(input=>input.value); }
function updateCount(side) {
  const count = selected(side).length; text('count-'+side, count+' / 11 selected');
  document.querySelectorAll('input[name="xi-'+side+'"]').forEach(input=>input.disabled = count >= 11 && !input.checked);
}
async function command(action, extra = {}) {
  text('error',''); text('notice','');
  const response = await fetch('/api/control', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,...extra})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the form values and try again.');
  render(data); text('notice','Saved.');
}
function bindForm(id, handler) {
  if (!$(id)) return;
  $(id).onsubmit = async event => { event.preventDefault(); const button = event.submitter; if (button) button.disabled=true; try { await handler(); } catch(error) { text('error', error.message); } finally { if(button) button.disabled=false; } };
}
bindForm('scene-form', ()=>command('set_broadcast',{stream_title:$('stream-title').value.trim(),timer_seconds:Number($('timer-seconds').value),background:$('background-style').value}));
bindForm('match-form', ()=> {
  if ($('team-a').value === $('team-b').value) throw new Error('Choose two different teams.');
  if (!confirm('Start a new match? This clears the current score, toss and playing XI.')) return;
  const a=teams.find(t=>t.name===$('team-a').value), b=teams.find(t=>t.name===$('team-b').value);
  return command('reset',{team_a:a.name,team_b:b.name,team_a_short:a.short_name,team_b_short:b.short_name,overs:Number($('match-overs').value)});
});
bindForm('xi-form', ()=>command('set_playing_xi',{playing_xi_a:selected('a'),playing_xi_b:selected('b')}));
bindForm('toss-form', ()=>command('set_toss',{toss_side:$('toss-side').value,toss_winner:$('toss-winner').value,toss_decision:$('toss-decision').value}));
document.querySelectorAll('[data-command],[data-outcome]').forEach(button=>button.onclick=async()=>{ button.disabled=true; try { await command(button.dataset.command || 'delivery',button.dataset.outcome ? {outcome:button.dataset.outcome} : {}); } catch(error) {text('error',error.message);} finally {button.disabled=false;} });
function connect() {
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
  ws.onopen=()=>{ retry=500; text('connection','Connected - local'); };
  ws.onmessage=event=>{try {render(JSON.parse(event.data));} catch(error) {text('error','Unable to display the current state: '+error.message);} };
  ws.onerror=()=>ws.close();
  ws.onclose=()=>{text('connection','Offline - reconnecting - score may be stale'); setTimeout(connect,retry); retry=Math.min(retry*2,10000);};
}
async function init() {
  const response=await fetch('/api/roster'); if(!response.ok) throw new Error('Unable to load saved squads. Reload to retry.');
  teams=(await response.json()).teams; connect();
}
if ($('timer-seconds')) { $('timer-seconds').min=0; $('timer-seconds').max=86400; $('timer-seconds').required=true; }
if ($('match-overs')) { $('match-overs').min=1; $('match-overs').max=50; $('match-overs').required=true; }
init().catch(error=>text('error',error.message));
