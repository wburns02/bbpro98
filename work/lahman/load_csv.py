"""Load a SABR Lahman CSV release into a new SQLite file with the schema the old lahmansbaseballdb.sqlite uses.

The CSV releases (2024 onward) dropped the surrogate keys the SQL edition carried (ID, team_ID, park_ID, div_ID),
renamed teamRank to Rank and dropped batting.G_batting and the *_date columns. build.py and lahdb.py query the old
names, so this copies every CREATE TABLE and CREATE INDEX from a reference database and fills the derived columns:

    usage: python3 -m work.lahman.load_csv --csv DIR --ref OLD.sqlite --out NEW.sqlite

The reference is opened read-only. --out must not exist. Every value is bound with ?; table and column names come
from the reference schema and the CSV header, and a header name that is not a reference column is an error.
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
from pathlib import Path

# CSV header name -> reference column, where they differ (after case folding).
RENAMES = {'rank': 'teamRank'}

# CSV columns the reference schema has no place for: (table, lower-case header).
SKIP = {('people', 'id')}

# Leagues the reference lacks (Negro Leagues and the independent pseudo-leagues), from readme2025.txt section 1.
EXTRA_LEAGUES = {
    'ANL': 'American Negro League', 'EAS': 'Eastern Independent Clubs', 'ECL': 'Eastern Colored League',
    'EWL': 'East-West League', 'IND': 'Independent Clubs', 'INT': 'Independent Clubs (INT)',
    'NAC': 'Independent Clubs (NAC)', 'NAL': 'Negro American League', 'NN2': 'Negro National League II',
    'NNL': 'Negro National League I', 'NSL': 'Negro Southern League', 'WES': 'Western Independent Clubs',
}

DATE_COLS = {'birth_date': ('birthYear', 'birthMonth', 'birthDay'), 'death_date': ('deathYear', 'deathMonth',
                                                                                    'deathDay')}

# Unique keys the CSV release breaks, index name (without quotes) -> reason. Anything not listed here stops the load.
RELAXED = {
    'awardsplayers_playerID': 'weekly and monthly awards (Player of the Week, Player of the Month, '
                              'Rookie of the Month) repeat for one player within a season',
}


def ref_schema(ref):
    tables = {}
    for name, sql in ref.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        cols = [r[1] for r in ref.execute('SELECT * FROM pragma_table_info(?)', (name,))]
        tables[name] = (sql, cols)
    indexes = [sql for (sql,) in ref.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL ORDER BY name")]
    return tables, indexes


def csv_files(csv_dir):
    return {p.stem.lower(): p for p in Path(csv_dir).iterdir() if p.suffix.lower() == '.csv'}


_INT = re.compile(r'[+-]?[0-9]+')
_REAL = re.compile(r'[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?')


def _text_affinity(decl):
    """SQLite's affinity rule 2: a declared type containing CHAR, CLOB or TEXT (and not INT) stores text."""
    d = (decl or '').upper()
    return 'INT' not in d and any(k in d for k in ('CHAR', 'CLOB', 'TEXT'))


def _value(s, text=False):
    """One CSV cell: None when blank, the stripped string for a text column, else int, then a finite float.

    Only plain decimal digits count as numbers ('1_000', 'nan' and 'inf' stay strings), and a text column never
    loses leading zeros or a trailing '.0' to a number round trip."""
    s = s.strip()
    if s == '':
        return None
    if text:
        return s
    if _INT.fullmatch(s):
        return int(s)
    if _REAL.fullmatch(s):
        return float(s)
    return s


def load_table(con, table, cols, path):
    lower = {c.lower(): c for c in cols}
    types = dict(con.execute('SELECT name, type FROM pragma_table_info(?)', (table,)))
    with open(path, newline='', encoding='utf-8-sig') as fh:
        rd = csv.reader(fh)
        header = next(rd, None)
        if not header:
            raise SystemExit('%s: empty file, no header row' % path.name)
        mapped, keep = [], []
        for i, h in enumerate(header):
            key = RENAMES.get(h.lower(), h).lower()
            if (table, key) in SKIP:
                continue
            keep.append(i)
            if key not in lower:
                raise SystemExit('%s: column %r is not in the reference table %s' % (path.name, h, table))
            mapped.append(lower[key])
        text = [_text_affinity(types.get(c)) for c in mapped]
        quoted = ', '.join('"%s"' % c for c in mapped)
        marks = ', '.join('?' * len(mapped))
        n = 0
        for row in rd:
            if not any(x.strip() for x in row):
                continue
            if len(row) != len(header):
                raise SystemExit('%s line %d: %d fields, header has %d' % (path.name, rd.line_num, len(row),
                                                                         len(header)))
            con.execute('INSERT INTO "%s" (%s) VALUES (%s)' % (table, quoted, marks),
                        [_value(row[i], t) for i, t in zip(keep, text)])
            n += 1
    return n


def _has(cols, name):
    return name in cols


