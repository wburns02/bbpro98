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
        if _has_lgid(con, table):
            out.update(r[0] for r in con.execute(
                'SELECT DISTINCT teamID FROM %s WHERE yearID = ? AND lgID IN (%s)' % (table, marks),
                (year,) + tuple(leagues)))
    return out


def _has_lgid(con, table):
    return 'lgid' in {r[1].lower() for r in con.execute('PRAGMA table_info(%s)' % table)}   # constants only


def stints(con, year, leagues):
    """{playerID: [teamID, ...]} for the players of year with two or more distinct teams in leagues, each list in stint
    order: a team sits at the lowest stint number Batting or Pitching gives it (a missing number counts as 1; ties go to
    teamID). Rows count when their own lgID is in leagues (Batting and Pitching carry it in Lahman); without that column
    a team counts when appearances or teams put it in leagues. So a player split between a major and a minor club has
    one team and is left out. Players come in playerID order."""
    marks = ','.join('?' * len(leagues))
    by_row = _has_lgid(con, 'batting') and _has_lgid(con, 'pitching')
    cond = ' AND lgID IN (%s)' % marks if by_row else ''
    args = ((year,) + tuple(leagues)) if by_row else (year,)
    rows = con.execute('''
        SELECT playerID, teamID, MIN(COALESCE(stint, 1)) FROM (
            SELECT playerID, teamID, stint FROM batting WHERE yearID = ?%s
            UNION ALL
            SELECT playerID, teamID, stint FROM pitching WHERE yearID = ?%s)
        GROUP BY playerID, teamID''' % (cond, cond), args + args).fetchall()
    in_lg = None if by_row else _league_teams(con, year, leagues)
    seen = {}
    for pid, team, stint in rows:
        if in_lg is None or team in in_lg:
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
