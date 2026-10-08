"""Extract the target chunks for the 'chunks' target (Claude-owned). Writes <out>/<id>_<SOURCE>.bin + files.json.
usage: python3 make_files.py WORK_INSTALL OUT_DIR HOLDOUT_DIR TARGET_DIR
OUT_DIR is mounted read-only into the lanes; HOLDOUT_DIR must not be (the referee reads it only on --holdout)."""
import sys, os, json
sys.path.insert(0, '/home/will/bbpro98/work')
import chunkdat
src, out, hdir, tdir = sys.argv[1:5]
STADIUM = {'e957', '947d', 'cb7c', '7709', 'ce8c'}           # MI STA:, HS DAT:, WT, XT, @W GID:
SIM = {'e6e7', 'e1a4', 'bb43', '6be6', '5200', 'b0e7'}        # @C cameras, MI injuries, MS, OL, PB strings, UN
HOLD = {'HOUSTON', 'MIAMI', 'SEATTLE', 'TORONTO', 'PITTSBUR', 'KANSASCI', 'CHICAGON', 'OAKLAND'}
os.makedirs(out, exist_ok=True); os.makedirs(hdir, exist_ok=True)
files, hold = [], []
def put(name, data, h):
    with open(f'{hdir if h else out}/{name}', 'wb') as fh: fh.write(data)
    (hold if h else files).append(name)
for cid, tag, data in chunkdat.split(open(f'{src}/SIM.DAT', 'rb').read())[0]:
    if f'{cid:04x}' in SIM: put(f'{cid:04x}_SIM.bin', data, False)
for fn in sorted(os.listdir(f'{src}/Stadia')):
    st, ext = os.path.splitext(fn)
    for cid, tag, data in chunkdat.split(open(f'{src}/Stadia/{fn}', 'rb').read())[0]:
        if f'{cid:04x}' in STADIUM: put(f'{cid:04x}_{st}{"_DT" if ext.upper() == ".DT" else ""}.bin', data, st in HOLD)
json.dump({'dir': out, 'files': files, 'holdout': hold, 'holdout_dir': hdir,
           'coverage': ['e957_*', 'e6e7_*', 'e1a4_*', '5200_*']}, open(f'{tdir}/files.json', 'w'), indent=0)
print(len(files), 'visible,', len(hold), 'holdout')
