"""Fictional two-innings cricket. All deliveries come from a seeded simulator."""
import random
from dataclasses import asdict, dataclass, field


@dataclass
class Batter:
    name: str
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    out: bool = False


@dataclass
class Innings:
    team: str
    players: list[Batter]
    runs: int = 0
    wickets: int = 0
    balls: int = 0
    extras: int = 0
    striker: int = 0
    non_striker: int = 1
    recent: list[str] = field(default_factory=list)


class Match:
    teams = ('Kathmandu Gurkhas', 'Pokhara Avengers')

    def __init__(self, seed=42, overs=20, teams=None):
        self.rng = random.Random(seed)
        self.overs = overs
        self.teams = tuple(teams or type(self).teams)
        self.lineups = [[], []]
        self.innings = [self.new_innings(0)]
        self.complete = False
        self.result = ''
        self.commentary = 'Simulation ready. Press Start or Next ball.'
        self.free_hit = False
        self.sequence = 0

    def new_innings(self, index):
        prefixes = {'Kathmandu Gurkhas': 'KTM', 'Pokhara Avengers': 'PKR'}
        prefix = prefixes.get(self.teams[index], self.teams[index][:3].upper())
        players = [Batter(f'{prefix} Player {i}') for i in range(1, 12)]
        if self.lineups[index]:
            players = [Batter(name) for name in self.lineups[index]]
        return Innings(self.teams[index], players)

    def step(self, outcome=None):
        if self.complete:
            return
        outcome = outcome or self.rng.choices(
            ['0', '1', '2', '3', '4', '6', 'W', 'Wd', 'Nb'],
            [30, 32, 10, 1, 12, 5, 5, 3, 2])[0]
        if outcome not in ('0', '1', '2', '3', '4', '6', 'W', 'Wd', 'Nb'):
            raise ValueError('Unknown delivery')
        inn = self.innings[-1]
        batter = inn.players[inn.striker]
        label = outcome
        if outcome in ('Wd', 'Nb'):
            inn.runs += 1
            inn.extras += 1
            if outcome == 'Nb':
                self.free_hit = True
            self.commentary = f'{outcome}: one extra, delivery does not count.'
        else:
            inn.balls += 1
            batter.balls += 1
            if outcome == 'W' and self.free_hit:
                label = '0 FH'
                self.commentary = 'Free hit: caught, but batter stays. Dot ball.'
            elif outcome == 'W':
                inn.wickets += 1
                batter.out = True
                self.commentary = f'{batter.name} is caught!'
                if inn.wickets < 10:
                    inn.striker = inn.wickets + 1
            else:
                runs = int(outcome)
                inn.runs += runs
                batter.runs += runs
                batter.fours += runs == 4
                batter.sixes += runs == 6
                self.commentary = f'{batter.name}: {runs} run(s).'
                if runs % 2:
                    inn.striker, inn.non_striker = inn.non_striker, inn.striker
            self.free_hit = False
            if inn.balls % 6 == 0:
                inn.striker, inn.non_striker = inn.non_striker, inn.striker
        inn.recent = (inn.recent + [label])[-12:]
        self.sequence += 1
        chased = len(self.innings) == 2 and inn.runs > self.innings[0].runs
        if chased or inn.wickets == 10 or inn.balls == self.overs * 6:
            if len(self.innings) == 1:
                self.innings.append(self.new_innings(1))
                self.free_hit = False
                self.commentary += f' Innings break. Target: {inn.runs + 1}.'
            else:
                self.complete = True
                first = self.innings[0].runs
                self.result = (f'{inn.team} win by {10 - inn.wickets} wickets' if chased else
                               'Match tied (no super over simulated)' if inn.runs == first else
                               f'{self.teams[0]} win by {first - inn.runs} runs')

    def snapshot(self):
        inn = self.innings[-1]
        data = asdict(inn)
        data['overs'] = f'{inn.balls // 6}.{inn.balls % 6}'
        data['run_rate'] = round(inn.runs * 6 / inn.balls, 2) if inn.balls else 0
        target = self.innings[0].runs + 1 if len(self.innings) == 2 else None
        left = self.overs * 6 - inn.balls
        return dict(simulation=True, sequence=self.sequence, teams=self.teams,
                    innings_number=len(self.innings), innings=[asdict(i) for i in self.innings],
                    current=data, max_overs=self.overs, target=target,
                    required_rate=round(max(0, target - inn.runs) * 6 / left, 2) if target and left else None,
                    balls_remaining=left, complete=self.complete, result=self.result,
                    free_hit=self.free_hit, commentary=self.commentary)
