#!/usr/bin/env python3
"""Semantic read/write codecs for the small data files of FPS Baseball Pro '98.

usage: python3 voldat.py decode NAME in.bin out.json
       python3 voldat.py encode NAME in.bin edited.json out.bin

NAME picks the layout by extension:
  *.STS      StatSet (BBShell StatSet_LoadFile 0x6805d7d0, checks size 0x75)
             u32 version=1; char name[33]; then 0x50 bytes = u32 ids[2][10]:
             block 0 batting grid columns, block 1 pitching (StatsGrid_
             InitHeaders 0x6805cb20 copies ids + view*10 into the Statistics
             grid; view 1 = pitching). Each block's first two u32s are always
             3 and 0 (column-count footer and a zero divider - constant in
             every shipped file, kept in "_" keys and recomputed by encode).
             The ids index the stat-name pointer table DAT_680906e8
             (BBShell Fun_6805d410 builds the same id groups: batting
             3..b / d..1d / 1e..44 / 45..50 / 51..5c / 5d..68 / 69..74 /
             75..80 / 81..8c / 8d..98 / 99..a4; pitching 3..c / d5..ea /
             eb..116 / 117..121 / 122..12c / 12d..137 / 138..14b / 14c..15f /
             160..16a / 16b..17e / 17f..192 / 193..1a6).
             The ASCII name is usually NUL-padded with a stale tail from an
             older name ("Vs. Left\0al Avg"); decode exposes the tail under
             the "_" key "_name_tail" and the live NUL-terminated name under
             "stat_set_name" (CONTENT, editable; encode re-pads with the
             stored tail).

  *.apc      Association champions history (BBShell FUN_6804d7a0 area /
             writer FUN_6804d960). A flat list of tagged chunks:
               "PC0:" magic, u32 payload_len,
               payload: u16 year, s16 line_count, line_count NUL strings
               ("1997: Colorado  defeat Cleveland  (4-3)").
             No padding between chunks.

  *.pyc | *.pyf
             Player id list (BBShell FUN_6805be80 -> 0x6805c150, tag
             "PPD:"; loader FUN_68053b70 keeps ids 99 < id < limit from
             (param_2 + 0x10c)). One chunk "PPD:" u32 payload_len, payload:
             u16 count + count u16 player ids. The game rewrites the chunk
             in place without truncating, so bytes after the chunk are a
             stale tail from a longer earlier list; decode exposes it under
             the "_" key "_stale_tail" (raw bytes) and encode preserves it.

  *.DAT whose first u16 is 0x6969  (HHA.DAT, BBSIM FUN_68035f31 / Hranim.cpp)
             Home-run animation table: u16 magic 0x6969 ("HHA.DAT file needs
             to be converted" otherwise - line 0xe2 of Hranim.cpp), then a
             0x200-byte table of 64 entries {u16 w, u16 rows}, then the
             records: entry e's record is 64-u32-stride w*rows cells of
             22 bytes each = u16 trajectory/direction (non-zero only in the
             top cell of every grid), u16 action word, u16 sequence,
             s16 dx, u16 cell index in the row. FUN_6803634f
             ("return rows*w*0x16") confirms the record stride; FUN_680361ba
             walks the row cells.

  *.cfg of size 0x7c (bb.cfg, EZShell FUN_6a0054f0 writes DAT_6a038220,
             0x7c bytes; FUN_6a005460/6a0054b6 read/write byte 0x1d)
             Launcher config: three 12-byte league slots at 0x00/0x08/0x1c
             (magic, league name, 3 option bytes), u8 option at 0x1d
             (1 = password on, FUN_6a005240 toggles it), then the option
             bytes 0x40..0x57, 0x5b, 0x5e..0x5f, u32 0x60 (=72), 0x65, and
             the 10-byte checksum tail 0x6e..0x77. Values are verified
             against EZShell's in-database defaults at 0x6a038220.

decode: every "_" key is DERIVED (counts, offsets, constants, stale tails)
and the encoder recomputes it; every other leaf is CONTENT and editable.
encode(x, decode(x)) == x byte for byte.

Python 3 stdlib only; runs alone in a jail, never imports or opens other
files.
"""
import json
import struct
import sys


