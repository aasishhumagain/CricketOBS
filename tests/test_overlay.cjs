const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.style={};this.hidden=false;this.textContent='';}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 replaceWith(other){this.replacement=other;}
}
function fixture(){
 const ids=new Map(['scorebar','broadcast-scene','connection','venue','status','team-abbr','batting','team-mark','score','overs','limit','rate','summary','bowling-team','bowler-name','batters'].map(id=>[id,new Element()]));
 const locator=new Element();
 const context={document:{getElementById:id=>ids.get(id),querySelector:()=>locator,createElement:tag=>new Element(tag)},location:{protocol:'http:',host:'localhost'},WebSocket:function(){},setTimeout(){},console};
 vm.createContext(context);vm.runInContext(fs.readFileSync('app/static/overlay.js','utf8'),context);
 const state={teams:['Alpha','Beta'],current:{team:'Alpha',runs:4,wickets:0,overs:'0.1',run_rate:24,striker:0,non_striker:1,players:[{name:'Alice',runs:4,balls:1},{name:'Amy',runs:0,balls:0}]},max_overs:20,innings_number:1,complete:false,broadcast:{page:'score',stream_title:'Cup final',background:'green',match_start_seconds:65,teams:{team_a:{full_name:'Alpha',short_name:'ALP',logo:'alpha.png'},team_b:{full_name:'Beta',short_name:'BET',logo:'beta.png'}},playing_xi:{team_a:['Alice'],team_b:['Bob']},squads:[{name:'Alpha',players:[{name:'Alice',photo_url:'alice.png'}]},{name:'Beta',players:[{name:'Bob',photo_url:'bob.png'}]}],toss:{winner:'Beta',side:'Tails',decision:'Bowl'}}};
 return {ids,locator,state,render(){vm.runInContext('render('+JSON.stringify(state)+')',context);}};
}
function content(el){return [el.textContent,...el.children.map(content)].join(' ');}
test('score and crest follow the batting team and player portraits',()=>{
 const f=fixture();f.render();assert.equal(f.ids.get('score').textContent,'4/0');assert.equal(f.ids.get('team-mark').children[0].src,'alpha.png');assert.equal(f.ids.get('batters').children[0].children[1].children[0].src,'alice.png');
 f.state.current.team='Beta';f.render();assert.equal(f.ids.get('team-mark').children[0].src,'beta.png');
});
test('panel scene state selects countdown, squads, XI, toss and hidden output',()=>{
 const f=fixture();
 for(const scene of ['countdown','match-info','roster','playing-xi','toss']){f.state.broadcast.page=scene;f.render();assert.equal(f.ids.get('scorebar').hidden,true);assert.equal(f.ids.get('broadcast-scene').hidden,false);assert.match(content(f.ids.get('broadcast-scene')),/Alpha/);}
 assert.match(content(f.ids.get('broadcast-scene')),/Beta won the toss.*bowl first/);
 f.state.broadcast.page='countdown';f.render();assert.match(content(f.ids.get('broadcast-scene')),/01:05/);
 f.state.broadcast.match_start_seconds=0;f.render();assert.match(content(f.ids.get('broadcast-scene')),/00:00/);
 f.state.broadcast.page='hidden';f.render();assert.equal(f.ids.get('scorebar').hidden,true);assert.equal(f.ids.get('broadcast-scene').hidden,true);assert.equal(f.locator.hidden,true);
});

test('summary updates with deliveries and result waits for completion',()=>{
 const f=fixture();f.state.current.balls=1;f.state.current.extras=0;f.state.current.recent=['4'];
 f.state.innings=[f.state.current];f.state.broadcast.page='summary';f.render();
 assert.match(content(f.ids.get('broadcast-scene')),/4\/0/);
 f.state.current.runs=10;f.state.current.recent=['4','6'];f.render();
 assert.match(content(f.ids.get('broadcast-scene')),/10\/0/);
 assert.match(content(f.ids.get('broadcast-scene')),/Recent deliveries/);
 f.state.broadcast.page='result';f.render();assert.match(content(f.ids.get('broadcast-scene')),/final result will appear here/);
 f.state.complete=true;f.state.result='Alpha win by 5 runs';f.render();assert.match(content(f.ids.get('broadcast-scene')),/Alpha win by 5 runs/);
});
test('innings break uses the chase target and themes follow shared state',()=>{
 const f=fixture();f.state.broadcast.page='innings-break';f.render();assert.match(content(f.ids.get('broadcast-scene')),/first innings has not finished/);
 f.state.target=101;f.state.current.team='Beta';f.render();assert.match(content(f.ids.get('broadcast-scene')),/Beta need 101 runs to win/);
 for(const theme of ['classic','midnight','minimal']) {f.state.broadcast.overlay_style=theme;f.render();assert.equal(f.ids.get('scorebar').dataset.theme,theme);assert.equal(f.ids.get('broadcast-scene').dataset.theme,theme);}
});
