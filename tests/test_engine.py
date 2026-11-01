from app.engine import Match


def test_strike_and_over_notation():
    m = Match()
    assert m.snapshot()['teams'] == ('Kathmandu Gurkhas', 'Pokhara Avengers')
    assert m.innings[0].players[0].name == 'KTM Player 1'
    m.step('1')
    assert m.innings[0].striker == 1
    for _ in range(5):
        m.step('0')
    assert m.snapshot()['current']['overs'] == '1.0'
    assert m.innings[0].striker == 0


def test_extras_and_free_hit():
    m = Match()
    for ball in ['Nb', 'Wd', 'W']:
        m.step(ball)
    i = m.innings[0]
    assert (i.runs, i.extras, i.balls, i.wickets) == (2, 2, 1, 0)
    m.step('W')
    assert i.wickets == 1 and i.players[0].out and i.striker == 2


def test_all_out_and_chase():
    m = Match()
    for _ in range(10):
        m.step('W')
    assert len(m.innings) == 2
    assert m.snapshot()['target'] == 1
    m.step('Wd')
    assert m.complete and '10 wickets' in m.result
    before = m.snapshot()
    m.step('6')
    assert before == m.snapshot()


def test_tie_and_defended_total():
    m = Match(overs=1)
    for _ in range(12):
        m.step('0')
    assert m.complete and 'tied' in m.result
    m = Match(overs=1)
    for _ in range(6):
        m.step('1')
    for _ in range(6):
        m.step('0')
    assert '6 runs' in m.result


def test_many_seeded_matches_reconcile():
    for seed in range(100):
        m = Match(seed=seed)
        for _ in range(2000):
            m.step()
            i = m.innings[-1]
            assert i.runs == sum(p.runs for p in i.players) + i.extras
            assert i.balls == sum(p.balls for p in i.players)
            assert 0 <= i.wickets <= 10 and i.balls <= 120
            if m.complete:
                break
        assert m.complete
    a, b = Match(), Match()
    for _ in range(30):
        a.step()
        b.step()
    assert a.snapshot() == b.snapshot()
