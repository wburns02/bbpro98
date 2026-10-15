"""Real midseason moves from Lahman stints: which players changed teams in a season, in what order, and how far into
the season. stints reads the Batting and Pitching stint numbers, moves_for turns a player's stints into moves placed by
his games played, first_team names the club he started with. Pure apart from the one SQL read in stints; the build
(build.py --moves) writes the result as a MOV file and news/roster.py applies it between sessions.
"""

AT_MIN, AT_MAX = 0.05, 0.95        # a move never happens before 5% or after 95% of the season


def _league_teams(con, year, leagues):
    """The teamIDs of year in leagues, by the lgID of appearances and of teams (each table that has the column)."""
    marks = ','.join('?' * len(leagues))
    out = set()
    for table in ('appearances', 'teams'):         # constants, never caller input
        if 'lgid' in {r[1].lower() for r in con.execute('PRAGMA table_info(%s)' % table)}:
            out.update(r[0] for r in con.execute(
                'SELECT DISTINCT teamID FROM %s WHERE yearID = ? AND lgID IN (%s)' % (table, marks),
                (year,) + tuple(leagues)))
    return out


def stints(con, year, leagues):
    """{playerID: [teamID, ...]} for the players of year with two or more distinct teams in leagues, each list in stint
    order: a team sits at the lowest stint number Batting or Pitching gives it (a missing number counts as 1; ties go to
    teamID). A team that is in no league of leagues does not count, so a player split between a major and a minor
    club has one team and is left out. Players come in playerID order."""
    in_lg = _league_teams(con, year, leagues)
    rows = con.execute('''
        SELECT playerID, teamID, MIN(COALESCE(stint, 1)) FROM (
            SELECT playerID, teamID, stint FROM batting WHERE yearID = ?
            UNION ALL
            SELECT playerID, teamID, stint FROM pitching WHERE yearID = ?)
        GROUP BY playerID, teamID''', (year, year)).fetchall()
    seen = {}
    for pid, team, stint in rows:
        if team in in_lg:
            seen.setdefault(pid, []).append((stint, team))
    return {pid: [team for _, team in sorted(v)] for pid, v in sorted(seen.items()) if len(v) >= 2}


def moves_for(stint_map, app, team_games):
    """[{"player", "from", "to", "at"}] sorted by (at, player, from): one move for each consecutive pair of a player's
    teams. at is the player's G_all summed over his teams up to and including "from" (app is lahdb.appearances: a
    missing team or count is 0) over team_games[from], rounded to 3 places and held to AT_MIN..AT_MAX. A move whose
    "from" team has no positive game count in team_games is left out."""
    out = []
    for pid, teams in stint_map.items():
        played = 0
        for frm, to in zip(teams, teams[1:]):
            played += app.get(pid, {}).get(frm, {}).get('G_all', 0)
            games = team_games.get(frm)
            if not games or games < 0:
                continue
            at = min(max(round(played / games, 3), AT_MIN), AT_MAX)
            out.append({'player': pid, 'from': frm, 'to': to, 'at': at})
    return sorted(out, key=lambda m: (m['at'], m['player'], m['from']))


def first_team(stint_map):
    """{playerID: teamID}: the team each player started the season with (his stint 1 team)."""
    return {pid: teams[0] for pid, teams in stint_map.items()}
