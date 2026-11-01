import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient
from app.database import SEED_PATH, add_player, get_roster, import_roster, initialize_database
from app.main import app


def test_pages_and_validation():
    with TestClient(app) as c:
        for path in ['/', '/overlay', '/roster', '/static/live.js', '/static/roster.js',
                     '/static/roster.css', '/static/overlay-scorebar.css',
                     '/static/style.css', '/health']:
            assert c.get(path).status_code == 200
        assert c.get('/api/state').json()['simulation']
        assert c.post('/api/control', json={'action':'unknown'}).status_code == 400
        assert c.post('/api/control', json={'action':'speed','interval':0}).status_code == 422
        assert c.post('/api/control', json={'action':'start'}, headers={'origin':'https://other.example'}).status_code == 403


def test_seeded_rosters_persist_across_app_restart():
    player_name = f'Roster Persistence {uuid4().hex}'
    team_slug = 'biratnagar-kings'
    seed = json.loads(SEED_PATH.read_text(encoding='utf-8'))
    expected_players = sum(len(team['players']) for team in seed['teams'])

    with TestClient(app) as c:
        roster = c.get('/api/roster').json()
        assert roster['season'] == 2026
        assert len(roster['teams']) == 8
        assert sum(len(team['players']) for team in roster['teams']) == expected_players
        assert all(team['logo_url'] for team in roster['teams'])
        assert sum(bool(player['photo_url']) for team in roster['teams'] for player in team['players']) == expected_players
        assert roster['source_url'] == 'https://nplt20league.com/teams/'
        kings = next(team for team in roster['teams'] if team['slug'] == team_slug)
        assert any(player['name'] == 'Sandeep Lamichhane' and player['captain'] for player in kings['players'])

        added = c.post(f'/api/roster/{team_slug}/players', json={
            'name': player_name,
            'role': 'Batter',
            'category': 'Domestic',
        })
        assert added.status_code == 201
        player_id = added.json()['id']

    with TestClient(app) as c:
        roster = c.get('/api/roster').json()
        kings = next(team for team in roster['teams'] if team['slug'] == team_slug)
        assert any(player['name'] == player_name for player in kings['players'])
        assert c.delete(f'/api/roster/{team_slug}/players/{player_id}').status_code == 204
        assert c.delete(f'/api/roster/{team_slug}/players/{player_id}').status_code == 404


def test_roster_import_persists_media_and_keeps_user_players():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / 'roster.sqlite3'
        seed_path = root / 'seed.json'
        initialize_database(database)
        add_player('biratnagar-kings', 'User Added Player', database_path=database)

        seed = json.loads(SEED_PATH.read_text(encoding='utf-8'))
        seed['source'] = 'https://nplt20league.com/teams/'
        seed['teams'][0]['logo_url'] = 'https://nplt20league.com/uploads/team.png'
        seed['teams'][0]['players'][0].update(
            category='Not listed',
            photo_url='https://nplt20league.com/uploads/player.webp',
        )
        imported_player_name = seed['teams'][0]['players'][0]['name']
        import_roster(seed, database, seed_path)

        kings = next(team for team in get_roster(database) if team['slug'] == 'biratnagar-kings')
        imported_player = next(player for player in kings['players'] if player['name'] == imported_player_name)
        assert kings['logo_url'].endswith('team.png')
        assert imported_player['photo_url'].endswith('player.webp')
        assert imported_player['category'] == 'Not listed'
        assert any(player['name'] == 'User Added Player' for player in kings['players'])
        assert json.loads(seed_path.read_text(encoding='utf-8'))['source'] == seed['source']


def test_live_multiple_clients_and_reset():
    with TestClient(app) as c:
        with c.websocket_connect('/ws') as a, c.websocket_connect('/ws') as b:
            assert a.receive_json()['sequence'] == b.receive_json()['sequence'] == 0
            c.post('/api/control', json={'action':'step'})
            assert a.receive_json()['sequence'] == b.receive_json()['sequence'] == 1
            reset = c.post('/api/control', json={'action':'reset'}).json()
            assert reset['teams'] == ['Kathmandu Gurkhas', 'Pokhara Avengers']
            assert reset['broadcast']['teams']['team_a']['short_name'] == 'KTM'
            assert reset['broadcast']['teams']['team_b']['short_name'] == 'PKR'
            assert a.receive_json()['sequence'] == b.receive_json()['sequence'] == 0


