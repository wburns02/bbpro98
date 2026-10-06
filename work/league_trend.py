import sys; sys.path.insert(0,'.')
from bbstats import lines
print('yr   AB     AVG   HR/AB  BB/AB  SO/AB   ERA   | bat>=300AB  OPSproxy top10avg')
for k in range(2,11):
    bat,pit=lines('/home/will/seasons/s%d'%k)
    T=[sum(c[i] for c in bat.values()) for i in range(8)]
    ab,s,d,t,hr,rbi,bb,so=T; h=s+d+t+hr
    outs=sum(c[18] for c in pit.values()); er=sum(c[26] for c in pit.values())
    sl=lambda c:(c[1]+2*c[2]+3*c[3]+4*c[4])/max(c[0],1)
    top=sorted([c for c in bat.values() if c[0]>=300],key=lambda c:-sl(c))[:10]
    print(1996+k,ab,'%.3f %.4f %.4f %.4f %.2f'%(h/ab,hr/ab,bb/ab,so/ab,27*er/outs),'|',len([c for c in bat.values() if c[0]>=300]),'%.3f'%(sum(sl(c) for c in top)/10))
