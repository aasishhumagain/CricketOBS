import asyncio
import copy
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .database import add_player, delete_player, get_roster, import_roster, initialize_database
from .engine import Match

STATIC = Path(__file__).parent / 'static'
TEAM_SHORT_NAMES = {'Kathmandu Gurkhas': 'KTM', 'Pokhara Avengers': 'PKR'}
ROSTER_SOURCE_NOTE = 'NPLT20League.com is an independent NPL coverage site, not affiliated with official NPL.'


class Command(BaseModel):
    model_config = ConfigDict(extra='ignore')

    action: str
    outcome: str = '0'
    team_a: str = Field(default='Kathmandu Gurkhas', max_length=32)
    team_b: str = Field(default='Pokhara Avengers', max_length=32)
    overs: int = Field(default=20, ge=1, le=50)
    interval: float = Field(default=1.0, gt=0)
    stream_title: str = ''
    background: str = ''
    timer_seconds: int = Field(default=90, ge=0)
    team_a_short: str = ''
    team_b_short: str = ''
    team_a_logo: str = ''
    team_b_logo: str = ''
    toss_side: str = 'Heads'
    toss_winner: str = ''
    toss_decision: Literal['Bat', 'Bowl'] = 'Bat'
    playing_xi_a: list[str] = Field(default_factory=list, max_length=11)
    playing_xi_b: list[str] = Field(default_factory=list, max_length=11)
    page: Literal['score', 'countdown', 'match-info', 'roster', 'playing-xi', 'toss', 'summary', 'innings-break', 'result', 'hidden'] = 'score'
    overlay_style: Literal['classic', 'midnight', 'minimal'] = 'classic'


class RosterPlayer(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default='', max_length=40)
    category: Literal['Domestic', 'Overseas', 'Not listed'] = 'Domestic'
    captain: bool = False


class ImportedPlayer(RosterPlayer):
    photo_url: str = ''
    profile_url: str = ''


class ImportedTeam(BaseModel):
    slug: str = Field(pattern=r'^[a-z0-9-]+$')
    name: str = Field(min_length=1, max_length=80)
    short_name: str = Field(min_length=1, max_length=8)
    logo_url: str = ''
    players: list[ImportedPlayer]


class RosterImport(BaseModel):
    season: int = 2026
    source: str
    source_published: str
    source_note: str = ROSTER_SOURCE_NOTE
    teams: list[ImportedTeam]


class Service:
    def __init__(self):
        self.match = Match()
        self.history = []
        self.clients: set[asyncio.Queue] = set()
        self.sequence = 0
        self.running = False
        self.interval = 1.0
        self._task: asyncio.Task | None = None
        self.team_media = {team['name']: team['logo_url'] for team in get_roster()}
        self.broadcast = {
            'stream_title': 'Nepal Premire League',
            'background': 'linear-gradient(120deg, #08141f, #10273a)',
            'match_start_seconds': 90,
            'timer_running': False,
            'teams': {
                'team_a': {'full_name': 'Kathmandu Gurkhas', 'short_name': 'KTM', 'logo': self.team_media.get('Kathmandu Gurkhas', '')},
                'team_b': {'full_name': 'Pokhara Avengers', 'short_name': 'PKR', 'logo': self.team_media.get('Pokhara Avengers', '')},
            },
            'roster': {team['name']: [p['name'] for p in team['players']] for team in get_roster()},
            'playing_xi': {'team_a': [], 'team_b': []},
            'toss': {'side': 'Heads', 'winner': '', 'result': 'Heads', 'decision': 'Bat'},
            'page': 'score',
            'overlay_style': 'classic',
        }

    async def _tick(self):
        while self.running:
            await asyncio.sleep(1)
            if not self.running:
                break
            self.broadcast['match_start_seconds'] = max(0, self.broadcast['match_start_seconds'] - 1)
            if self.broadcast['match_start_seconds'] == 0:
                self.running = False
                self.broadcast['timer_running'] = False
            self.publish()

    def start(self):
        if self.running or self.broadcast['match_start_seconds'] == 0:
            return
        self.running = True
        self.broadcast['timer_running'] = True
        self._task = asyncio.create_task(self._tick())
        self.publish()

    def pause(self):
        self.running = False
        self.broadcast['timer_running'] = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.publish()

    def step(self):
        self.sequence += 1
        self.publish()

    def reset(self, team_a='Kathmandu Gurkhas', team_b='Pokhara Avengers', overs=20,
              team_a_short='', team_b_short=''):
        self.pause()
        self.history.clear()
        self.running = False
        self.interval = 1.0
        self.sequence = 0
        self.broadcast['timer_running'] = False
        self.broadcast['teams']['team_a']['full_name'] = team_a
        self.broadcast['teams']['team_b']['full_name'] = team_b
        self.broadcast['teams']['team_a']['short_name'] = team_a_short.strip() or TEAM_SHORT_NAMES.get(team_a, team_a[:3].upper())
        self.broadcast['teams']['team_b']['short_name'] = team_b_short.strip() or TEAM_SHORT_NAMES.get(team_b, team_b[:3].upper())
        self.broadcast['teams']['team_a']['logo'] = self.team_media.get(team_a, '')
        self.broadcast['teams']['team_b']['logo'] = self.team_media.get(team_b, '')
        self.broadcast['playing_xi'] = {'team_a': [], 'team_b': []}
        self.broadcast['toss'] = {'side': 'Heads', 'winner': '', 'result': 'Heads', 'decision': 'Bat'}
        self.match = Match(overs=overs, teams=(team_a.strip() or 'Team A', team_b.strip() or 'Team B'))
        self.publish()

    def state(self):
        payload = dict(self.match.snapshot(), running=self.running, sequence=self.sequence, simulation=True)
        payload['broadcast'] = copy.deepcopy(self.broadcast)
        payload['broadcast']['squads'] = get_roster()
        return payload

    def publish(self):
        state = self.state()
        for queue in self.clients:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(state)


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    app.state.service = Service()
    try:
        yield
    finally:
        app.state.service.pause()


