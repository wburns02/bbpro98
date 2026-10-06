from match import *
import statistics as S
def feats(year, pyr, minAB=150, minIP=40):
    pl=load_pyr(pyr); ppl,byname,bat,pit=lahman(year); m=match(pl,ppl,byname); H=[];P=[]
    for p in pl:
        L=m.get(p['id'])
        if not L: continue
        b=bat[L]; q=pit[L]
        if p['pos']!=1 and b['AB']>=minAB:
            pa=b['AB']+b['BB']+b['HBP']+b['SF']+b['SH']
            H.append((p,dict(AVG=b['H']/b['AB'],HR=b['HR']/b['AB'],SB=b['SB']/max(1,b['G']),T=b['3B']/b['AB'],XBH=(b['2B']+b['3B'])/b['AB'],BB=b['BB']/pa,K=b['SO']/pa)))
        if p['pos']==1 and q['IPouts']>=minIP*3:
            ip=q['IPouts']/3
            P.append((p,dict(GS=q['GS']/max(1,q['G']),IPG=ip/max(1,q['G']),BB9=9*q['BB']/ip,K9=9*q['SO']/ip,HR9=9*q['HR']/ip,H9=9*q['H']/ip)))
    return H,P
def ols(X,y):  # X list of feature rows (with bias handled by caller); normal equations via gaussian elimination
    n=len(X[0]); A=[[sum(r[i]*r[j] for r in X) for j in range(n)] for i in range(n)]; b=[sum(r[i]*t for r,t in zip(X,y)) for i in range(n)]
    for i in range(n):
        piv=max(range(i,n),key=lambda r:abs(A[r][i])); A[i],A[piv]=A[piv],A[i]; b[i],b[piv]=b[piv],b[i]
        for r in range(i+1,n):
            f=A[r][i]/A[i][i]
            for c in range(i,n): A[r][c]-=f*A[i][c]
            b[r]-=f*b[i]
    w=[0]*n
    for i in reversed(range(n)): w[i]=(b[i]-sum(A[i][j]*w[j] for j in range(i+1,n)))/A[i][i]
    return w
def design(rows,names): return [[1.0]+[r[1][k] for k in names] for r in rows]
def fit_eval(train,test,byte,names,label):
    w=ols(design(train,names),[r[0]['cur'][byte-70] for r in train])
    pred=lambda r:max(0,min(99,sum(a*b for a,b in zip(w,[1.0]+[r[1][k] for k in names]))))
    err=[abs(pred(r)-r[0]['cur'][byte-70]) for r in test]; sd=S.pstdev([r[0]['cur'][byte-70] for r in test])
    print(f'  {label:<9} byte {byte} ~ {"+".join(names):<22} MAE {S.mean(err):5.1f}  (rating sd {sd:4.1f}; guess-mean MAE would be ~{0.8*sd:4.1f})  n={len(test)}')
    return w
if __name__=='__main__':
    H97,P97=feats(1996,'../pristine_v10/Assn/MLBPA97.PYR')
    H96,P96=feats(1995,'../pristine_v10/Assn/MLBPA96E.PYR')
    print('train on 97 league(1996 stats), test on 96 league(1995 stats):')
    for byte,names in [(70,['AVG']),(70,['AVG','K']),(71,['HR']),(71,['HR','XBH']),(72,['SB']),(72,['SB','T'])]:
        w=fit_eval(H97,H96,byte,names,'hit'); print('      weights',[round(x,1) for x in w])
    for byte,names in [(75,['GS']),(75,['GS','IPG']),(76,['BB9']),(77,['K9']),(77,['K9','H9'])]:
        w=fit_eval(P97,P96,byte,names,'pitch'); print('      weights',[round(x,1) for x in w])
