#!/usr/bin/env python3
"""#11 in-game test: edits through four codecs, checked on screen by OCR (work/harness/ingame.py).

usage: t_shell_edits.py PRISTINE_SHELL.VOL OUTDIR [--asn WORK_ASN]

Builds from the pristine SHELL.VOL (volcodec) a copy with
  MENU.REQ   (reqcodec)  Association Data requester: caption "Association Data -" -> "League Data -",
                         label "Championship Trophy:" -> "World Series Trophy:" (same width: the label
                         gadget is 149 px wide, so a longer label is clipped, and the caption's right neighbour is
                         the name gadget at x=228, so a longer caption is overdrawn)
  MENU.DAT   (volmisc)   popup "Association" -> "Leagues", its entry "Statistics" -> "Stat Sheets"
  PREFSCRN.DAT (strtable) "Association Data" -> "Association Summary"
and from the work copy's league file (league.py) the trophy "The Dynamix Cup" -> "The Claude Cup", league
"National League" -> "Senior Circuit" and its "Eastern" division -> "Atlantic".
Then runs the game on :99, opens the league (Association Data screen), the Leagues menu and Preferences, and
asserts the new text is drawn and the old text is not. Every edited file is restored afterwards (ingame.py).
"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import reqcodec, strtable, volcodec, volmisc

WORK = '/mnt/nvme/bbpro98/work_install'


def one(xs, what):
    if len(xs) != 1:
        sys.exit(f'{what}: {len(xs)} matches')
    return xs[0]


def main():
    src, out = sys.argv[1], os.path.abspath(sys.argv[2])
    asn_in = sys.argv[sys.argv.index('--asn') + 1] if '--asn' in sys.argv else f'{WORK}/Assn/MLBPA97.ASN'
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='t11vol', dir=out) as td:
        volcodec.unpack(src, td)
        man = json.load(open(f'{td}/manifest.json'))
        path = {e['name']: f'{td}/{e["file"]}' for e in man['entries']}

        doc = reqcodec.decode(open(path['MENU.REQ'], 'rb').read())
        r = one([r for r in doc['requesters'] if r['id'] == 7], 'requester 7')
        one([c for c in r['captions'] if c['text'] == 'Association Data -'], 'caption')['text'] = 'League Data -'
        one([g for g in r['gadgets'] if g.get('label') == 'Championship Trophy:'], 'label')['label'] = 'World Series Trophy:'
        open(path['MENU.REQ'], 'wb').write(reqcodec.encode(doc))

        m = volmisc.menu_decode(open(path['MENU.DAT'], 'rb').read())
        pops = [p for bar in m['menus'] for p in bar['popups'] if p['title']['text'] == 'Association']
        if not pops:
            sys.exit('no Association popup')
        for p in pops:
            p['title']['text'] = 'Leagues'
            for e in p['entries']:
                if e.get('caption', {}).get('text') == 'Statistics':
                    e['caption']['text'] = 'Stat Sheets'
        open(path['MENU.DAT'], 'wb').write(volmisc.menu_encode(m))

        s = strtable.decode(open(path['PREFSCRN.DAT'], 'rb').read())
        sec = s['sections'][0]
        sec[sec.index('Association Data')] = 'Association Summary'
        open(path['PREFSCRN.DAT'], 'wb').write(strtable.encode(s))
        volcodec.pack(td, f'{out}/SHELL.VOL')

    subprocess.run([sys.executable, f'{os.path.dirname(HERE)}/league.py', 'decode', asn_in, f'{out}/asn.json'],
                   check=True)
    a = json.load(open(f'{out}/asn.json'))
    if a['association'][0]['trophy'] != 'The Dynamix Cup':
        sys.exit(f'unexpected trophy {a["association"][0]["trophy"]!r}')
    a['association'][0]['trophy'] = 'The Claude Cup'
    lg = one([l for l in a['leagues'] if l['name'] == 'National League'], 'league')
    lg['name'] = 'Senior Circuit'
    one([d for d in a['divisions'] if d['key'] in lg['divisions'] and d['name'] == 'Eastern'], 'division')['name'] = \
        'Atlantic'
    json.dump(a, open(f'{out}/asn.json', 'w'))
    subprocess.run([sys.executable, f'{os.path.dirname(HERE)}/league.py', 'encode', asn_in, f'{out}/asn.json',
                    f'{out}/MLBPA97.ASN'], check=True)

    top = [200, 300, 900, 60]                  # title + menu bar of the shell window
    plan = {'install': {'SHELL.VOL': f'{out}/SHELL.VOL', 'Assn/MLBPA97.ASN': f'{out}/MLBPA97.ASN'}, 'launch_wait': 22,
            'steps': [['click', 500, 677, 6], ['click', 643, 556, 5], ['click', 643, 566, 8], ['move', 900, 900],
                      ['ocr', 'assn_data', None, {'expect': ['League Data', 'World Series Trophy',
                                                             'The Claude Cup', 'Senior Circuit', 'Atlantic'],
                                                  'absent': ['Association Data', 'Dynamix', 'National League']}],
                      ['ocr', 'menubar', top, {'expect': ['Leagues'], 'absent': ['Association']}],
                      ['click', 447, 328, 1.5],
                      ['ocr', 'leagues_menu', [300, 320, 400, 260], {'expect': ['Stat Sheets'], 'absent': ['Statistics']}],
                      ['key', 'Escape', 1], ['key', 'ctrl+p', 5],
                      ['ocr', 'prefs', None, {'expect': ['Association Summary']}]]}
    json.dump(plan, open(f'{out}/plan.json', 'w'), indent=1)
    env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    sys.exit(subprocess.run([sys.executable, f'{HERE}/ingame.py', f'{out}/plan.json', f'{out}/shots'], env=env).returncode)


if __name__ == '__main__':
    main()
