# exact Maker-Breaker solver for small boards (Maker moves first)
import sys
from functools import lru_cache
def solve(ncells, lines):
    masks=[sum(1<<c for c in l) for l in lines]
    full=(1<<ncells)-1
    @lru_cache(maxsize=None)
    def maker_wins(m,b):
        # Maker to move
        live=[x for x in masks if not x&b]
        if not live: return False
        free=full&~(m|b)
        if not free: return False
        # immediate win
        for x in live:
            r=x&~m
            if r&(r-1)==0: return True
        f=free
        while f:
            c=f&-f; f^=c
            if breaker_holds(m|c,b) is False: return True
        return False
    @lru_cache(maxsize=None)
    def breaker_holds(m,b):
        # Breaker to move; returns True if Breaker wins
        live=[x for x in masks if not x&b]
        if not live: return True
        free=full&~(m|b)
        # forced block
        threats=[x&~m for x in live if (x&~m)&((x&~m)-1)==0]
        if len(set(threats))>=2: return False
        cand=threats if threats else []
        f=free
        if not cand:
            while f:
                c=f&-f; f^=c; cand.append(c)
        for c in cand:
            if not maker_wins(m,b|c): return True
        return False
    return not maker_wins(0,0)
if __name__=="__main__":
    def grid(k,diag=True):
        L=[[r*k+c for c in range(k)] for r in range(k)]+[[r*k+c for r in range(k)] for c in range(k)]
        if diag: L+= [[i*k+i for i in range(k)],[i*k+(k-1-i) for i in range(k)]]
        return L
    print("3x3 Breaker wins:", solve(9,grid(3)))
    print("4x4 Breaker wins:", solve(16,grid(4)))
