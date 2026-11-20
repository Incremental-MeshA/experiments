#!/usr/bin/env python3
"""Prespecified fresh cohort. All selection precedes candidate timings."""
import hashlib,json,shlex,subprocess,random
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
NEW=['envelope_mesh','dual_mesh','circuit_mesh']
ABLATION=['mesh_cold','mesh_reuse','cut_mesh','lattice_envelope']
CONTROL=['lba_reuse','mesha','mpgaa','md_astar','boundary_mesh','boundary_mpgaa','delta_mpgaa','batch_mpgaa','dstar_lattice','cmesh_dstar']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def split_suite(path):
 t=shlex.split(path.read_text(),comments=False);i=2;nt,np,nc=map(int,t[i+1:i+4]);i+=4+nt
 for _ in range(np):n=int(t[i+5]);i+=6+2*n
 for _ in range(nc):ne,nf=map(int,t[i+4:i+6]);i+=6+ne*5+nf*4
 head=t[:i];nm=int(t[i]);i+=1;maps=[]
 for _ in range(nm):h,w=map(int,t[i+1:i+3]);maps.append(t[i:i+3+h]);i+=3+h
 n=int(t[i]);i+=1;cases={}
 for _ in range(n):
  begin=i;name=t[i];nq=int(t[i+3]);i+=4
  for _ in range(nq):nb,no=map(int,t[i+9:i+11]);i+=11+2*(nb+no)
  cases[name]=t[begin:i]
 assert i==len(t)
 return head,maps,cases

