import sys,csv,struct,collections,math
sys.path.insert(0,'../mods')
import dump_pyr as D
def load_pyr(path):
    d,recs,inv=D.load(path); out=[]
    for r in recs:
        p=D.decode(r,inv); dn=struct.unpack('<I',p[26:30])[0]
        out.append(dict(id=struct.unpack('<H',p[:2])[0],first=D.cstr(p[30:47]),last=D.cstr(p[47:64]),by=int(dn/365.2425),pos=p[68],bats=p[65],thr=p[66],yrs=p[64],cur=list(p[70:93]),pot=list(p[93:116]),spl=list(p[116:141])))
    return out
def lahman(year):
    ppl={}
    for r in csv.DictReader(open('People.csv',encoding='utf-8-sig')):
        ppl[r['playerID']]=r
    byname=collections.defaultdict(list)
    for pid,r in ppl.items():
        byname[(r['nameFirst'].lower(),r['nameLast'].lower())].append(pid)
    bat=collections.defaultdict(lambda:collections.Counter()); pit=collections.defaultdict(lambda:collections.Counter())
    for r in csv.DictReader(open('Batting.csv')):
        if int(r['yearID'])==year:
            for k in ('G','AB','R','H','2B','3B','HR','RBI','SB','CS','BB','SO','IBB','HBP','SH','SF','GIDP'):
                bat[r['playerID']][k]+=int(r[k] or 0)
    for r in csv.DictReader(open('Pitching.csv')):
        if int(r['yearID'])==year:
            for k in ('W','L','G','GS','CG','SHO','SV','IPouts','H','ER','HR','BB','SO','BFP','WP','HBP','BK','R'):
                pit[r['playerID']][k]+=int(r.get(k) or 0)
    return ppl,byname,bat,pit
def match(players,ppl,byname):
    res={}
    for p in players:
        c=byname.get((p['first'].lower().strip('*'),p['last'].lower().strip('*')),[])
        c=[x for x in c if ppl[x]['birthYear'] and abs(int(ppl[x]['birthYear'])-p['by'])<=1]
        if len(c)==1: res[p['id']]=c[0]
    return res
if __name__=='__main__':
    pl=load_pyr('../pristine_v10/Assn/MLBPA97.PYR'); ppl,byname,bat,pit=lahman(1996)
    m=match(pl,ppl,byname); print(len(pl),'players;',len(m),'matched to Lahman')
    print('with 1996 batting AB>=1:',sum(1 for i,x in m.items() if bat[x]['AB']),' pitching IP>0:',sum(1 for i,x in m.items() if pit[x]['IPouts']))