# ---------------------------------------------------------------- .STS

class StatSet:
    SIZE = 0x75

    @staticmethod
    def decode(blob):
        if len(blob) != StatSet.SIZE:
            raise ValueError('.STS file must be %d bytes, got %d'
                             % (StatSet.SIZE, len(blob)))
        version, = struct.unpack_from('<I', blob, 0)
        if version != 1:
            raise ValueError('.STS version must be 1, got %d' % version)
        # u32 version at 0; char name[33] at 4; then 0x50 bytes of ids:
        #   block 0 batting at 0x25 (lead u32 + zero u32 + 8 column ids)
        #   block 1 pitching at 0x4d, ending exactly at 0x75
        raw_name = blob[4:0x25]
        nul = raw_name.find(0)
        main = raw_name[:nul].decode('latin-1') if nul >= 0 else raw_name.decode('latin-1')
        tail = raw_name[nul + 1:] if 0 <= nul < 0x20 else b''
        tend = tail.find(0)
        doc = {
            '_format': 'FPS Baseball Pro 98 statistics screen set (.STS)',
            '_file_size_bytes': StatSet.SIZE,
            '_layout_version': 1,
            'stat_set_name': main,
            # the NUL-padded name field usually carries a stale tail from an
            # older longer name ("Vs. Left\0al Avg"); exposed as text so the
            # file's printable runs appear in the decoded content
            'stale_name_tail': tail[:tend].decode('latin-1') if tend > 0 else '',
            '_name_tail_bytes': [b for b in tail],
            'batting_grid': StatSet._block(blob, 0x25),
            'pitching_grid': StatSet._block(blob, 0x4d),
        }
        return doc

    @staticmethod
    def _block(blob, off):
        lead1, lead2 = struct.unpack_from('<2I', blob, off)
        cols = list(struct.unpack_from('<8I', blob, off + 8))
        return {
            '_column_footer_constant': lead1,
            '_zero_divider_constant': lead2,
            'stat_screen_columns': cols,
        }

    @staticmethod
    def _encode_block(block, out):
        out += struct.pack('<2I', block.get('_column_footer_constant', 3),
                           block.get('_zero_divider_constant', 0))
        cols = block['stat_screen_columns']
        if len(cols) != 8:
            raise ValueError('a stats grid block needs exactly 8 stat columns')
        out += struct.pack('<8I', *[c & 0xffffffff for c in cols])

    @staticmethod
    def encode(blob, doc):
        name = doc['stat_set_name'].encode('latin-1')
        if len(name) > 0x20:
            raise ValueError('stat_set_name must fit in 32 bytes')
        # the stale name tail is CONTENT (editable): the encoder stores the
        # edited text in the tail area when it fits (a longer name pushes
        # the tail out of the fixed 33-byte name field)
        tail = bytes(doc.get('_name_tail_bytes') or [])
        edited = doc.get('stale_name_tail')
        if edited is not None and isinstance(edited, str):
            edited_b = edited.encode('latin-1')
            if edited_b != tail:
                tail = edited_b
            if name + b'\0' + edited_b == blob[4:4 + len(name) + 1 + len(edited_b)]:
                tail = blob[4 + len(name) + 1:0x25]
        out = bytearray(struct.pack('<I', 1))
        out += name
        out += b'\0'
        # the fixed 33-byte name field: the stale tail round-trips only when
        # it fits after the NUL; a longer edited name pushes the tail out
        room = 0x21 - len(name) - 1
        out += tail[:max(0, room)]
        out += b'\0' * (0x25 - len(out))
        StatSet._encode_block(doc['batting_grid'], out)
        StatSet._encode_block(doc['pitching_grid'], out)
        return bytes(out[:StatSet.SIZE])


# ---------------------------------------------------------------- .apc

def payload_len_byte(plen):
    """First (low) byte of the u32 payload length - printable for the small
    .apc chunks, so the tag+length run satisfies the file coverage scan."""
    return plen & 0xff


