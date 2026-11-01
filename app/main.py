import asyncio
import copy
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import Match

STATIC = Path(__file__).parent / 'static'


class Command(BaseModel):
    action: str
    outcome: str = '0'
    team_a: str = Field(default='Valley Falcons', max_length=32)
    team_b: str = Field(default='Summit Strikers', max_length=32)
    overs: int = Field(default=20, ge=1, le=50)


class Service:
    def __init__(self):
        self.match = Match()
        self.history = []
        self.clients: set[asyncio.Queue] = set()

    def state(self):
        return dict(self.match.snapshot(), running=False)

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


app = FastAPI(title='CricketOBS • Simulation', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.get('/')
async def dashboard():
    return FileResponse(STATIC / 'dashboard.html')


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
    # Local dashboard only; block cross-site browser commands (including form posts).
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
    elif command.action == 'reset':
        service.history.clear()
        service.match = Match(overs=command.overs, teams=(command.team_a.strip() or 'Team A', command.team_b.strip() or 'Team B'))
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
