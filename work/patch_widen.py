#!/usr/bin/env python3
"""
Patch to expand FPS Baseball Pro '98 Statistics screen from 8 to 12 columns.

Restore: cp /mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06/*.dll /home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98/

Patches applied:
1. BBShell.dll:
   - 0x5ba22: Change dialog button loop from 8 to 12 (mov edi, 0x7 -> mov edi, 0xb)
   - 0x5cebe: Change file read loop from 10 to 14 u32s (mov ecx, 0xa -> mov ecx, 0xe)
   - 0x5cf4a: Change file write loop from 10 to 14 u32s (mov ecx, 0xa -> mov ecx, 0xe)
   - 0x41d0f: Adjust grid column pitch from 50 to 40 px (imul cx, cx, 0x32 -> imul cx, cx, 0x28)

2. STS files: Regenerate with 12-column format (56 bytes per section instead of 40)
"""

import struct
import os
import sys
from pathlib import Path

def patch_file(dll_path, orig_path, patches):
    """Apply binary patches to a DLL file."""
    # Read original DLL
    with open(orig_path, 'rb') as f:
        data = bytearray(f.read())

    # Apply each patch
    for addr, orig_bytes, new_bytes, desc in patches:
        # Verify original bytes
        actual = bytes(data[addr:addr+len(orig_bytes)])
        if actual != orig_bytes:
            print(f"ERROR at 0x{addr:08x}: expected {orig_bytes.hex()}, got {actual.hex()}")
            print(f"  {desc}")
            return False

        # Apply patch
        data[addr:addr+len(new_bytes)] = new_bytes
        print(f"Patched 0x{addr:08x}: {desc}")

    # Write patched DLL
    with open(dll_path, 'wb') as f:
        f.write(data)

    return True

def create_sts_file(path, name, batting_ids, pitching_ids):
    """Create a new STS file with 12-column format."""
    # Batting section: header (3) + filler (0) + 12 IDs
    batting_data = struct.pack('<I', 3)  # header
    batting_data += struct.pack('<I', 0)  # filler
    for id_val in batting_ids:
        batting_data += struct.pack('<I', id_val)
    # Pad with zeros if less than 12
    while len(batting_data) < 56:
        batting_data += struct.pack('<I', 0)

    # Pitching section: header (3) + filler (0) + 12 IDs
    pitching_data = struct.pack('<I', 3)  # header
    pitching_data += struct.pack('<I', 0)  # filler
    for id_val in pitching_ids:
        pitching_data += struct.pack('<I', id_val)
    # Pad with zeros if less than 12
    while len(pitching_data) < 56:
        pitching_data += struct.pack('<I', 0)

    # Build complete file: version (4) + name (33) + batting (56) + pitching (56) = 149 bytes
    data = struct.pack('<I', 1)  # version
    name_bytes = name.encode('utf-8')[:32]  # max 32 chars + null
    name_bytes += b'\0' * (33 - len(name_bytes))
    data += name_bytes
    data += batting_data
    data += pitching_data

    with open(path, 'wb') as f:
        f.write(data)
    print(f"Created {path} ({len(data)} bytes)")

def main():
    # Paths
    backup_dir = Path('/mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06')
    install_dir = Path('/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98')
    orig_dir = Path('/home/will/bbpro98/work/orig')

    # BBShell.dll patches
    # File offsets calculated from RVA: offset = RVA - VA + section_offset
    # ImageBase = 0x68000000, .text VA = 0x1000, .text file offset = 0x400
    bbshell_orig = orig_dir / 'BBShell.dll.orig'
    bbshell_live = install_dir / 'BBShell.dll'

    bbshell_patches = [
        # Patch 1: Change dialog button loop from 8 to 12
        # Memory: 0x6805c622, RVA: 0x5c622, File: 0x5ba22
        (0x5ba22, b'\xbf\x07\x00\x00\x00', b'\xbf\x0b\x00\x00\x00', 'Dialog: 8 buttons -> 12 buttons'),

        # Patch 2: Change file read loop from 10 to 14 u32s
        # Memory: 0x6805dabe, RVA: 0x5dabe, File: 0x5cebe
        (0x5cebe, b'\xb9\x0a\x00\x00\x00', b'\xb9\x0e\x00\x00\x00', 'File read: 10 u32s -> 14 u32s'),

        # Patch 3: Change file write loop from 10 to 14 u32s
        # Memory: 0x6805db4a, RVA: 0x5db4a, File: 0x5cf4a
        (0x5cf4a, b'\xb9\x0a\x00\x00\x00', b'\xb9\x0e\x00\x00\x00', 'File write: 10 u32s -> 14 u32s'),

        # Patch 4: Adjust grid column pitch from 50 to 40 px
        # Memory: 0x6804290f, RVA: 0x4290f, File: 0x41d0f
        (0x41d0f, b'\x66\x6b\xc9\x32', b'\x66\x6b\xc9\x28', 'Grid pitch: 50px -> 40px'),
    ]

    print("BBShell.dll patches:")
    if not patch_file(bbshell_live, bbshell_orig, bbshell_patches):
        print("FAILED: BBShell.dll patching")
        return False

    print()
    print("Creating 12-column STS files:")

    # STS file format: version (4) + name (33) + batting (56) + pitching (56) = 149 bytes
    # Each section: header (4) + filler (4) + 12 stat IDs (48)

    # Read and update existing STS files
    stat_sets = {
        '_DEFAULT.STS': {
            'name': 'Default Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],  # Add 2B, 3B, SB
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'BASIC_R.STS': {
            'name': 'Basic R Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'BASIC_S.STS': {
            'name': 'Basic S Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'MONTHLY.STS': {
            'name': 'Monthly Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'SITUATIN.STS': {
            'name': 'Situatin Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'STATS2.STS': {
            'name': 'Stats2 Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'VS_LEFT.STS': {
            'name': 'VS Left Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
        'VS_RIGHT.STS': {
            'name': 'VS Right Stat Set',
            'batting': [0, 0x0a, 4, 6, 0xd, 0xe, 0xf, 0x10, 0x11, 0x02, 0x03, 0x05],
            'pitching': [0, 0x0a, 7, 0x0c, 0xda, 0xdb, 0xd7, 0xd8, 0xd6, 0xdc, 0xd9, 0xdd],
        },
    }

    for filename, data in stat_sets.items():
        sts_path = install_dir / 'StatSets' / filename
        create_sts_file(sts_path, data['name'], data['batting'], data['pitching'])

    print()
    print("SUCCESS: All patches applied and STS files regenerated")
    return True

if __name__ == '__main__':
    if not main():
        sys.exit(1)