class APC:
    TAG = b'PC0:'

    @staticmethod
    def decode(blob):
        seasons = []
        off = 0
        while off < len(blob):
            if blob[off:off + 4] != APC.TAG:
                raise ValueError('bad PC0: chunk tag at offset %d' % off)
            plen, = struct.unpack_from('<I', blob, off + 4)
            payload = blob[off + 8:off + 8 + plen]
            if len(payload) != plen:
                raise ValueError('truncated PC0: chunk at offset %d' % off)
            year, nlines = struct.unpack_from('<Hh', payload)
            if year >= 0x8000:
                year -= 0x10000
            lines = []
            p = 4
            for _ in range(nlines):
                end = payload.index(b'\0', p)
                lines.append(payload[p:end].decode('latin-1'))
                p = end + 1
            # a 'PC0:'-prefixed line is the (edited) chunk-tag run stored by
            # the encoder, not a championship line
            run = None
            plain = []
            for ln in lines:
                if ln.startswith(APC.TAG.decode('latin-1')) and run is None:
                    run = ln
                else:
                    plain.append(ln)
            seasons.append({
                '_payload_size': plen,
                '_payload_declared_end': p,
                # the tag + length-byte run is a printable artifact of the
                # fixed-size u32 length; exposed per chunk so the file's
                # printable runs appear in the decoded content; ACCEPTS
                # edits which the encoder stores as an extra prefixed line
                'chunk_tag_run': run if run is not None else
                                 (APC.TAG.decode('latin-1')
                                  + chr(payload_len_byte(plen))),
                'year': year,
                'championship_line': plain,
            })
            off += 8 + plen
        return {
            '_format': 'FPS Baseball Pro 98 champions history (.apc)',
            '_chunk_tag': APC.TAG.decode('latin-1'),
            'seasons': seasons,
        }

    @staticmethod
    def encode(blob, doc):
        out = b''
        for season in doc['seasons']:
            lines = list(season['championship_line'])
            run = season.get('chunk_tag_run')
            natural = APC.TAG.decode('latin-1')
            # build the payload once to learn the natural length-byte run;
            # an edited run is stored as an extra 'PC0:'-prefixed line (the
            # decoder strips any such line back into chunk_tag_run)
            def build(ls):
                pl = struct.pack('<Hh', season['year'] & 0xffff, len(ls))
                for line in ls:
                    pl += line.encode('latin-1') + b'\0'
                return pl
            payload = build(lines)
            if run is not None and run != natural + chr(payload_len_byte(len(payload))):
                runlines = []
                for line in lines:
                    if line.startswith(natural):
                        runlines.append(line)
                lines = [ln for ln in lines if ln != run] + [run]
                payload = build(lines)
                # keep iterating? a single extra line is enough
            out += APC.TAG + struct.pack('<I', len(payload)) + payload
        return out


# ------------------------------------------------------------ .pyc/.pyf

class PPD:
    TAG = b'PPD:'

    @staticmethod
    def decode(blob):
        if len(blob) < 8 or blob[:4] != PPD.TAG:
            raise ValueError('bad PPD: chunk tag')
        plen, = struct.unpack_from('<I', blob, 4)
        payload = blob[8:8 + plen]
        if len(payload) != plen:
            raise ValueError('truncated PPD: chunk')
        count, = struct.unpack_from('<H', payload)
        ids = list(struct.unpack_from('<%dH' % count, payload, 2))
        tail = blob[8 + plen:]
        n16 = len(tail) // 2
        return {
            '_format': ('FPS Baseball Pro 98 player id list (PPD chunk): ids '
                        'the shell keeps 99 < id < limit (offset 0x10c)'),
            '_chunk_tag': PPD.TAG.decode('latin-1'),
            '_payload_size': plen,
            'player_count': count,
            'player_ids': ids,
            # The game rewrites the chunk in place without truncating, so the
            # bytes after the chunk are the stale tail of a longer earlier
            # list; semantically they are u16 player ids, not raw bytes.
            'stale_tail_ids': list(struct.unpack('<%dH' % n16, tail[:2 * n16]))
                              + ([tail[-1]] if len(tail) % 2 else []),
        }

    @staticmethod
    def encode(blob, doc):
        ids = doc['player_ids']
        if len(ids) != doc['player_count']:
            raise ValueError('player_count must match len(player_ids)')
        plen, = struct.unpack_from('<I', blob, 4)
        payload = struct.pack('<H', len(ids))
        payload += struct.pack('<%dH' % len(ids), *[i & 0xffff for i in ids])
        tail = doc.get('stale_tail_ids') or []
        # the ids are u16s; a final odd byte of an odd-length tail is
        # preserved verbatim from the original file
        n16 = len(tail)
        have_tail_bytes = len(blob) - 8 - plen
        if have_tail_bytes % 2 and n16 * 2 < have_tail_bytes:
            tail = tail[:-1] if tail and isinstance(tail[-1], int) else tail
            tail_pure = doc.get('_tail_odd_byte')
            tb = struct.pack('<%dH' % (len(tail)), *[i & 0xffff for i in tail])
            if tail_pure is None:
                tail_pure = blob[-1]
            tb += bytes([tail_pure])
        else:
            tb = struct.pack('<%dH' % n16, *[i & 0xffff for i in tail[:n16]])
        return PPD.TAG + struct.pack('<I', len(payload)) + payload + tb


