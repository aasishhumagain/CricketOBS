import time
from fastapi.testclient import TestClient
from app.main import app


def test_pages_and_validation():
    with TestClient(app) as c:
        for path in ['/', '/overlay', '/static/live.js', '/static/style.css', '/health']:
            assert c.get(path).status_code == 200
        assert c.get('/api/state').json()['simulation']
        assert c.post('/api/control', json={'action':'unknown'}).status_code == 400
        assert c.post('/api/control', json={'action':'speed','interval':0}).status_code == 422
        assert c.post('/api/control', json={'action':'start'}, headers={'origin':'https://other.example'}).status_code == 403


def test_live_multiple_clients_and_reset():
    with TestClient(app) as c:
        with c.websocket_connect('/ws') as a, c.websocket_connect('/ws') as b:
            assert a.receive_json()['sequence'] == b.receive_json()['sequence'] == 0
            c.post('/api/control', json={'action':'step'})
            assert a.receive_json()['sequence'] == b.receive_json()['sequence'] == 1
            c.post('/api/control', json={'action':'reset'})
            assert a.receive_json()['sequence'] == b.receive_json()['sequence'] == 0


def test_automatic_play_pause():
    with TestClient(app) as c:
        c.post('/api/control', json={'action':'speed','interval':0.2})
        c.post('/api/control', json={'action':'start'})
        deadline = time.monotonic() + 5
        while c.get('/api/state').json()['sequence'] == 0 and time.monotonic() < deadline:
            time.sleep(.05)
        state = c.post('/api/control', json={'action':'pause'}).json()
        assert state['sequence'] > 0 and not state['running']
        time.sleep(.3)
        assert c.get('/api/state').json()['sequence'] == state['sequence']
