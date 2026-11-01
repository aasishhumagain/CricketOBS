import asyncio
import copy
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .engine import Match

STATIC = Path(__file__).parent / 'static'


class Command(BaseModel):
    model_config = ConfigDict(extra='ignore')

    action: str
    outcome: str = '0'
    team_a: str = Field(default='Valley Falcons', max_length=32)
    team_b: str = Field(default='Summit Strikers', max_length=32)
    overs: int = Field(default=20, ge=1, le=50)
    interval: float = Field(default=1.0, gt=0)
    stream_title: str = ''
    background: str = ''
    timer_seconds: int = Field(default=90, ge=0)
    team_a_short: str = 'VF'
    team_b_short: str = 'SS'
    team_a_logo: str = ''
    team_b_logo: str = ''
    toss_side: str = 'Heads'
    toss_winner: str = ''


class Service:
    def __init__(self):
        self.match = Match()
        self.history = []
        self.clients: set[asyncio.Queue] = set()
        self.sequence = 0
        self.running = False
        self.interval = 1.0
        self._task: asyncio.Task | None = None
        self.broadcast = {
            'stream_title': 'CricketOBS Broadcast',
            'background': 'linear-gradient(120deg, #08141f, #10273a)',
            'match_start_seconds': 90,
            'timer_running': False,
            'teams': {
                'team_a': {'full_name': 'Valley Falcons', 'short_name': 'VF', 'logo': ''},
                'team_b': {'full_name': 'Summit Strikers', 'short_name': 'SS', 'logo': ''},
            },
            'roster': {
                'team_a': ['Aarav Shrestha', 'Anish Gurung', 'Bibek Pandey', 'Nabin Tamang', 'Rabin Karki'],
                'team_b': ['Sanjay KC', 'Prabin Rai', 'Hari Thapa', 'Rohit Shah', 'Kushal Magar'],
            },
            'playing_xi': {
                'team_a': ['Aarav Shrestha', 'Anish Gurung', 'Bibek Pandey', 'Nabin Tamang', 'Rabin Karki'],
                'team_b': ['Sanjay KC', 'Prabin Rai', 'Hari Thapa', 'Rohit Shah', 'Kushal Magar'],
            },
            'toss': {'side': 'Heads', 'winner': 'Valley Falcons', 'result': 'Heads'},
            'page': 'home',
        }

    async def _tick(self):
        while self.running:
            await asyncio.sleep(self.interval)
            if not self.running:
                break
            self.sequence += 1
            try:
                self.match.step('1')
            except ValueError:
                self.running = False
                break
            self.publish()

    def start(self):
        if self.running:
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

    def reset(self, team_a='Team A', team_b='Team B', overs=20):
        self.history.clear()
        self.running = False
        self.interval = 1.0
        self.sequence = 0
        self.broadcast['timer_running'] = False
        self.broadcast['teams']['team_a']['full_name'] = team_a
        self.broadcast['teams']['team_b']['full_name'] = team_b
        self.broadcast['teams']['team_a']['short_name'] = team_a[:2].upper() if len(team_a) >= 2 else team_a.upper()
        self.broadcast['teams']['team_b']['short_name'] = team_b[:2].upper() if len(team_b) >= 2 else team_b.upper()
        self.match = Match(overs=overs, teams=(team_a.strip() or 'Team A', team_b.strip() or 'Team B'))
        self.publish()

    def state(self):
        payload = dict(self.match.snapshot(), running=self.running, sequence=self.sequence, simulation=True)
        payload['broadcast'] = self.broadcast.copy()
        return payload

    def publish(self):
        state = self.state()
        for queue in self.clients:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(state)


@asynccontextmanager
async def lifespan(app):
    app.state.service = Service()
    yield


app = FastAPI(title='CricketOBS • Broadcast Control', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


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
        service.reset(team_a=command.team_a, team_b=command.team_b, overs=command.overs)
    elif command.action == 'set_broadcast':
        service.broadcast['stream_title'] = command.stream_title or service.broadcast['stream_title']
        service.broadcast['match_start_seconds'] = command.timer_seconds or service.broadcast['match_start_seconds']
        service.broadcast['background'] = command.background or service.broadcast['background']
        service.broadcast['teams']['team_a']['full_name'] = command.team_a or service.broadcast['teams']['team_a']['full_name']
        service.broadcast['teams']['team_b']['full_name'] = command.team_b or service.broadcast['teams']['team_b']['full_name']
        service.broadcast['teams']['team_a']['short_name'] = command.team_a_short or service.broadcast['teams']['team_a']['short_name']
        service.broadcast['teams']['team_b']['short_name'] = command.team_b_short or service.broadcast['teams']['team_b']['short_name']
        service.broadcast['teams']['team_a']['logo'] = command.team_a_logo or service.broadcast['teams']['team_a']['logo']
        service.broadcast['teams']['team_b']['logo'] = command.team_b_logo or service.broadcast['teams']['team_b']['logo']
    elif command.action == 'set_toss':
        service.broadcast['toss'] = {
            'side': command.toss_side,
            'winner': command.toss_winner or service.broadcast['toss']['winner'],
            'result': command.toss_side,
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