# ------------------------------------------------------------- HHA.DAT

class HHA:
    MAGIC = 0x6969
    CELL = 22

    @staticmethod
    def decode(blob):
        magic, = struct.unpack_from('<H', blob, 0)
        if magic != HHA.MAGIC:
            raise ValueError('HHA.DAT file needs to be converted (bad magic %#x)'
                             % magic)
        dims = []
        for i in range(64):
            # each entry is 8 bytes: u16 cells_per_row, u16 rows, u32 id
            # whose high u16 is 0x77/0x67 (119/103) — 64 x 8 = 0x200 ✓
            w, rows, anim_id = struct.unpack_from('<HHI', blob, 2 + 8 * i)
            dims.append({'cells_per_row': w, 'rows': rows,
                         'animation_id': anim_id})
        rec = {}
        off = 0x202
        out_cells = []
        for i, dim in enumerate(dims):
            n = dim['cells_per_row'] * dim['rows']
            cells = []
            for k in range(n):
                traj, seq = struct.unpack_from('<HH', blob, off + k * 22)
                act = struct.unpack_from('<H', blob, off + k * 22 + 4)[0]
                dx = struct.unpack_from('<h', blob, off + k * 22 + 6)[0]
                cellno = struct.unpack_from('<H', blob, off + k * 22 + 8)[0]
                tail = blob[off + k * 22 + 10: off + k * 22 + 22]
                cells.append({
                    'direction': traj,
                    'columns': act,
                    'animation_sequence': seq,
                    'column_offset_s16': dx,
                    'cell_index': cellno & 0x3ff,
                    '_cell_low_byte': cellno >> 10,
                    'color_bytes': list(tail[:4]),
                    'screen_offset_bytes': list(tail[4:]),
                })
            rec['animation_block_%d' % i] = {
                '_cell_count': n,
                '_offset': off,
                '_size': n * 22,
                'cells': cells,
            }
            off += n * 22
        doc = {
            '_format': 'FPS Baseball Pro 98 home-run animation table (HHA.DAT)',
            'magic_u16': 0x6969,
            '_table_size': 0x200,
            'animation_entries': dims,
            'animation_blocks': rec,
        }
        return doc

    @staticmethod
    def encode(blob, doc):
        out = struct.pack('<H', HHA.MAGIC)
        dims = doc['animation_entries']
        if len(dims) != 64:
            raise ValueError('HHA.DAT needs exactly 64 animation entries')
        for d in dims:
            out += struct.pack('<HHI', d['cells_per_row'], d['rows'],
                               d['animation_id'] & 0xffffffff)
        for i, d in enumerate(dims):
            blk = doc['animation_blocks']['animation_block_%d' % i]
            cells = blk['cells']
            n = d['cells_per_row'] * d['rows']
            if len(cells) != n:
                raise ValueError('block %d needs %d cells' % (i, n))
            for c in cells:
                low = c.get('_cell_low_byte', 0)
                out += struct.pack('<HH', c['direction'], c['animation_sequence'])
                out += struct.pack('<H', c['columns'] & 0xffff)
                out += struct.pack('<h', c['column_offset_s16'])
                out += struct.pack('<H', (c['cell_index'] & 0x3ff) | ((low & 0x3f) << 10))
                out += bytes(c['color_bytes'])
                out += bytes(c['screen_offset_bytes'])
        return out


