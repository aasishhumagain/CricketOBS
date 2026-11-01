const $ = id => document.getElementById(id);
const put = (id, value) => { if ($(id)) $(id).textContent = value ?? ''; };
function node(tag, cls, value) { const el=document.createElement(tag); el.className=cls; if(value!=null) el.textContent=value; return el; }
function media(url, alt, cls) {
  const el=node('img',cls); el.alt=alt; el.src=url; el.referrerPolicy='no-referrer';
  el.onerror=()=>el.replaceWith(node('span',cls+' media-fallback',alt)); return el;
}
function crest(team, cls='scene-logo') { return team.logo ? media(team.logo,team.full_name+' logo',cls) : node('span',cls+' media-fallback',team.short_name); }
let sceneKey='', retry=500;
function render(s) {
  const b=s.broadcast, c=s.current, sides=['team_a','team_b'], scene=b.page || 'score';
  const theme=b.overlay_style || 'classic';
  $('scorebar').dataset.theme=theme;
  $('broadcast-scene').dataset.theme=theme;
  const teams=sides.map(side=>b.teams[side]);
  const squads=teams.map(team=>(b.squads || []).find(squad=>squad.name===team.full_name));
  const battingIndex=s.teams.indexOf(c.team), batting=teams[Math.max(0,battingIndex)], fielding=teams[battingIndex===0?1:0];
  $('scorebar').hidden=scene!=='score'; document.querySelector('.match-locator').hidden=scene!=='score';
  $('broadcast-scene').hidden=scene==='score'||scene==='hidden';
  put('venue', b.venue || 'Tribhuvan University International Cricket Ground, Kirtipur');
  put('status',s.complete?'FULL TIME':'LIVE'); put('team-abbr',batting.short_name); put('batting',batting.full_name);
  const mark=$('team-mark');
  if(mark.dataset.logo!==batting.logo || !mark.dataset.ready) {
    mark.dataset.logo=batting.logo;mark.dataset.ready='yes';
    mark.replaceChildren(crest(batting,'scorebar-logo'),node('span','scorebar-abbr',batting.short_name));
  }
  put('score',c.runs+'/'+c.wickets);put('overs',c.overs);put('limit',s.max_overs);put('rate',Number(c.run_rate).toFixed(2));
  put('summary',s.result || (s.target ? 'TARGET '+s.target+' | NEED '+Math.max(0,s.target-c.runs)+' FROM '+s.balls_remaining : 'INNINGS '+s.innings_number+' | '+batting.short_name+' vs '+fielding.short_name));
  put('bowling-team',fielding.full_name); put('bowler-name','Not assigned');
  const battingSquad=squads[Math.max(0,battingIndex)];
  $('batters').replaceChildren(...[c.striker,c.non_striker].map((index,n)=>{
    const player=c.players[index], profile=battingSquad?.players.find(p=>p.name===player.name);
    const row=node('div','batter-row'+(n===0&&!s.complete?' on-strike':''));
    row.append(node('span','strike-marker','▶'));
    const identity=node('div','batter-identity');if(profile?.photo_url)identity.append(media(profile.photo_url,player.name,'batter-photo'));identity.append(node('strong','',player.name));
    const score=node('b','',String(player.runs)+' ');score.append(node('small','','('+player.balls+')'));row.append(identity,score);return row;
  }));
  // Rebuild scene content only when its data changes, not on every heartbeat.
  const key=JSON.stringify([scene,theme,b.stream_title,b.background,b.match_start_seconds,b.teams,b.playing_xi,b.toss,b.squads,s.innings,c,s.target,s.complete,s.result]);
  if(key===sceneKey)return;sceneKey=key;
  const root=$('broadcast-scene');root.style.background=b.background;root.replaceChildren();
  root.append(node('div','scene-eyebrow',b.stream_title),node('h1','scene-title',({'countdown':'Match starts soon','match-info':'Match information','roster':'Team squads','playing-xi':'Playing XI','toss':'Toss & decision','summary':'Match centre','innings-break':'Innings break','result':s.complete?'Match result':'Result pending'})[scene] || ''));
  if(['summary','innings-break','result'].includes(scene)) {
    const innings=s.innings || [c];
    const scores=node('div','summary-teams');
    teams.forEach(team=>{
      const inningsScore=innings.find(inn=>inn.team===team.full_name);
      const card=node('section','summary-team');
      card.append(crest(team,'summary-logo'),node('h2','',team.full_name));
      card.append(node('div','summary-total',inningsScore ? inningsScore.runs+'/'+inningsScore.wickets : 'Yet to bat'));
      if(inningsScore)card.append(node('p','summary-overs',Math.floor(inningsScore.balls/6)+'.'+inningsScore.balls%6+' / '+s.max_overs+' overs'));
      scores.append(card);
    });
    root.append(scores);
    let headline='First innings in progress';
    if(s.target)headline='Target '+s.target+' | '+c.team+' need '+Math.max(0,s.target-c.runs)+' from '+s.balls_remaining+' balls';
    if(scene==='innings-break')headline=s.target ? c.team+' need '+s.target+' runs to win' : 'The first innings has not finished';
    if(scene==='result')headline=s.complete ? s.result : 'Match in progress - final result will appear here';
    if(s.complete)headline=s.result;
    root.append(node('div','summary-headline',headline));
    if(scene==='summary') {
      const stats=node('div','summary-stats');
      for(const [label,value] of [['Run rate',Number(c.run_rate).toFixed(2)],['Required rate',s.required_rate ?? '--'],['Extras',c.extras ?? 0]]) {
        const stat=node('div','summary-stat');stat.append(node('small','',label),node('strong','',String(value)));stats.append(stat);
      }
      root.append(stats);
      const recent=node('div','summary-recent');
      recent.append(node('span','','Recent deliveries'));
      (c.recent || []).slice(-6).forEach(ball=>recent.append(node('b','delivery-chip'+(ball==='W'?' is-wicket':['4','6'].includes(ball)?' is-boundary':''),ball)));
      root.append(recent);
    }
    return;
  }
  if(scene==='countdown') {
    const seconds=b.match_start_seconds;root.append(node('div','scene-countdown',String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')));
  }
  const grid=node('div','scene-teams');
  teams.forEach((team,index)=>{
    const card=node('section','scene-team');const head=node('div','scene-team-heading');head.append(crest(team),node('h2','',team.full_name));card.append(head);
    if(scene==='roster'||scene==='playing-xi') {
      const players=scene==='roster' ? squads[index]?.players || [] : (b.playing_xi[sides[index]] || []).map(name=>squads[index]?.players.find(p=>p.name===name)||{name});
      const list=node('div','scene-players');
      players.forEach(player=>{const row=node('div','scene-player');if(player.photo_url)row.append(media(player.photo_url,player.name,'scene-portrait'));row.append(node('span','',player.name+(player.captain?' (C)':'')));list.append(row);});
      if(!players.length)list.append(node('p','','No playing XI saved'));card.append(list);
    }
    grid.append(card);
  });
  root.append(grid);
  if(scene==='toss')root.append(node('div','scene-toss',b.toss.winner ? b.toss.winner+' won the toss ('+b.toss.side+') and chose to '+(b.toss.decision||'Bat').toLowerCase()+' first' : 'Waiting for the toss result'));
}
function connect() {
 const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
 ws.onopen=()=>{retry=500;$('connection').hidden=true;};
 ws.onmessage=event=>{try{render(JSON.parse(event.data));}catch(error){$('connection').hidden=false;put('connection','Unable to display update');console.error(error);}};
 ws.onerror=()=>ws.close();ws.onclose=()=>{$('connection').hidden=false;put('connection','OFFLINE - score may be stale');setTimeout(connect,retry);retry=Math.min(retry*2,10000);};
}
connect();