def synthetic(model,dest):
 head,_,_=split_suite(ROOT/f'cpp/experiments/frozen/{model}_model.txt')
 server=subprocess.Popen([str(HERE/'build/replay'),'--serve','--input',str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 maps=[];cases=[];contexts={}
 try:
  for size in [32,64]:
   for seed in [48101,48102]:
    for regime in ['remote','frontier','reconnect']:
     rng=random.Random(seed+size);g=[list('.'*size) for _ in range(size)];mid=size//2;lo=mid-3;hi=mid+3
     for i in range(size):
      for j in range(lo,hi+1):g[i][j]='#'
     # Fixed scattered obstacles on both sides, identical across regimes.
     for _ in range(size):
      i,j=rng.randrange(size),rng.randrange(size)
      if j<lo-3 or j>hi+3:g[i][j]='#'
     s=[size//2,4,0];goal=[size//2,size-5,0];g[s[0]][s[1]]=g[goal[0]][goal[1]]='.'
     initial=[''.join(row) for row in g];name=f'{model}__separator{size}__{regime}__s{seed}';qs=[];tokens=[]
     for q in range(17):
      edits={}
      if q:
       if regime=='reconnect' and q%4==0:
        value='.' if q%8==4 else '#'
        for i in range(size//2-6,size//2+7):
         for j in range(lo,hi+1):edits[i,j]=value
       else:
        for _ in range(8):
         if regime=='remote':i,j=rng.randrange(size),rng.randrange(hi+4,size)
         elif regime=='frontier':i,j=rng.randrange(size),rng.randrange(lo,hi+1)
         else:i,j=rng.randrange(size),rng.randrange(1,lo-2)
         if [i,j] not in [s[:2],goal[:2]]:edits[i,j]='.' if g[i][j]=='#' else '#'
      b=[];o=[]
      for (i,j),v in sorted(edits.items()):
       if v!=g[i][j]:(b if v=='#' else o).append([i,j]);g[i][j]=v
      server.stdin.write('plan '+' '.join(map(str,[size,size,*s,*goal]))+'\n'+'\n'.join(''.join(r) for r in g)+'\n');server.stdin.flush()
      answer=json.loads(server.stdout.readline());assert not answer['capped'];cost=answer['cost']
      qq=dict(start=s,goal=goal,blocks=b,opens=o,expected=cost,category='initial' if q==0 else 'event',event=regime,changes=len(b)+len(o));qs.append(qq)
      tokens.extend(map(str,[*s,*goal,-1 if cost is None else cost,qq['category'],regime,len(b),len(o)]))
      tokens.extend(str(v) for cell in b+o for v in cell)
     maps.extend([f'map_{len(cases)}',str(size),str(size),*initial]);cases.append([name,regime,str(len(cases)),'17',*tokens])
     contexts[name]=dict(id=name,map=f'separator{size}',map_family='synthetic',control=model,cohort='separator',family=regime,seed=seed,shape=[size,size],params=dict(queries=17,random_edits=8),queries=qs)
 finally:
  server.stdin.write('quit\n');server.stdin.flush();server.wait()
 out=dest/f'{model}_separator.txt';out.write_text(' '.join(head+[str(len(cases))]+maps+[str(len(cases))]+sum(cases,[]))+'\n')
 return out,contexts

def main():
 dest=HERE/'frozen';dest.mkdir(exist_ok=True);assert not (dest/'manifest.json').exists()
 plan=[];contexts={};files={}
 def reg(p):
  key=str(p.relative_to(ROOT));files[key]=sha(p);return key
 for model in ['car16','grid8']:
  source=ROOT/f'cpp/experiments/frozen/{model}_replay.txt';ctx=source.with_suffix('.contexts.json');cs=json.loads(ctx.read_text())['cases']
  # Balanced six-map car study; retain original history and sensitivity only
  # in a secondary cohort to avoid treating oversampled maps as independent.
  selected=[c for c in cs if model=='grid8' or 'main' in c['panels'] or 'history' in c['panels']]
  head,maps,cases=split_suite(source);out=dest/(model+'_replay.txt');out.write_text(' '.join(head+[str(len(maps))]+sum(maps,[])+[str(len(selected))]+sum((cases[c['id']] for c in selected),[]))+'\n')
  reg(source);reg(ctx);contexts.update({c['id']:dict(c,cohort='replay',control=model) for c in selected})
  methods=CONTROL+NEW+ABLATION+(['octile_reuse'] if model=='grid8' else [])
  plan.append(dict(name='replay_'+model,mode='replay',input=reg(out),cases=len(selected),methods=methods))
  out,cs=synthetic(model,dest);contexts.update(cs)
  plan.append(dict(name='separator_'+model,mode='replay',input=reg(out),cases=len(cs),methods=methods))
 old=ROOT/'cpp/navigation_sweeps/frozen'
 for source in sorted(old.glob('*.specs.txt')):
  stem=source.name.removesuffix('.specs.txt');model=stem.split('_')[0];kind=stem.rsplit('_',1)[1];selected=[];ids=set()
  for line in source.read_text().splitlines()[1:]:
   f=shlex.split(line);r,k,cr=map(int,f[2:5])
   if ('s48101' if model=='car16' else 's68101') in f[0] and ((kind=='dynamic' and (k,cr) in {(2,5),(32,20)}) or (kind=='unknown' and r in [8,16,32,64])):
    selected.append(line);ids.add(f[0])
  if not selected:continue
  specs=dest/(stem+'.specs.txt');specs.write_text(f'NAV_SPEC 1 {len(selected)}\n'+'\n'.join(selected)+'\n')
  ctx=old/(stem+'.contexts.json');cs=[c for c in json.loads(ctx.read_text())['cases'] if c['id'] in ids];assert len(cs)==len(ids)
  contexts.update({c['id']:dict(c,control=model,cohort='navigation_'+kind) for c in cs});reg(ctx);reg(source)
  # Navigation omits collision-only/negative-only ablations, includes the three
  # candidates and all ten fresh controls. n=k and actual cr are inherited.
  job=dict(name='navigation_'+stem,mode='navigation',input=reg(old/(stem+'.txt')),specs=reg(specs),cases=len(ids),methods=CONTROL+NEW+(['octile_reuse'] if model=='grid8' else []))
  if kind=='dynamic':job['visibility']=reg(old/(model+'_visibility.txt'))
  plan.append(job)
 (dest/'contexts.json').write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');reg(dest/'contexts.json')
 dirs=['cpp/include/ima','cpp/mesh_variants','cpp/navigation_controls','cpp/navigation_sweeps','cpp/mpgaa_mesh','cpp/mpgaa_lazy','cpp/mesh_envelope']
 sources=[p for d in dirs for p in (ROOT/d).glob('*.hpp')]
 sources +=[ROOT/p for p in ['cpp/experiments/memory.hpp','cpp/experiments/dstar_boundary.hpp']]
 sources +=[HERE/p for p in ['Makefile','test.cpp','replay.cpp','navigation.cpp','prepare.py','run_all.py']]
 manifest=dict(version=1,base_commit='7b8876cdfd798c0ee3768f701379e2dff33b416b',repeats=3,cap=1000000,seed=731019,primary_methods=NEW,controls=CONTROL+['octile_reuse'],ablations=ABLATION,plan=plan,files=files,sources={str(p.relative_to(ROOT)):sha(p) for p in sources},protocol='Frozen before timings. Six car maps x two roots x four replay families plus four old history cases; all 96 grid replay. New separators: two sizes x two roots x three edit regimes x two control sets, 17 queries. Car unknown: all six maps, one root, four radii. Dynamic: all sixteen maps, one root, two anchors (k,cr)=(2,5),(32,20), visibility n=k, balanced edits clamped and actual cr retained. Three serial randomized repeats; separate allocation pass. No source changes or parameter tuning after freeze.')
 manifest.update(scenarios=sum(j['cases'] for j in plan),timed_runs=sum(j['cases']*len(j['methods'])*3 for j in plan),memory_runs=sum(j['cases']*len(j['methods']) for j in plan))
 (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({k:manifest[k] for k in ['scenarios','timed_runs','memory_runs','protocol']}))
if __name__=='__main__':main()