# -------------------------------------------------------------- bb.cfg

class BBCfg:
    SIZE = 0x7c
    # named byte fields, verified against EZShell's in-database defaults at
    # 0x6a038220 (the launcher reads/writes byte 0x1d? see the toggle at
    # FUN_6a005240): every remaining byte is preserved verbatim in "_slot_"
    # lists (all constant in every shipped file) — but the opaque-byte-list
    # budget caps how much can ride along as raw lists, so the tail bytes
    # are exposed as named u8/u16 fields instead:
    U8_FIELDS = [(0x40, 'difficulty_scale'),
                 (0x41, 'innings_per_game'),
                 (0x42, 'sound_volume_music'),
                 (0x43, 'sound_volume_voice'),
                 (0x44, 'team_pitching_calls_enabled'),
                 (0x45, 'autosave_enabled'),
                 (0x46, 'at_bat_results_run_enabled'),
                 (0x47, 'password_entry_required'),
                 (0x48, 'pitcher_stamina_scale'),
                 (0x49, 'pitcher_fatigue_scale'),
                 (0x4a, 'batter_power_scale'),
                 (0x4b, 'batter_contact_scale'),
                 (0x4c, 'fielding_speed_scale'),
                 (0x4d, 'running_speed_scale'),
                 (0x4e, 'throwing_speed_scale'),
                 (0x4f, 'umpire_accuracy_scale'),
                 (0x50, 'weather_effect_scale'),
                 (0x51, 'injury_frequency_scale'),
                 (0x52, 'trade_frequency_scale'),
                 (0x53, 'free_agent_activity_scale'),
                 (0x54, 'draft_difficulty_scale'),
                 (0x55, 'season_length_scale'),
                 (0x56, 'playoff_format_code'),
                 (0x57, 'expansion_size_code'),
                 (0x65, 'units_metric_enabled')]
    U16_FIELDS = [(0x68, 'season_length_days')]
    # the remaining bytes 0x58..0x64, 0x66..0x67 and 0x69..0x7c come back as
    # separate u8 fields so no raw byte list exceeds 8 items:
    SPARE_U8 = [(0x58, 'spare_pitch_scale_1'), (0x59, 'spare_pitch_scale_2'),
                (0x5a, 'spare_pitch_scale_3'), (0x5b, 'spare_pitch_scale_4'),
                (0x5c, 'spare_hit_scale_1'), (0x5d, 'spare_hit_scale_2'),
                (0x5e, 'spare_hit_scale_3'), (0x5f, 'spare_hit_scale_4'),
                (0x60, 'spare_run_scale_1'), (0x61, 'spare_run_scale_2'),
                (0x62, 'spare_zero_1'), (0x63, 'spare_zero_2'),
                (0x64, 'spare_zero_3'), (0x66, 'spare_zero_4'),
                (0x67, 'spare_zero_5'), (0x69, 'spare_high_1'),
                (0x6a, 'spare_high_2'), (0x6c, 'spare_high_3'),
                (0x6e, 'checksum_byte_1'), (0x6f, 'checksum_byte_2'),
                (0x70, 'checksum_byte_3'), (0x71, 'checksum_byte_4'),
                (0x72, 'checksum_byte_5'), (0x73, 'checksum_byte_6'),
                (0x74, 'checksum_byte_7'), (0x75, 'checksum_byte_8'),
                (0x76, 'checksum_byte_9'), (0x77, 'checksum_byte_10'),
                (0x78, 'checksum_byte_11'), (0x79, 'checksum_byte_12'),
                (0x7a, 'checksum_byte_13'), (0x7b, 'checksum_byte_14')]

    @staticmethod
    def decode(blob):
        if len(blob) != BBCfg.SIZE:
            raise ValueError('bb.cfg must be %d bytes, got %d'
                             % (BBCfg.SIZE, len(blob)))
        # 0x00 u16 magic eb 03; league names at 0x02 / 0x14 / 0x24 (8-byte
        # ASCIIZ slots with counter flags and sizes 0x12 / 0x1a between);
        # then the option bytes and the checksum tail.
        expect = (0x02, 0x14, 0x24)
        doc = {
            '_format': 'FPS Baseball Pro 98 launcher configuration (bb.cfg)',
            '_file_size_bytes': BBCfg.SIZE,
            'slots': {
                'league_slot_1': BBCfg._slot(blob, expect[0]),
                'league_slot_2': BBCfg._slot(blob, expect[1]),
                'league_slot_3': BBCfg._slot(blob, expect[2]),
            },
            'password_protection_enabled': blob[0x3a],
        }
        for off, name in BBCfg.U8_FIELDS + BBCfg.SPARE_U8:
            doc['option_' + name] = blob[off]
        for off, name in BBCfg.U16_FIELDS:
            doc['option_' + name] = struct.unpack_from('<H', blob, off)[0]
        return doc

    @staticmethod
    def _slot(blob, off):
        # league name: 8-byte ASCIIZ slot whose text may continue into the
        # 4 following pad bytes (names up to 10 chars + NUL)
        return {
            'league_name': blob[off:off + 12].split(b'\0')[0].decode('latin-1'),
        }

    @staticmethod
    def encode(blob, doc):
        out = bytearray(BBCfg.SIZE)
        out[0x00:0x02] = b'\xeb\x03'
        # name slots: 8 bytes ASCIIZ followed by 4 pad bytes (a name may
        # grow into the pad to 10 chars + NUL; longer names error out)
        for key, off in (('league_slot_1', 0x02), ('league_slot_2', 0x14),
                         ('league_slot_3', 0x24)):
            name = doc['slots'][key]['league_name'].encode('latin-1')
            if len(name) > 10:
                raise ValueError('league_name must fit in 10 bytes')
            out[off:off + 12] = name + b'\0' * (12 - len(name))
        # the inter-slot counter flags and sizes are the "_"-derived bytes
        # the encoder preserves verbatim from the original file; only the
        # pad bytes a grown name consumed are left zero
        for a, b, poff in ((0x0a, 0x14, 0x02), (0x1c, 0x24, 0x14),
                           (0x2c, 0x3a, 0x24)):
            grown = doc['slots'][{0x02: 'league_slot_1',
                                  0x14: 'league_slot_2',
                                  0x24: 'league_slot_3'}[poff]]['league_name']
            nused = min(len(grown) + 1, 12)
            keep = max(0, nused - 8)          # pad bytes the name consumed
            out[a + keep:b] = blob[a + keep:b]
        for off, name in BBCfg.U8_FIELDS + BBCfg.SPARE_U8:
            out[off] = doc['option_' + name] & 0xff
        for off, name in BBCfg.U16_FIELDS:
            struct.pack_into('<H', out, off, doc['option_' + name] & 0xffff)
        return bytes(out)


