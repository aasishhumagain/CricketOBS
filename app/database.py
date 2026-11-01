import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / 'data' / 'cricketobs.sqlite3'
SEED_PATH = Path(__file__).with_name('npl_2026_rosters.json')


@contextmanager
def _connection(database_path=DATABASE_PATH):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path=DATABASE_PATH):
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    seed = json.loads(SEED_PATH.read_text(encoding='utf-8'))
    with _connection(database_path) as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS teams (
                slug TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                short_name TEXT NOT NULL,
                season INTEGER NOT NULL,
                source_url TEXT NOT NULL,
                source_published TEXT NOT NULL,
                logo_url TEXT NOT NULL DEFAULT ''
            );
        ''')
        team_columns = {row['name'] for row in connection.execute('PRAGMA table_info(teams)')}
        if 'logo_url' not in team_columns:
            connection.execute("ALTER TABLE teams ADD COLUMN logo_url TEXT NOT NULL DEFAULT ''")

        player_columns = {row['name'] for row in connection.execute('PRAGMA table_info(players)')}
        if not player_columns:
            _create_players_table(connection)
        else:
            if 'photo_url' not in player_columns:
                connection.execute("ALTER TABLE players ADD COLUMN photo_url TEXT NOT NULL DEFAULT ''")
            if 'profile_url' not in player_columns:
                connection.execute("ALTER TABLE players ADD COLUMN profile_url TEXT NOT NULL DEFAULT ''")
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'players'"
            ).fetchone()['sql']
            if "'Not listed'" not in table_sql:
                connection.execute('ALTER TABLE players RENAME TO players_legacy')
                _create_players_table(connection)
                connection.execute('''
                    INSERT INTO players (id, team_slug, name, role, category, is_captain,
                                         source_url, photo_url, profile_url)
                    SELECT id, team_slug, name, role, category, is_captain,
                           source_url, photo_url, profile_url
                    FROM players_legacy
                ''')
                connection.execute('DROP TABLE players_legacy')

        if connection.execute('SELECT COUNT(*) FROM teams').fetchone()[0] == 0:
            _insert_seed(connection, seed)


def get_roster(database_path=DATABASE_PATH):
    with _connection(database_path) as connection:
        rows = connection.execute('''
            SELECT t.slug, t.name AS team_name, t.short_name, t.season,
                     t.source_url, t.source_published, t.logo_url,
                   p.id AS player_id, p.name AS player_name, p.role,
                     p.category, p.is_captain, p.photo_url, p.profile_url
            FROM teams AS t
            LEFT JOIN players AS p ON p.team_slug = t.slug
            ORDER BY t.name, p.is_captain DESC, p.name COLLATE NOCASE
        ''').fetchall()

    teams = {}
    for row in rows:
        team = teams.setdefault(row['slug'], {
            'slug': row['slug'],
            'name': row['team_name'],
            'short_name': row['short_name'],
            'season': row['season'],
            'source_url': row['source_url'],
            'source_published': row['source_published'],
            'logo_url': row['logo_url'],
            'players': [],
        })
        if row['player_id'] is not None:
            team['players'].append({
                'id': row['player_id'],
                'name': row['player_name'],
                'role': row['role'],
                'category': row['category'],
                'captain': bool(row['is_captain']),
                'photo_url': row['photo_url'],
                'profile_url': row['profile_url'],
            })
    return list(teams.values())


def import_roster(seed, database_path=DATABASE_PATH, seed_path=SEED_PATH):
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with _connection(database_path) as connection:
        for team in seed['teams']:
            connection.execute('''
                INSERT INTO teams
                    (slug, name, short_name, season, source_url, source_published, logo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    name = excluded.name,
                    short_name = excluded.short_name,
                    season = excluded.season,
                    source_url = excluded.source_url,
                    source_published = excluded.source_published,
                    logo_url = excluded.logo_url
            ''', (team['slug'], team['name'], team['short_name'], seed['season'],
                  seed['source'], seed['source_published'], team.get('logo_url', '')))
            connection.execute(
                "DELETE FROM players WHERE team_slug = ? AND source_url != 'user-added'",
                (team['slug'],),
            )
            for player in team['players']:
                connection.execute('''
                    INSERT INTO players
                        (team_slug, name, role, category, is_captain, source_url,
                         photo_url, profile_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (team['slug'], player['name'], player.get('role', ''),
                      player.get('category', 'Not listed'), int(player.get('captain', False)),
                      seed['source'], player.get('photo_url', ''), player.get('profile_url', '')))

    Path(seed_path).write_text(json.dumps(seed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def add_player(team_slug, name, role='', category='Domestic', captain=False,
               database_path=DATABASE_PATH):
    with _connection(database_path) as connection:
        if connection.execute('SELECT 1 FROM teams WHERE slug = ?', (team_slug,)).fetchone() is None:
            raise LookupError('Unknown team')
        try:
            cursor = connection.execute(
                     '''INSERT INTO players
                         (team_slug, name, role, category, is_captain, source_url)
                         VALUES (?, ?, ?, ?, ?, 'user-added')''',
                (team_slug, name.strip(), role, category, int(captain)),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError('That player is already on this roster') from error
        row = connection.execute(
                '''SELECT id, name, role, category, is_captain AS captain,
                             photo_url, profile_url
               FROM players WHERE id = ?''', (cursor.lastrowid,),
        ).fetchone()
        player = dict(row)
        player['captain'] = bool(player['captain'])
        return player


def delete_player(team_slug, player_id, database_path=DATABASE_PATH):
    with _connection(database_path) as connection:
        cursor = connection.execute(
            'DELETE FROM players WHERE id = ? AND team_slug = ?',
            (player_id, team_slug),
        )
        return cursor.rowcount > 0


def _create_players_table(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_slug TEXT NOT NULL REFERENCES teams(slug) ON DELETE CASCADE,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL CHECK (category IN ('Domestic', 'Overseas', 'Not listed')),
            is_captain INTEGER NOT NULL DEFAULT 0,
            source_url TEXT NOT NULL,
            photo_url TEXT NOT NULL DEFAULT '',
            profile_url TEXT NOT NULL DEFAULT '',
            UNIQUE (team_slug, name)
        )
    ''')


def _insert_seed(connection, seed):
    for team in seed['teams']:
        connection.execute('''
            INSERT OR IGNORE INTO teams
                (slug, name, short_name, season, source_url, source_published, logo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (team['slug'], team['name'], team['short_name'], seed['season'],
              seed['source'], seed['source_published'], team.get('logo_url', '')))
        for player in team['players']:
            connection.execute('''
                INSERT OR IGNORE INTO players
                    (team_slug, name, role, category, is_captain, source_url,
                     photo_url, profile_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (team['slug'], player['name'], player.get('role', ''),
                  player.get('category', 'Not listed'), int(player.get('captain', False)),
                  seed['source'], player.get('photo_url', ''), player.get('profile_url', '')))