def derive(con, tables):
    """Fill the surrogate and derived columns the CSV edition no longer carries."""
    # Surrogate ids: rowid order, which is CSV order.
    for t, (_, cols) in tables.items():
        if _has(cols, 'ID') and t not in ('people', 'parks', 'divisions'):
            con.execute('UPDATE "%s" SET ID = rowid WHERE ID IS NULL' % t)
    # team_ID -> teams.ID by (yearID, teamID); lgID is not needed, teamID is unique within a year.
    for t, (_, cols) in tables.items():
        if t != 'teams' and _has(cols, 'team_ID') and _has(cols, 'teamID') and _has(cols, 'yearID'):
            con.execute('''UPDATE "%s" SET team_ID = (SELECT tm.ID FROM teams tm
                           WHERE tm.yearID = "%s".yearID AND tm.teamID = "%s".teamID)''' % (t, t, t))
    if 'homegames' in tables:
        con.execute('''UPDATE homegames SET
                         team_ID = (SELECT tm.ID FROM teams tm WHERE tm.yearID = homegames.yearkey
                                    AND tm.teamID = homegames.teamkey),
                         park_ID = (SELECT p.ID FROM parks p WHERE p.parkkey = homegames.parkkey),
                         spanfirst_date = spanfirst, spanlast_date = spanlast''')
    if 'seriespost' in tables:
        for side in ('winner', 'loser'):
            con.execute('''UPDATE seriespost SET team_ID%s = (SELECT tm.ID FROM teams tm
                           WHERE tm.yearID = seriespost.yearID AND tm.teamID = seriespost.teamID%s)''' % (side, side))
    if 'divisions' in tables and 'teams' in tables:
        con.execute('''UPDATE teams SET div_ID = (SELECT d.ID FROM divisions d
                       WHERE d.lgID = teams.lgID AND d.divID = teams.divID)''')
    # G_batting was dropped from batting; appearances still carries it per (player, year, team).
    if 'batting' in tables and _has(tables['batting'][1], 'G_batting'):
        con.execute('''UPDATE batting SET G_batting = (SELECT a.G_batting FROM appearances a
                       WHERE a.playerID = batting.playerID AND a.yearID = batting.yearID
                         AND a.teamID = batting.teamID)''')
    if 'people' in tables:
        for col, (y, m, d) in DATE_COLS.items():
            con.execute('''UPDATE people SET %s = printf('%%04d-%%02d-%%02d', %s, %s, %s)
                           WHERE %s IS NOT NULL AND %s IS NOT NULL AND %s IS NOT NULL''' % (col, y, m, d, y, m, d))
        con.execute('UPDATE people SET debut_date = substr(debut, 1, 10), finalgame_date = substr(finalGame, 1, 10)')


def copy_lookup(con, ref, table):
    cols = [r[1] for r in ref.execute('SELECT * FROM pragma_table_info(?)', (table,))]
    quoted = ', '.join('"%s"' % c for c in cols)
    marks = ', '.join('?' * len(cols))
    for row in ref.execute('SELECT %s FROM "%s"' % (quoted, table)):
        con.execute('INSERT INTO "%s" (%s) VALUES (%s)' % (table, quoted, marks), row)


def load(csv_dir, ref_path, out_path, log=print):
    out_path = Path(out_path)
    if out_path.exists():
        raise SystemExit('%s exists; refusing to overwrite' % out_path)
    ref = sqlite3.connect(Path(ref_path).resolve().as_uri() + '?mode=ro', uri=True)
    tables, indexes = ref_schema(ref)
    files = csv_files(csv_dir)
    tmp = out_path.with_name(out_path.name + '.part')
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(str(tmp))
    try:
        for sql, _ in tables.values():
            # The CSV edition leaves some key columns blank (allstarfull.gameNum); keep the shape, drop NOT NULL.
            con.execute(sql.replace(' NOT NULL', ' NULL'))
        counts = {}
        for t, (_, cols) in tables.items():
            if t in files:
                counts[t] = load_table(con, t, cols, files[t])
            elif t in ('leagues', 'divisions'):
                copy_lookup(con, ref, t)
                counts[t] = con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
            else:
                raise SystemExit('no CSV for table %s' % t)
        have = {r[0] for r in con.execute('SELECT lgID FROM leagues')}
        for lg, name in sorted(EXTRA_LEAGUES.items()):
            if lg not in have:
                con.execute("INSERT INTO leagues (lgID, league, active) VALUES (?, ?, 'N')", (lg, name))
        for sql in indexes:
            try:
                con.execute(sql)
            except sqlite3.IntegrityError:
                name = sql.split(' ON ')[0].split()[-1].strip('"')
                if name not in RELAXED:
                    raise SystemExit('unique key %s broken by the release; check the data, then add it to '
                                     'load_csv.RELAXED with the reason' % name)
                # Keep the index for speed, without the constraint; see RELAXED.
                con.execute(sql.replace('CREATE UNIQUE INDEX', 'CREATE INDEX', 1))
                log('not unique: %s (%s)' % (name, RELAXED[name]))
        # derive()'s correlated lookups need these; the reference indexes do not cover them all.
        helpers = {'_load_teams_key': 'teams (yearID, teamID)', '_load_parks_key': 'parks (parkkey)',
                   '_load_app_key': 'appearances (playerID, yearID, teamID)'}
        helpers = {k: v for k, v in helpers.items() if v.split()[0] in tables}
        for name, on in helpers.items():
            con.execute('CREATE INDEX IF NOT EXISTS %s ON %s' % (name, on))
        derive(con, tables)
        for name in helpers:
            con.execute('DROP INDEX %s' % name)
        con.commit()
        os.replace(tmp, out_path)
    finally:
        con.close()
        ref.close()
        if tmp.exists():
            tmp.unlink()
    for t in sorted(counts):
        log('%-22s %8d rows' % (t, counts[t]))
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--csv', required=True, help='directory of the release CSV files')
    ap.add_argument('--ref', required=True, help='reference database with the target schema (opened read-only)')
    ap.add_argument('--out', required=True, help='new SQLite file to write')
    a = ap.parse_args(argv)
    load(a.csv, a.ref, a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