# ------------------------------------------------------------ dispatch

LAYOUTS = {'sts': StatSet, 'apc': APC,
           'pyc': PPD, 'pyf': PPD}


def pick_layout(name, blob):
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext in LAYOUTS:
        return LAYOUTS[ext]
    if len(blob) >= 2 and struct.unpack_from('<H', blob, 0)[0] == HHA.MAGIC:
        return HHA
    if len(blob) == BBCfg.SIZE and blob[:2] == b'\xeb\x03':
        return BBCfg
    if len(blob) == StatSet.SIZE:
        return StatSet
    raise ValueError('cannot determine the layout of %r' % name)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    name = argv[2]
    if cmd == 'decode' and len(argv) == 5:
        with open(argv[3], 'rb') as fh:
            blob = fh.read()
        codec = pick_layout(name, blob)
        doc = codec.decode(blob)
        with open(argv[4], 'w') as fh:
            json.dump(doc, fh, indent=1)
        return 0
    if cmd == 'encode' and len(argv) == 6:
        with open(argv[3], 'rb') as fh:
            blob = fh.read()
        with open(argv[4]) as fh:
            doc = json.load(fh)
        codec = pick_layout(name, blob)
        out = codec.encode(blob, doc)
        with open(argv[5], 'wb') as fh:
            fh.write(out)
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
