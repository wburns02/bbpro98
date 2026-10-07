#!/usr/bin/env python3
"""
Read and parse FPS Baseball Pro '98 .ASN (Association) files.
Structure: Container with multiple data/index block pairs (a, l, d, t, r, s, xs, tr, df, po, sp).
Each block has .dat (data) and .idx (index) parts.
"""
import struct, sys

class ASNReader:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self.blocks = {}
        self._parse_directory()

    def _parse_directory(self):
        """Parse the directory that lists all data blocks.

        Directory format (rough):
        - Marker byte (0x3a or 0x3b): = or ;
        - Filename (e.g., "a.dat")
        - Offset info (variable length, u32 little-endian)
        - Size info (variable length)
        - Flags (u16?)
        """
        # The directory typically starts after the header and extends until the first data block
        # Look for ".dat" and ".idx" filenames with their offsets

        # Strategy: search for all instances of "?.dat" and "?.idx" patterns
        # and extract the bytes following them as offsets

        block_names = ['a', 'l', 'd', 't', 'r', 's', 'xs', 'tr', 'df', 'po', 'sp']

        for name in block_names:
            # Look for marker + name.dat
            for suffix in ['dat', 'idx']:
                searchkey = f'{name}.{suffix}'.encode()
                pos = self.data.find(searchkey)

                if pos >= 0:
                    # Extract offset bytes following the name (variable length)
                    # Based on observations: offset is typically 3-4 bytes LE after the name
                    off_start = pos + len(searchkey)

                    # Try to extract offset (skip padding/spaces first)
                    while off_start < len(self.data) and self.data[off_start:off_start+1].decode('latin1') in ' \x00':
                        off_start += 1

                    # Read offset (u32 LE)
                    if off_start + 4 <= len(self.data):
                        offset_candidate = struct.unpack('<I', self.data[off_start:off_start+4])[0]

                        # Sanity check: offset should be within file
                        if 0 < offset_candidate < len(self.data) - 100:
                            key = f'{name}.{suffix}'
                            self.blocks[key] = {
                                'name': name,
                                'type': suffix,
                                'dir_pos': pos,
                                'offset': offset_candidate
                            }

    def read_records_from_block(self, block_type):
        """Read record stream from a .dat block (same format as Stats DAT).

        Record format: 0xfafa marker, u32 total, u32 payload_len, u32 recno, u32 logical_off, payload
        """
        dat_key = f'{block_type}.dat'

        if dat_key not in self.blocks:
            return None

        offset = self.blocks[dat_key].get('offset')
        if offset is None:
            return None

        records = []
        i = offset

        while i < len(self.data) - 20:
            # Look for 0xfafa marker
            if self.data[i:i+2] == b'\xfa\xfa':
                total = struct.unpack('<I', self.data[i+2:i+6])[0]
                payload_len = struct.unpack('<I', self.data[i+6:i+10])[0]

                if total == payload_len + 18 and 0 < payload_len < 10000:
                    recno = struct.unpack('<I', self.data[i+10:i+14])[0]
                    payload = self.data[i+18:i+18+payload_len]
                    records.append({
                        'offset': i,
                        'recno': recno,
                        'payload_len': payload_len,
                        'payload': payload
                    })
                    i += 18 + payload_len
                else:
                    i += 1
            else:
                i += 1

        return records

    def get_leagues(self):
        """Extract league records (l.dat)."""
        return self.read_records_from_block('l')

    def get_divisions(self):
        """Extract division records (d.dat)."""
        return self.read_records_from_block('d')

    def get_teams(self):
        """Extract team records (t.dat)."""
        return self.read_records_from_block('t')

def format_payload(payload, max_bytes=64):
    """Format payload as hex and ASCII."""
    hex_str = ' '.join(f'{b:02x}' for b in payload[:max_bytes])
    ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload[:max_bytes])
    return f"{hex_str:<48} | {ascii_str}"

def main():
    if len(sys.argv) < 2:
        print("usage: asn_read.py <file.asn> [--verbose]")
        sys.exit(1)

    path = sys.argv[1]
    verbose = '--verbose' in sys.argv

    print(f"Reading: {path}")
    print(f"File size: {len(open(path, 'rb').read())} bytes\n")

    reader = ASNReader(path)

    print("="*80)
    print("ASN FILE STRUCTURE")
    print("="*80)

    print("\nBlocks found in directory:")
    for key in sorted(reader.blocks.keys()):
        info = reader.blocks[key]
        print(f"  {key:8s} @ dir:{info['dir_pos']:06x}  data:{info.get('offset', '?'):06x}")

    print("\n" + "="*80)
    print("LEAGUES (l.dat)")
    print("="*80)
    leagues = reader.get_leagues()
    if leagues:
        print(f"Found {len(leagues)} league records:")
        for i, rec in enumerate(leagues[:10]):
            print(f"  Rec {i}: recno={rec['recno']:3d} len={rec['payload_len']:4d} | {format_payload(rec['payload'])}")
        if len(leagues) > 10:
            print(f"  ... and {len(leagues) - 10} more")
    else:
        print("No league records found")

    print("\n" + "="*80)
    print("DIVISIONS (d.dat)")
    print("="*80)
    divisions = reader.get_divisions()
    if divisions:
        print(f"Found {len(divisions)} division records:")
        for i, rec in enumerate(divisions[:10]):
            print(f"  Rec {i}: recno={rec['recno']:3d} len={rec['payload_len']:4d} | {format_payload(rec['payload'])}")
        if len(divisions) > 10:
            print(f"  ... and {len(divisions) - 10} more")
    else:
        print("No division records found")

    print("\n" + "="*80)
    print("TEAMS (t.dat)")
    print("="*80)
    teams = reader.get_teams()
    if teams:
        print(f"Found {len(teams)} team records:")
        for i, rec in enumerate(teams[:15]):
            print(f"  Rec {i:2d}: recno={rec['recno']:3d} len={rec['payload_len']:4d} | {format_payload(rec['payload'])}")
        if len(teams) > 15:
            print(f"  ... and {len(teams) - 15} more")
    else:
        print("No team records found")

if __name__ == '__main__':
    main()
