const $ = id => document.getElementById(id);
const put = (id, text) => { if ($(id)) $(id).textContent = String(text ?? ''); };
const imageUrl = (url, width) => {
  if (!url.startsWith('https://nplt20league.com/uploads/')) return url;
  const query = new URLSearchParams({ url, w: String(width), q: '75' });
  return `https://nplt20league.com/_next/image/?${query}`;
};
let lastState;
function render(s) {
  lastState = s;
  const c = s.current || {};
  const broadcast = s.broadcast || {};
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
    if ($('batters')) $('batters').replaceChildren(...[c.striker, c.non_striker].map((i, n) => {
      const player = c.players[i];
      const row = document.createElement('div');
      row.className = `batter-row${n === 0 && !s.complete ? ' on-strike' : ''}`;
      const marker = document.createElement('span');
      marker.className = 'strike-marker';
      marker.textContent = '▶';
      const name = document.createElement('strong');
      name.textContent = player.name;
      const score = document.createElement('b');
      score.append(document.createTextNode(String(player.runs)));
      const balls = document.createElement('small');
      balls.textContent = `(${player.balls})`;
      score.append(balls);
      row.append(marker, name, score);
      return row;
    }));
  }

  if ($('scorebar')) {
    const teamA = broadcast.teams?.team_a || { full_name: s.teams?.[0] || 'Team A', short_name: 'A', logo: '' };
    const teamB = broadcast.teams?.team_b || { full_name: s.teams?.[1] || 'Team B', short_name: 'B', logo: '' };
    const battingIndex = c.team === teamB.full_name ? 1 : 0;
    const battingTeam = battingIndex === 0 ? teamA : teamB;
    const fieldingTeam = battingIndex === 0 ? teamB : teamA;
    put('venue', broadcast.venue || 'Tribhuvan University International Cricket Ground, Kirtipur');
    put('status', s.complete ? 'FULL TIME' : 'LIVE');
    put('team-abbr', battingTeam.short_name || battingTeam.full_name.slice(0, 3).toUpperCase());
    const teamMark = $('team-mark');
    const teamLogo = $('team-logo');
    if (teamMark && teamLogo) {
      teamMark.classList.toggle('has-logo', Boolean(battingTeam.logo));
      teamLogo.hidden = !battingTeam.logo;
      teamLogo.alt = `${battingTeam.full_name} logo`;
      if (battingTeam.logo) {
        teamLogo.src = imageUrl(battingTeam.logo, 128);
        teamLogo.onerror = () => {
          teamLogo.hidden = true;
          teamMark.classList.remove('has-logo');
        };
      }
    }
    put('batting', battingTeam.full_name);
    put('score', `${c.runs || 0}/${c.wickets || 0}`);
    put('overs', c.overs || '0.0');
    put('limit', s.max_overs);
    put('rate', Number(c.run_rate || 0).toFixed(2));
    put('summary', s.result || (s.target
      ? `${s.innings_number === 1 ? '1st' : '2nd'} innings · Need ${Math.max(0, s.target - c.runs)} from ${s.balls_remaining} · vs ${fieldingTeam.full_name}`
      : `${s.innings_number === 1 ? '1st' : '2nd'} innings · vs ${fieldingTeam.full_name}`));
    put('bowling-team', fieldingTeam.full_name);
    put('bowler-name', 'Not assigned');
  }

  if ($('sequence')) put('sequence', s.sequence ?? 0);
  if ($('status') && !$('scorebar')) put('status', s.running ? 'Running' : 'Paused');
  if ($('match-label')) put('match-label', `${s.teams?.[0] || 'Team A'} vs ${s.teams?.[1] || 'Team B'}`);
  if ($('countdown')) {
    const secs = Math.max(0, Number(s.broadcast?.match_start_seconds ?? 90));
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
  team_a: $('team-a') ? $('team-a').value.trim() || 'Kathmandu Gurkhas' : 'Kathmandu Gurkhas',
  team_b: $('team-b') ? $('team-b').value.trim() || 'Pokhara Avengers' : 'Pokhara Avengers',
  team_a_short: $('team-a-short') ? $('team-a-short').value.trim() || 'KTM' : 'KTM',
  team_b_short: $('team-b-short') ? $('team-b-short').value.trim() || 'PKR' : 'PKR',
  overs: Number($('match-overs') ? $('match-overs').value : 20)
}));
document.querySelectorAll('[data-broadcast-set]').forEach(button => button.onclick = () => command('set_broadcast', {
  stream_title: $('stream-title') ? $('stream-title').value.trim() : 'CricketOBS Broadcast',
  timer_seconds: Number($('timer-seconds') ? $('timer-seconds').value : 90),
  background: $('background-style') ? $('background-style').value : 'linear-gradient(135deg, #08141f, #173449)',
  team_a: $('team-a-name') ? $('team-a-name').value.trim() : 'Kathmandu Gurkhas',
  team_b: $('team-b-name') ? $('team-b-name').value.trim() : 'Pokhara Avengers',
  team_a_short: $('team-a-short') ? $('team-a-short').value.trim() : 'KTM',
  team_b_short: $('team-b-short') ? $('team-b-short').value.trim() : 'PKR'
}));
document.querySelectorAll('[data-outcome]').forEach(button => button.onclick = () => command('delivery',{outcome:button.dataset.outcome}));
if ($('reset-match')) $('reset-match').onclick = () => command('reset', {
  team_a:$('team-a').value.trim() || 'Kathmandu Gurkhas', team_b:$('team-b').value.trim() || 'Pokhara Avengers', overs:Number($('match-overs').value)
});
connect();
