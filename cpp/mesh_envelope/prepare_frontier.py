#!/usr/bin/env python3
"""Structural complement: all three barrier widths, before inspecting aggregates.

Width 7 exceeds the car primitive span, hiding free outside endpoints. Widths
1/3 exercise explicit mesh cut witnesses. A shifting thin wall also exposes
conservative-superset rebuilds. This complement is reported separately.
"""
import json,subprocess,random
from pathlib import Path
from prepare import HERE,ROOT,split_suite,sha,CONTROL,NEW,ABLATION

def main():
 dest=HERE/'frozen/frontier';dest.mkdir(parents=True,exist_ok=True);assert not (dest/'manifest.json').exists()
 primary=json.loads((HERE/'frozen/manifest.json').read_text());files={};contexts={};plan=[]
 def reg(p):key=str(p.relative_to(ROOT));files[key]=sha(p);return key
 for model in ['car16','grid8']:
  head,_,_=split_suite(ROOT/f'cpp/experiments/frozen/{model}_model.txt');maps=[];cases=[]
  server=subprocess.Popen([str(HERE/'build/replay'),'--serve','--input',str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  try:
   for width in [1,3,7]:
    for seed in [48101,48102]:
     size=64;mid=size//2;lo=mid-width//2;g=[list('.'*size) for _ in range(size)];rng=random.Random(seed)
     for _ in range(2*size):
      i,j=rng.randrange(size),rng.randrange(size)
      if abs(j-mid)>10:g[i][j]='#'
     for i in range(size):
      for j in range(lo,lo+width):g[i][j]='#'
     s=[size//2,5,0];t=[size//2,size-6,0];g[s[0]][s[1]]=g[t[0]][t[1]]='.';initial=[''.join(r) for r in g]
     name=f'{model}__shifted_separator64__w{width}__s{seed}';qs=[];tokens=[]
     for q in range(17):
      newlo=lo+(q%2);b=[];o=[]
      if q:
       for i in range(size):
        for j in range(lo,lo+width+1):
         v='#' if newlo<=j<newlo+width else '.'
         if g[i][j]!=v:(b if v=='#' else o).append([i,j]);g[i][j]=v
      server.stdin.write('plan '+' '.join(map(str,[size,size,*s,*t]))+'\n'+'\n'.join(''.join(r) for r in g)+'\n');server.stdin.flush();a=json.loads(server.stdout.readline());assert not a['capped']
      assert a['cost'] is None,'separator unexpectedly traversable'
      qq=dict(start=s,goal=t,blocks=b,opens=o,expected=None,category='initial' if not q else 'event',event='shift',changes=len(b)+len(o));qs.append(qq)
      tokens.extend(map(str,[*s,*t,-1,qq['category'],'shift',len(b),len(o)]));tokens.extend(str(v) for c in b+o for v in c)
     maps.extend([f'map_{len(cases)}',str(size),str(size),*initial]);cases.append([name,'shift',str(len(cases)),'17',*tokens])
     contexts[name]=dict(id=name,map=f'shift64_w{width}',map_family='synthetic',control=model,cohort='frontier_width',family='shift',seed=seed,shape=[size,size],width=width,queries=qs)
  finally:server.stdin.write('quit\n');server.stdin.flush();server.wait()
  out=dest/(model+'.txt');out.write_text(' '.join(head+[str(len(cases))]+maps+[str(len(cases))]+sum(cases,[]))+'\n')
  plan.append(dict(name='frontier_'+model,mode='replay',input=reg(out),cases=len(cases),methods=CONTROL+NEW+ABLATION+(['octile_reuse'] if model=='grid8' else [])))
 ctx=dest/'contexts.json';ctx.write_text(json.dumps(contexts,indent=1)+'\n');reg(ctx)
 source={**primary['sources'],str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),str((HERE/'run_frontier.py').relative_to(ROOT)):sha(HERE/'run_frontier.py')}
 m=dict(version=1,repeats=3,cap=primary['cap'],seed=731021,primary_methods=NEW,controls=primary['controls'],ablations=ABLATION,plan=plan,files=files,sources=source,contexts_file=str(ctx.relative_to(ROOT)),protocol='Separate structural complement specified before inspecting aggregate primary times: fixed 64x64 maps, widths 1/3/7, two fixed-start map seeds, alternating one-column barrier shift, both control sets, 17 queries. All three widths retained, including conservative-certificate fallbacks. Three serial randomized timings and a separate allocation pass; same immutable kernel binaries as primary. Not pooled with primary summary.')
 m.update(scenarios=sum(x['cases'] for x in plan),timed_runs=sum(x['cases']*len(x['methods'])*3 for x in plan),memory_runs=sum(x['cases']*len(x['methods']) for x in plan))
 (dest/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(m['scenarios'],m['timed_runs'])
if __name__=='__main__':main()
