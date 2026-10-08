"""Referee for re/targets/tapnames (Claude-owned): tapnameref.py <target> <lane> [--audit DIR].

Grades lanes/<lane>/NAMES.json, the proposed names for the tape fields tapcodec still calls at_0x... It runs no lane
code. Mechanical checks only (meaning is judged by the audit): every field present, a snake_case non-placeholder name
unique among its struct's keys, a meaning of real length, and evidence quotes that occur verbatim (whitespace
collapsed) in the cited BBSIM function body, at least one of them at a use site rather than the tape copy routines."""
import json, os, re, stat, sys

INDEX = '/mnt/nvme/bbpro98/index'
# field paths, and the keys each struct already uses (a new name must not collide with them)
FIELDS = ['actor.at_0x2e', 'camera.at_0x58', 'camera.at_0x5b', 'camera.at_0x61', 'camera.at_0x67',
          'ball.at_0x50', 'ball.at_0x52', 'ball.at_0x44', 'ball.at_0x40', 'ball.at_0x4c', 'sim.at_0xe92', 'sim.at_0xea8',
          'fielders.at_0x2a5', 'fielders.at_0x2a9', 'offense.at_0x2b9', 'offense.at_0x2a9', 'offense.at_0x2ad',
          'offense.at_0x2b1', 'record.at_0x1d', 'pitch.at_0x3390', 'pitch.at_0x3394', 'state.at_0x00',
          'snapshot.at_0x7e', 'ball_flight.at_0xe70', 'path.at_0xe78', 'path.at_0xe7c', 'path.at_0xe80',
          'path.at_0xe84', 'path.at_0xe88']
ACTOR = ['x', 'y', 'z', 'heading', 'animation']
KEYS = {'actor': ACTOR, 'camera': ['angle_0x11', 'angle_0x15', 'position'], 'ball': ['state', 'position', 'velocity'],
        'sim': ['global_b80b4'], 'fielders': ACTOR, 'offense': ACTOR,
        'record': ['ball', 'sim', 'fielding_0x2f', 'fielders', 'offense', 'umpires', 'pitch', 'global_ec180',
                   'global_ec194', 'stack_pad'], 'pitch': [],
        'state': ['batting_side', 'teams', 'balls', 'strikes', 'outs', 'inning', 'clock'],
        'snapshot': ['state', 'team_records', 'game', 'stadium_dat', 'fielders', 'offense'],
        'ball_flight': ['path'], 'path': ['points', 'n']}
# names that share one struct: an actor's own field sits beside the fielder/offense extras
GROUP = {'actor': ('actor', 'fielders', 'offense'), 'fielders': ('actor', 'fielders'), 'offense': ('actor', 'offense')}
# the tape writer/reader and plain copy helpers: they show where a field is stored, not what it means
COPY_FNS = {'FUN_680737fc', 'FUN_680736c4', 'FUN_6807adde', 'FUN_68079aee', 'FUN_68079e75', 'FUN_6807ac99',
            'FUN_680157e8', 'FUN_680490ca', 'FUN_680ac376', 'FUN_680ac3f7', 'FUN_68048e56', 'FUN_6802d8a3',
            'FUN_6805de6a', 'FUN_68078374', 'FUN_68047f66', 'FUN_68005985', 'FUN_68079de6', 'FUN_6806eed4',
            'FUN_6800972a', 'FUN_6804d42d', 'FUN_6806a8d4',
            # their membuf_read counterparts (the tape loaders): also storage, not use
            'FUN_68048d50', 'FUN_68048f5c', 'FUN_680782e1', 'FUN_68047f0b', 'FUN_68047fc5', 'FUN_6804d3e9',
            'FUN_680095f8', 'FUN_6806ee85', 'FUN_680156ca', 'FUN_6805ddac', 'FUN_6800588c', 'FUN_6802d82d',
            'FUN_6806a749'}
NAME_RE = re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$')
PLACEHOLDER = re.compile(r'(^|_)(at|unk|unknown|field|var|param|local|dat|fun|misc|tmp|temp|todo|x[0-9a-f]+|'
                         r'(?=[0-9a-f]*[0-9])[0-9a-f]{3,})($|_)|0x')


def norm(s): return ' '.join(s.split())


def bodies():
    out, cur, buf = {}, None, []
    with open(os.path.join(INDEX, 'BBSIM', '_all.c'), errors='replace') as fh:
        for line in fh:
            m = re.match(r'// ==== ([0-9a-f]{8}) (\S+)', line)
            if m:
                if cur: out[cur] = norm(''.join(buf))
                cur, buf = m.group(2), []
            elif cur:
                buf.append(line)
    if cur: out[cur] = norm(''.join(buf))
    return out


