const $ = id => document.getElementById(id);
const put = (id, text) => { if ($(id)) $(id).textContent = String(text ?? ''); };
let lastState;
function render(s) {
  lastState = s;
  const c = s.current || {};
  if (c && c.team) {
    put('teams', s.teams.join(' vs ')); put('batting', c.team);
    put('score', `${c.runs} / ${c.wickets}`); put('overs', c.overs);
    put('limit', s.max_overs); put('innings', `INNINGS ${s.innings_number}`);
    put('rate', c.run_rate.toFixed(2));
    put('status', s.complete ? 'MATCH COMPLETE' : 'LIVE SCORE');
    put('commentary', s.result || s.commentary);
    put('freehit', s.free_hit ? 'FREE HIT' : '');
    put('chase', s.target ? `TARGET ${s.target} • NEED ${Math.max(0, s.target-c.runs)} FROM ${s.balls_remaining}` : 'FIRST INNINGS');
    put('summary', s.result || (s.target ? `Required run rate: ${s.required_rate ?? '—'}` : 'Manual cricket score.'));
    put('previous', s.innings_number === 2 ? `${s.innings[0].team}: ${s.innings[0].runs}/${s.innings[0].wickets}` : '');
    if ($('recent')) $('recent').replaceChildren(...(c.recent || []).map(ball => {
      const el = document.createElement('span'); el.textContent = ball;
      el.className = ball === 'W' ? 'wicket' : ['4','6'].includes(ball) ? 'boundary' : '';
      return el;
    }));
    if ($('batters')) $('batters').replaceChildren(...[c.striker, c.non_striker].map((i,n) => {
      const el = document.createElement('div'); const p = c.players[i];
      el.textContent = `${p.name}${n === 0 && !s.complete ? ' *' : ''}    ${p.runs} (${p.balls})`;
      return el;
    }));
  }

  if ($('sequence')) put('sequence', s.sequence ?? 0);
  if ($('status')) put('status', s.running ? 'Running' : 'Paused');
  if ($('match-label')) put('match-label', `${s.teams?.[0] || 'Team A'} vs ${s.teams?.[1] || 'Team B'}`);
  if ($('countdown')) {
    const secs = Math.max(0, Number(s.broadcast?.match_start_seconds ?? 90) - Number(s.sequence || 0));
    const min = Math.floor(secs / 60).toString().padStart(2, '0');
    const sec = (secs % 60).toString().padStart(2, '0');
    $('countdown').textContent = `${min}:${sec}`;
  }
}
let retry = 500;
function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { retry = 500; put('connection', 'CONNECTED • LOCAL'); };
  ws.onmessage = event => { try { render(JSON.parse(event.data)); } catch { put('connection','INVALID UPDATE'); } };
  ws.onerror = () => ws.close();
  ws.onclose = () => { put('connection','OFFLINE • RETRYING • SCORE MAY BE STALE'); setTimeout(connect,retry); retry = Math.min(retry*2,10000); };
}
async function command(action, extra={}) {
  try {
    const response = await fetch('/api/control', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action,...extra}) });
    if (!response.ok) throw Error(`Command failed (${response.status})`);
    render(await response.json()); put('error','');
  } catch (error) { put('error',error.message); }
}
document.querySelectorAll('[data-action="undo"]').forEach(button => button.onclick = () => command('undo'));
document.querySelectorAll('[data-action="start"]').forEach(button => button.onclick = () => command('start'));
document.querySelectorAll('[data-action="pause"]').forEach(button => button.onclick = () => command('pause'));
document.querySelectorAll('[data-action="reset"]').forEach(button => button.onclick = () => command('reset', {
  team_a: $('team-a') ? $('team-a').value.trim() || 'Team A' : 'Team A',
  team_b: $('team-b') ? $('team-b').value.trim() || 'Team B' : 'Team B',
  overs: Number($('match-overs') ? $('match-overs').value : 20)
}));
document.querySelectorAll('[data-broadcast-set]').forEach(button => button.onclick = () => command('set_broadcast', {
  stream_title: $('stream-title') ? $('stream-title').value.trim() : 'CricketOBS Broadcast',
  timer_seconds: Number($('timer-seconds') ? $('timer-seconds').value : 90),
  background: $('background-style') ? $('background-style').value : 'linear-gradient(135deg, #08141f, #173449)',
  team_a: $('team-a-name') ? $('team-a-name').value.trim() : 'Valley Falcons',
  team_b: $('team-b-name') ? $('team-b-name').value.trim() : 'Summit Strikers',
  team_a_short: $('team-a-short') ? $('team-a-short').value.trim() : 'VF',
  team_b_short: $('team-b-short') ? $('team-b-short').value.trim() : 'SS'
}));
document.querySelectorAll('[data-outcome]').forEach(button => button.onclick = () => command('delivery',{outcome:button.dataset.outcome}));
if ($('reset-match')) $('reset-match').onclick = () => command('reset', {
  team_a:$('team-a').value.trim() || 'Team A', team_b:$('team-b').value.trim() || 'Team B', overs:Number($('match-overs').value)
});
connect();
