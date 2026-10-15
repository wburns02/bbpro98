"""runreport.py: summarize a season run log (one JSON object per line)."""
import json
import sys

def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse(text):
    if not isinstance(text, str):
        return []
    out = []
    for line in text.splitlines():
        if not line.startswith('{'):
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def summary(lines):
    demo = []
    champions = []
    seasons = []
    verdicts = {}
    postseason = {}
    stops = 0
    first = None
    last = None
    prev_age = None
    for obj in lines:
        if not isinstance(obj, dict):
            continue
        t = obj.get('t')
        if isinstance(t, str):
            if first is None:
                first = t
            last = t
        if 'demographics' in obj:
            row = {key: obj.get(key) for key in ('k', 'year', 'rostered', 'mean_age',
                                                 'le25', 'ge33', 'fa', 'retired',
                                                 'players', 'roster_min', 'pitchers_min')}
            row['k'] = obj.get('demographics')
            if is_num(row['mean_age']) and is_num(prev_age):
                row['step'] = round(row['mean_age'] - prev_age, 2)
            else:
                row['step'] = None
            if is_num(row['mean_age']):
                prev_age = row['mean_age']
            demo.append(row)
        if 'at' in obj and 'champion' in obj:
            champions.append({key: obj.get(key) for key in
                              ('at', 'season', 'champion', 'runner_up', 'series', 'error')})
        if 'season' in obj and 'done' in obj:
            seasons.append({'stem': obj.get('season'),
                            'done': obj.get('done'),
                            'played': obj.get('played'),
                            'rounds': obj.get('rounds'),
                            'stops': obj.get('stops'),
                            'timeout': bool(obj.get('timeout')),
                            'wrong_association': bool(obj.get('wrong_association'))})
        v = obj.get('verdict')
        if isinstance(v, str) and ('progress' in obj or obj.get('postseason') == 'waiting'):
            verdicts[v] = verdicts.get(v, 0) + 1
        p = obj.get('postseason')
        if isinstance(p, str):
            postseason[p] = postseason.get(p, 0) + 1
        if 'stop' in obj:
            stops += 1
    return {'demographics': demo, 'champions': champions, 'seasons': seasons,
            'verdicts': verdicts, 'postseason': postseason, 'stops': stops,
            'first': first, 'last': last}


def _cell(v):
    return '-' if v is None else str(v)


def render(s):
    out = []
    out.append('Demographics')
    out.append('year       rostered  mean age  step  le25  ge33    fa  retired  players')
    for r in s.get('demographics', []):
        age = '-' if not is_num(r.get('mean_age')) else '%.2f' % r['mean_age']
        step = r.get('step')
        step = '-' if step is None else ('%+.2f' % step)
        out.append('%9s  %8s  %8s  %5s  %4s  %4s  %4s  %7s  %7s' % (
            _cell(r.get('year')), _cell(r.get('rostered')), age, step,
            _cell(r.get('le25')), _cell(r.get('ge33')), _cell(r.get('fa')),
            _cell(r.get('retired')), _cell(r.get('players'))))
    out.append('')
    out.append('Champions')
    rows = s.get('champions', [])
    if not rows:
        out.append('none')
    for r in rows:
        if r.get('error') is not None and r.get('champion') is None:
            out.append('%s error: %s' % (_cell(r.get('season')), _cell(r.get('error'))))
        elif r.get('champion') is None:
            out.append('%s no champion yet' % _cell(r.get('season')))
        else:
            out.append('%s %s over %s %s' % (
                _cell(r.get('season')), _cell(r.get('champion')), _cell(r.get('runner_up')),
                _cell(r.get('series'))))
    out.append('')
    out.append('Seasons')
    rows = s.get('seasons', [])
    if not rows:
        out.append('none')
    for r in rows:
        if r.get('timeout'):
            out.append('%s: timeout' % _cell(r.get('stem')))
        elif r.get('wrong_association'):
            out.append('%s: wrong association' % _cell(r.get('stem')))
        else:
            out.append('%s: done %s, played %s, rounds %s, stops %s' % (
                _cell(r.get('stem')), _cell(r.get('done')), _cell(r.get('played')),
                _cell(r.get('rounds')), _cell(r.get('stops'))))
    out.append('')
    out.append('Verdicts')
    if not s.get('verdicts'):
        out.append('none')
    for k in sorted(s.get('verdicts', {})):
        out.append('%s: %d' % (k, s['verdicts'][k]))
    out.append('')
    out.append('Postseason')
    if not s.get('postseason'):
        out.append('none')
    for k in sorted(s.get('postseason', {})):
        out.append('%s: %d' % (k, s['postseason'][k]))
    out.append('')
    out.append('Stops: %d' % s.get('stops', 0))
    out.append('Span: %s to %s' % (_cell(s.get('first')), _cell(s.get('last'))))
    return '\n'.join(out)


def main(argv):
    args = [a for a in argv if a != '--json']
    json_mode = args != argv
    if len(args) != 1 or args[0].startswith('-'):
        print('usage: runreport.py LOG [--json]', file=sys.stderr)
        return 2
    path = args[0]
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError as exc:
        print('runreport: %s: %s' % (path, exc.strerror or exc), file=sys.stderr)
        return 2
    s = summary(parse(text))
    if json_mode:
        print(json.dumps(s))
    else:
        print(render(s))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
