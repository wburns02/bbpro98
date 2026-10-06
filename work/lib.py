import struct
from parse_stats import records
OK={0,1,2,3,16,17}; LENS={22,36,40,70,150}
def load(path):
    out=[]
    for pos,rn,off,p in records(path):
        if len(p)>=6 and len(p) in LENS:
            u=struct.unpack('<%dH'%(len(p)//2),p)
            if u[0] in OK and u[1]==2: out.append((pos,rn,off,u))
    return out