def test_countdown_start_pause_resume_and_finish_without_scoring():
    with TestClient(app) as c:
        c.post('/api/control', json={'action': 'set_broadcast', 'timer_seconds': 3})
        before = c.get('/api/state').json()
        with c.websocket_connect('/ws') as viewer:
            viewer.receive_json()
            c.post('/api/control', json={'action': 'start'})
            assert viewer.receive_json()['running']
            tick = viewer.receive_json()
            assert tick['broadcast']['match_start_seconds'] == 2
            paused = c.post('/api/control', json={'action': 'pause'}).json()
            time.sleep(1.1)
            assert c.get('/api/state').json()['broadcast']['match_start_seconds'] == paused['broadcast']['match_start_seconds']
        c.post('/api/control', json={'action': 'start'})
        deadline = time.monotonic() + 5
        while c.get('/api/state').json()['running'] and time.monotonic() < deadline:
            time.sleep(.05)
        state = c.get('/api/state').json()
        assert not state['running']
        assert state['broadcast']['match_start_seconds'] == 0
        assert not state['broadcast']['timer_running']
        assert state['current'] == before['current']
        assert state['sequence'] == before['sequence']
        assert not c.post('/api/control', json={'action': 'start'}).json()['running']


def test_studio_toss_xi_and_partial_settings():
    with TestClient(app) as c:
        for path in ['/match-info', '/playing-xi', '/toss', '/static/studio.js']:
            assert c.get(path).status_code == 200
        teams = c.get('/api/roster').json()['teams'][:2]
        c.post('/api/control', json={'action': 'reset', 'team_a': teams[0]['name'], 'team_b': teams[1]['name']})
        c.post('/api/control', json={'action': 'set_broadcast', 'stream_title': 'Saved title'})
        state = c.post('/api/control', json={'action': 'set_broadcast', 'timer_seconds': 0}).json()
        assert state['teams'] == [team['name'] for team in teams]
        assert state['broadcast']['stream_title'] == 'Saved title'
        assert c.post('/api/control', json={'action': 'set_toss', 'toss_winner': 'Unknown'}).status_code == 422
        toss = c.post('/api/control', json={'action': 'set_toss', 'toss_winner': teams[1]['name'], 'toss_side': 'Tails', 'toss_decision': 'Bowl'}).json()
        assert toss['broadcast']['toss']['decision'] == 'Bowl'
        assert c.post('/api/control', json={'action': 'set_playing_xi', 'playing_xi_a': ['Unknown'] * 11}).status_code == 422
        a = [p['name'] for p in teams[0]['players'][:11]]
        b = [p['name'] for p in teams[1]['players'][:11]]
        response = c.post('/api/control', json={'action': 'set_playing_xi', 'playing_xi_a': a, 'playing_xi_b': b})
        assert response.status_code == 200
        assert response.json()['broadcast']['playing_xi']['team_a'] == a
        reset = c.post('/api/control', json={'action': 'reset'}).json()
        assert reset['broadcast']['playing_xi']['team_a'] == []
        assert reset['broadcast']['toss']['winner'] == ''


def test_panel_scene_and_lineups_reach_all_overlay_viewers():
    with TestClient(app) as c:
        with c.websocket_connect('/ws') as panel, c.websocket_connect('/ws') as overlay:
            panel.receive_json()
            overlay.receive_json()
            response = c.post('/api/control', json={'action': 'set_scene', 'page': 'toss'})
            assert response.status_code == 200
            assert panel.receive_json()['broadcast']['page'] == 'toss'
            assert overlay.receive_json()['broadcast']['page'] == 'toss'
            assert c.post('/api/control', json={'action': 'set_scene', 'page': 'unknown'}).status_code == 422
        squads = c.get('/api/roster').json()['teams']
        names = c.get('/api/state').json()['teams']
        lineups = [[p['name'] for p in next(t for t in squads if t['name'] == name)['players'][:11]] for name in names]
        response = c.post('/api/control', json={'action': 'set_playing_xi', 'playing_xi_a': lineups[0], 'playing_xi_b': lineups[1]})
        assert response.status_code == 200
        assert response.json()['current']['players'][0]['name'] == lineups[0][0]
        for _ in range(10):
            response = c.post('/api/control', json={'action': 'delivery', 'outcome': 'W'})
        assert response.json()['current']['players'][0]['name'] == lineups[1][0]
        assert c.post('/api/control', json={'action': 'set_playing_xi', 'playing_xi_a': lineups[0], 'playing_xi_b': lineups[1]}).status_code == 422


def test_extra_scenes_and_overlay_styles_are_shared():
    with TestClient(app) as c:
        with c.websocket_connect('/ws') as viewer:
            viewer.receive_json()
            for scene in ['summary', 'innings-break', 'result']:
                response = c.post('/api/control', json={'action': 'set_scene', 'page': scene})
                assert response.status_code == 200
                assert viewer.receive_json()['broadcast']['page'] == scene
            for style in ['classic', 'midnight', 'minimal']:
                response = c.post('/api/control', json={'action': 'set_overlay_style', 'overlay_style': style})
                assert response.status_code == 200
                state = viewer.receive_json()
                assert state['broadcast']['overlay_style'] == style
                assert state['broadcast']['page'] == 'result'
            assert c.post('/api/control', json={'action': 'set_overlay_style', 'overlay_style': 'unknown'}).status_code == 422
