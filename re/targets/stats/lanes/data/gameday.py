#!/usr/bin/env python3
"""Identify split tables: compare day01 team rows with schedule home/away and starter handedness."""
import sys, struct, collections, os
sys.path.insert(0, '/home/will/bbpro98/work')
import league as L
import explore
from explore import DATA, load_names
from box import box_files, box_rows_for
import asnref as A

explore.NAMES.update(load_names())

def day_games(day_dir):
    """Played games from the day's ASN: [(home, away, hr, ar, month, day)]"""
    doc = L.build_json(L.parse_container(open(f'{day_dir}/MLBPA97.ASN', 'rb').read()))
    out = []
    for g in doc['games']:
        if g['played']:
            out.append(g)
    return doc, out

def game_pitchers(hfile):
    """From a box file: per side, [(pid, w, l, outs, g, gs?)] for rec 70 rows; side tid."""
    rows = list(A.h_tables(open(hfile, 'rb').read()))
    sides = {}
    pits = []
    for rec, u in rows:
        pid, side = u[2] & 0x7fff, u[2] >> 15
        if pid < 100:
            sides[side] = pid
    for rec, u in rows:
        pid, side = u[2] & 0x7fff, u[2] >> 15
        if rec == 70 and pid >= 100 and side in sides:
            pits.append((sides[side], pid, explore.NAMES.get(pid, ('?',))[0], list(u[3:])))
    return pits

if __name__ == '__main__':
    day = sys.argv[1] if len(sys.argv) > 1 else 'day01'
    dd = f'{DATA}/{day}'
    doc, games = day_games(dd)
    print(f'{len(games)} played games in {day} ASN')
    for g in games[:12]:
        print(f"  game month {g['month']} day {g['day']} slot {g['slot']}: {g['away']} @ {g['home']}  {g['ar']}-{g['hr']}")
    print('== pitchers per box file (side tid, pid, name, outs, w, l)')
    for f in box_files(dd):
        for tid, pid, nmm, row in game_pitchers(f):
            print(f"  {os.path.basename(f)}: team {tid:2d} {nmm:22s} outs {row[18]:2d} w {row[20]} l {row[21]} g {row[12]}")
