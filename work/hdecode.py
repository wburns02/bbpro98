"""Decoder for FPS Baseball Pro '98 per-game box score files (Stats/MLBPA97.Hxx).

Usage: python3 hdecode.py <path-to-Hxx>   -> one JSON object on stdout.

Format (verified against day 2-7 truth; see HFILE_FORMAT.md for evidence):
  The file is a chain of tables, each: b"\\x02\\x65" | u16 unk | u16 count |
  u16 recsize, followed by count*recsize bytes. Records are little-endian u16
  arrays laid out exactly like the game's season stat lines minus the leading
  [scope, 2] pair:
      u16[0..1]  zeros
      u16[2]     id: player id, or team id (1..28) for team-total rows;
                 the away/second side has 0x8000 ORed in
      u16[3..]   stat columns (c0 = u16[3], same column order as season lines)
  recsize 40 = batting line, recsize 70 = pitching line, both plaintext.
  Only the first table (unk=0xffff, 1 x 2698 bytes) is obfuscated; it is not
  needed to score the game.

Player ids live in 100..2526; team totals use 1..28, so id < 100 is a team row.
Rows whose scored cells are all zero are players who appeared without a counted
stat (e.g. pinch runners); the per-day truth deltas exclude them, so skip them.
A pid is summed across its rows in one file (defensive: one row per player per
game in every observed file).
"""
import sys, json, struct


def tables(data):
    off = 0
    n = len(data)
    while off + 8 <= n:
        if data[off] != 0x02 or data[off + 1] != 0x65:
            break
        count, rec = struct.unpack_from('<HH', data, off + 4)
        body = off + 8
        end = body + count * rec
        if rec and end <= n:
            yield rec, body, count
        off = end


def rows(data, body, rec, count, nfields):
    for i in range(count):
        yield struct.unpack_from('<%dH' % nfields, data, body + i * rec)


def main():
    data = open(sys.argv[1], 'rb').read()
    bat, pit = {}, {}
    for rec, body, count in tables(data):
        if rec == 40:  # batting line
            for u in rows(data, body, rec, count, 20):
                pid = u[2] & 0x7FFF
                if pid < 100:
                    continue
                c = u[3:]
                d = bat.setdefault(pid, [0] * 8)
                d[0] += c[0]
                d[1] += c[1] + c[2] + c[3] + c[4]
                d[2] += c[4]
                d[3] += c[5]
                d[4] += c[6]
                d[5] += c[7]
                d[6] += c[13]
                d[7] += c[14]
        elif rec == 70:  # pitching line
            for u in rows(data, body, rec, count, 35):
                pid = u[2] & 0x7FFF
                if pid < 100:
                    continue
                c = u[3:]
                d = pit.setdefault(pid, [0] * 7)
                d[0] += c[18]
                d[1] += c[19]
                d[2] += c[1] + c[2] + c[3] + c[4]
                d[3] += c[4]
                d[4] += c[6]
                d[5] += c[7]
                d[6] += c[13]
    keys = ('ab', 'h', 'hr', 'rbi', 'bb', 'so', 'r', 'sb')
    batters = [dict(zip(('pid',) + keys, (pid,) + tuple(v)))
               for pid, v in bat.items() if any(v)]
    pkeys = ('outs', 'bf', 'h', 'hr', 'bb', 'so', 'r')
    pitchers = [dict(zip(('pid',) + pkeys, (pid,) + tuple(v)))
                for pid, v in pit.items() if any(v)]
    print(json.dumps({'batters': batters, 'pitchers': pitchers}))


if __name__ == '__main__':
    main()