def load(lane):
    fd = os.open(os.path.join(lane, 'NAMES.json'), os.O_RDONLY | os.O_NOFOLLOW)
    if not stat.S_ISREG(os.fstat(fd).st_mode): raise OSError('NAMES.json is not a regular file')
    data = os.read(fd, 400001); os.close(fd)
    if len(data) > 400000: raise ValueError('NAMES.json over 400 KB')
    return json.loads(data)


def check(d, fns):
    errs = []
    if not isinstance(d, dict): return ['top level is not an object'], 0
    extra = sorted(set(d) - set(FIELDS))
    if extra: errs.append(f'unknown field paths: {extra[:5]}')
    ok, chosen = 0, {}
    for path in FIELDS:
        sibs = KEYS[path.split('.')[0]]
        e = d.get(path)
        if not isinstance(e, dict): errs.append(f'{path}: missing'); continue
        bad = []
        name, meaning, conf, ev = e.get('name'), e.get('meaning'), e.get('confidence'), e.get('evidence')
        if not isinstance(name, str) or not NAME_RE.match(name) or not 3 <= len(name) <= 40:
            bad.append('name is not snake_case 3..40')
        elif PLACEHOLDER.search(name):
            bad.append(f'placeholder-like name {name!r}')
        elif name in sibs:
            bad.append(f'name {name!r} collides with an existing key of the struct')
        if not isinstance(meaning, str) or len(norm(meaning)) < 20: bad.append('meaning under 20 characters')
        if conf not in ('high', 'medium', 'low'): bad.append('confidence not high/medium/low')
        if not isinstance(ev, list) or not 1 <= len(ev) <= 6:
            bad.append('evidence must be a list of 1..6 items')
        else:
            use = False
            for i, q in enumerate(ev):
                if not isinstance(q, dict) or not isinstance(q.get('function'), str) or not isinstance(q.get('quote'), str):
                    bad.append(f'evidence[{i}] needs function and quote'); continue
                fn, quote = q['function'], norm(q['quote'])
                if fn not in fns: bad.append(f'evidence[{i}]: no BBSIM function {fn}'); continue
                if len(quote) < 15: bad.append(f'evidence[{i}]: quote under 15 characters'); continue
                if quote not in fns[fn]: bad.append(f'evidence[{i}]: quote not found in {fn}'); continue
                if fn not in COPY_FNS: use = True
            if not use and e.get('code_use') == 'none':
                # no use site exists (the offset appears only in the tape save/load pair): allowed when said so,
                # marked low, and the meaning rests on the tape values
                if conf != 'low': bad.append('code_use none needs confidence low')
                if 'tape' not in str(meaning).lower(): bad.append('code_use none: the meaning must cite the tape values')
            elif not use:
                bad.append('no evidence at a use site (every cited function is a tape/copy routine); '
                           'if the field has none, say so with "code_use": "none"')
        if bad: errs.append(f'{path}: ' + '; '.join(bad))
        else:
            ok += 1; chosen.setdefault(path.split('.')[0], []).append(name)
    for struct in chosen:
        names = [n for g in GROUP.get(struct, (struct,)) for n in chosen.get(g, [])]
        dup = sorted({n for n in chosen[struct] if names.count(n) > 1})
        if dup: errs.append(f'{struct}: duplicate names {dup}'); ok -= len(dup)
    return errs, ok


def main():
    lane = sys.argv[2]
    audit = '--audit' in sys.argv
    try:
        d = load(lane)
    except (OSError, ValueError) as e:
        print(f'cannot read NAMES.json: {e}'); print('FAIL'); return 1
    fns = bodies()
    errs, ok = check(d, fns)
    if audit:
        for path in FIELDS:
            e = d.get(path) or {}
            print(f'== {path} -> {e.get("name")} [{e.get("confidence")}]\n   {norm(str(e.get("meaning")))}')
            for q in e.get('evidence') or []:
                if isinstance(q, dict): print(f'   {q.get("function")}: {norm(str(q.get("quote")))[:300]}')
        print()
    print(f'fields {len(FIELDS)} ok {ok}')
    for x in errs[:30]: print('  ' + x)
    print('PASS' if not errs and ok == len(FIELDS) else 'FAIL')
    return 0 if not errs else 1


if __name__ == '__main__':
    sys.exit(main())
