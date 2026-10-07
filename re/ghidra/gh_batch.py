#!/usr/bin/env python3
"""gh_batch.py SPEC.py  -- headless pyghidra batch edit of /mnt/nvme/bbpro98/ghidra_proj (stop the MCP server first: project lock).
SPEC.py defines RENAMES=[(binary,addr,name)], LABELS=[(binary,addr,name,struct_or_None,comment)], and STRUCTS(dtm_for(binary)) -> builds data types.
Rule: every function/struct identified gets named/typed here or via the MCP rename tools in the same step; notes only summarize."""
import sys,os
os.environ.setdefault('GHIDRA_INSTALL_DIR','/mnt/nvme/ghidra/ghidra_12.1.4_PUBLIC')
import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.program.model.symbol import SourceType
from ghidra.program.model.data import *
spec=dict(globals()); exec(open(sys.argv[1]).read(),spec)
proj=GhidraProject.openProject('/mnt/nvme/bbpro98/ghidra_proj','BBShell',True)
progs={}
def prog(b):
    if b not in progs: progs[b]=proj.openProgram('/',b,False)
    return progs[b]
def A(p,a): return p.getAddressFactory().getDefaultAddressSpace().getAddress(a)
try:
    for b in sorted({x[0] for x in spec.get('RENAMES',[])+spec.get('LABELS',[])+spec.get('CREATE',[])}|set(spec.get('STRUCT_BINARIES',[]))): prog(b)
    for b,p in progs.items():
        tx=p.startTransaction('backfill'); ok=False
        try:
            if 'STRUCTS' in spec: spec['STRUCTS'](b,p)
            for bb,addr in spec.get('CREATE',[]):
                if bb!=b: continue
                from ghidra.app.cmd.disassemble import DisassembleCommand
                from ghidra.app.cmd.function import CreateFunctionCmd
                if p.getFunctionManager().getFunctionAt(A(p,addr)) is None:
                    DisassembleCommand(A(p,addr),None,True).applyTo(p); print('create func',b,hex(addr),CreateFunctionCmd(A(p,addr)).applyTo(p))
            for bb,addr,name in spec.get('RENAMES',[]):
                if bb!=b: continue
                f=p.getFunctionManager().getFunctionAt(A(p,addr))
                if f is None: print('NO FUNCTION',b,hex(addr)); continue
                print('rename',b,hex(addr),f.getName(),'->',name); f.setName(name,SourceType.USER_DEFINED)
            for bb,addr,name,st,cm in spec.get('LABELS',[]):
                if bb!=b: continue
                ad=A(p,addr); L=p.getListing()
                if st:
                    dt=p.getDataTypeManager().getDataType('/BBPro98/'+st); assert dt is not None,st
                    L.clearCodeUnits(ad,ad.add(dt.getLength()-1),False); L.createData(ad,dt)
                p.getSymbolTable().createLabel(ad,name,SourceType.USER_DEFINED)
                if cm: L.setComment(ad,2,cm)   # 2 = PLATE? use EOL(0)/PLATE(3) as needed
                print('label',b,hex(addr),name,st or '')
            ok=True
        finally: p.endTransaction(tx,ok)
        proj.save(p)
finally:
    for p in progs.values(): proj.close(p)
    proj.close()