app = FastAPI(title='CricketOBS • Broadcast Control', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.middleware('http')
async def revalidate_frontend(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/static/') or 'text/html' in response.headers.get('content-type', ''):
        response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get('/')
async def dashboard():
    return FileResponse(STATIC / 'dashboard.html')


@app.get('/studio')
async def studio():
    return FileResponse(STATIC / 'dashboard.html')


@app.get('/match-info')
async def match_info():
    return FileResponse(STATIC / 'match-info.html')


@app.get('/roster')
async def roster():
    return FileResponse(STATIC / 'roster.html')


@app.get('/playing-xi')
async def playing_xi():
    return FileResponse(STATIC / 'playing-xi.html')


@app.get('/toss')
async def toss_page():
    return FileResponse(STATIC / 'toss.html')


@app.get('/overlay')
async def overlay():
    return FileResponse(STATIC / 'overlay.html')


@app.get('/api/state')
async def state(request: Request):
    return request.app.state.service.state()


@app.get('/api/roster')
async def roster_data():
    teams = get_roster()
    return {
        'season': 2026,
        'source_url': teams[0]['source_url'] if teams else '',
        'source_published': teams[0]['source_published'] if teams else '',
        'source_note': ROSTER_SOURCE_NOTE,
        'teams': teams,
    }


@app.post('/api/roster/import')
async def roster_import(payload: RosterImport, request: Request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Use the local dashboard origin')
    if len(payload.teams) != 8:
        raise HTTPException(422, 'NPL Season 3 import must contain eight teams')
    if not payload.source.startswith('https://nplt20league.com/teams/'):
        raise HTTPException(422, 'Only the configured NPL team source can be imported')
    media_urls = [team.logo_url for team in payload.teams]
    media_urls.extend(player.photo_url for team in payload.teams for player in team.players)
    if any(url and not url.startswith('https://nplt20league.com/uploads/') for url in media_urls):
        raise HTTPException(422, 'Team logos and player photos must come from the NPL uploads host')

    seed = payload.model_dump()
    try:
        import_roster(seed)
    except (KeyError, ValueError) as error:
        raise HTTPException(422, f'Invalid roster import: {error}')

    service = request.app.state.service
    service.team_media = {team['name']: team['logo_url'] for team in seed['teams']}
    for team in seed['teams']:
        for side in ('team_a', 'team_b'):
            if service.broadcast['teams'][side]['full_name'] == team['name']:
                service.broadcast['teams'][side]['logo'] = team['logo_url']
    service.publish()
    return {'teams': len(seed['teams']), 'players': sum(len(team['players']) for team in seed['teams'])}


@app.post('/api/roster/{team_slug}/players', status_code=201)
async def roster_add_player(team_slug: str, player: RosterPlayer, request: Request):
    try:
        added = add_player(
            team_slug, player.name, player.role, player.category, player.captain,
        )
        request.app.state.service.publish()
        return added
    except LookupError as error:
        raise HTTPException(404, str(error))
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.delete('/api/roster/{team_slug}/players/{player_id}', status_code=204)
async def roster_delete_player(team_slug: str, player_id: int, request: Request):
    if not delete_player(team_slug, player_id):
        raise HTTPException(404, 'Player not found on this team')
    request.app.state.service.publish()
    return Response(status_code=204)


@app.get('/health')
async def health():
    return {'status': 'ok', 'mode': 'manual'}


@app.post('/api/control')
async def control(command: Command, request: Request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Use the local dashboard origin')

    service = request.app.state.service
    if command.action == 'delivery':
        service.history.append(copy.deepcopy(service.match))
        try:
            service.match.step(command.outcome)
        except ValueError as error:
            service.history.pop()
            raise HTTPException(422, str(error))
    elif command.action == 'undo':
        if service.history:
            service.match = service.history.pop()
    elif command.action == 'step':
        service.step()
    elif command.action == 'start':
        service.start()
    elif command.action == 'pause':
        service.pause()
    elif command.action == 'speed':
        service.interval = command.interval
        if not service.running:
            service.pause()
    elif command.action == 'reset':
        if command.team_a.strip() == command.team_b.strip():
            raise HTTPException(422, 'Choose two different teams')
        service.reset(team_a=command.team_a, team_b=command.team_b, overs=command.overs,
                      team_a_short=command.team_a_short, team_b_short=command.team_b_short)
    elif command.action == 'set_broadcast':
        for field, key in [('stream_title', 'stream_title'), ('timer_seconds', 'match_start_seconds'), ('background', 'background')]:
            if field in command.model_fields_set:
                service.broadcast[key] = getattr(command, field)
    elif command.action == 'set_playing_xi':
        if any(innings.balls or innings.runs or innings.wickets for innings in service.match.innings):
            raise HTTPException(422, 'Set the playing XI before scoring begins')
        squads = {team['name']: {p['name'] for p in team['players']} for team in get_roster()}
        for side, names in [('team_a', command.playing_xi_a), ('team_b', command.playing_xi_b)]:
            if len(names) != 11 or len(set(names)) != 11:
                raise HTTPException(422, 'Select eleven different players for each team')
            if not set(names) <= squads.get(service.broadcast['teams'][side]['full_name'], set()):
                raise HTTPException(422, 'Select players from the current team roster')
        service.broadcast['playing_xi'] = {'team_a': command.playing_xi_a, 'team_b': command.playing_xi_b}
        service.match.lineups = [command.playing_xi_a, command.playing_xi_b]
        for index, innings in enumerate(service.match.innings):
            for batter, name in zip(innings.players, service.match.lineups[index]):
                batter.name = name
    elif command.action == 'set_scene':
        service.broadcast['page'] = command.page
    elif command.action == 'set_overlay_style':
        service.broadcast['overlay_style'] = command.overlay_style
    elif command.action == 'set_toss':
        if command.toss_side not in ('Heads', 'Tails') or command.toss_winner not in service.match.teams:
            raise HTTPException(422, 'Choose a toss side and one of the current teams')
        service.broadcast['toss'] = {
            'side': command.toss_side,
            'winner': command.toss_winner or service.broadcast['toss']['winner'],
            'result': command.toss_side,
            'decision': command.toss_decision,
        }
    else:
        raise HTTPException(400, 'Unknown action')

    service.publish()
    return service.state()


@app.websocket('/ws')
async def live(ws: WebSocket):
    await ws.accept()
    service = ws.app.state.service
    queue = asyncio.Queue(maxsize=1)
    service.clients.add(queue)

    async def sender():
        await ws.send_json(service.state())
        while True:
            try:
                update = await asyncio.wait_for(queue.get(), timeout=10)
            except asyncio.TimeoutError:
                update = service.state()
            await ws.send_json(update)

    task = asyncio.create_task(sender())
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        service.clients.discard(queue)
        task.cancel()
        with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            await task
