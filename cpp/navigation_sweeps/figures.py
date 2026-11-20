#!/usr/bin/env python3
"""Scientific, map-separated vector and raster figures for navigation."""
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/ima_navigation_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd
from analyze import HERE,ROOT,METHODS,LABELS,digest,gm

KS=[2,4,8,16,32,64];CRS=[1,5,10,15,20,30];RADII=[8,16,32,64]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'pdf.fonttype':42,'axes.titleweight':'bold'})

def generate(directory,e,tables):
    destination=ROOT/'docs/experiments/navigation_figures';destination.mkdir(exist_ok=True)
    files={}
    def save(fig,name):
        for ext in ['png','pdf']:
            p=destination/(name+'.'+ext);fig.savefig(p,dpi=170,bbox_inches='tight');files[str(p.relative_to(ROOT))]=digest(p)
        plt.close(fig)
    def heat(ax,data,xt,yt,title,kind='speed',text=None):
        cmap=plt.get_cmap('RdBu' if kind=='speed' else 'YlGnBu').copy();cmap.set_bad('#dddddd')
        if kind=='speed':
            values=np.log2(data);im=ax.imshow(np.ma.masked_invalid(values),cmap=cmap,norm=TwoSlopeNorm(vmin=-4,vcenter=0,vmax=4),aspect='auto')
        else:im=ax.imshow(np.ma.masked_invalid(data),cmap=cmap,vmin=0,vmax=kind,aspect='auto')
        ax.set_xticks(range(len(xt)),xt);ax.set_yticks(range(len(yt)),yt);ax.set_title(title,pad=10)
        for i in range(len(yt)):
            for j in range(len(xt)):
                v=data[i,j];s=(text[i][j] if text is not None else ('—' if not np.isfinite(v) else f'{v:.2g}' if kind=='speed' else f'{v:.0f}'))
                ax.text(j,i,s,ha='center',va='center',fontsize=9,color='black',bbox=dict(facecolor='white',alpha=.66,edgecolor='none',pad=.4))
        return im
    # Every static radius is shown independently for every map.
    for name,a in e[e.kind.eq('unknown')].groupby('map',sort=True):
        speed=np.full((15,4),np.nan);coverage=np.zeros((15,4));base=a[a.method.eq('dstar_lattice')].set_index('case')
        for i,method in enumerate(METHODS):
            for j,radius in enumerate(RADII):
                x=a[a.method.eq(method)&a.radius.eq(radius)].set_index('case');coverage[i,j]=x.complete.sum();ids=x.index[x.complete&base.loc[x.index,'complete']]
                speed[i,j]=gm(base.loc[ids,'episode_s']/x.loc[ids,'episode_s']) or np.nan
        fig,axes=plt.subplots(1,2,figsize=(10,6),constrained_layout=True,gridspec_kw={'width_ratios':[1,1.6]})
        heat(axes[0],coverage,RADII,[LABELS[m] for m in METHODS],'Reached goal / 2 roots',2)
        im=heat(axes[1],speed,RADII,[LABELS[m] for m in METHODS],'Total planner speedup vs D* lattice')
        for ax in axes:ax.set_xlabel('Static sensing radius (cells)')
        cb=fig.colorbar(im,ax=axes[1],fraction=.035,pad=.03,ticks=[-4,-2,0,2,4],extend='both');cb.ax.set_yticklabels(['≤1/16×','1/4×','1×','4×','≥16×'])
        fig.suptitle(f'Initially unknown map, fixed goal — car16 / {name}\nSpeed on common goal-reaching roots; constructor included',fontsize=12)
        save(fig,'static_'+name)
    # Executed trajectories illustrate exploration without substituting for the
    # full 15-method scorecards. Endpoint polylines are not collision footprints.
    manifest=json.loads((HERE/'frozen/manifest.json').read_text())
    context={}
    for record in manifest['records']:
        for c in json.loads((ROOT/record['contexts']).read_text())['cases']:context[c['id']]=c
    for record in manifest['records']:
        if record['kind']!='unknown':continue
        meta=json.loads((ROOT/record['contexts']).read_text())['cases'];name=record['map']
        trace=pd.read_csv(directory/('timing_'+Path(record['path']).stem+'_traces.csv'))
        c=next(c for c in meta if c['seed']==48101);assert digest(ROOT/c['source'])==c['source_sha256']
        lines=(ROOT/c['source']).read_text().splitlines();at=lines.index('map')
        truth=np.array([[q not in '.G' for q in line] for line in lines[at+1:]],dtype=bool)
        if c.get('crop'):
            i,j,size=c['crop'];truth=truth[i:i+size,j:j+size]
        fig,axes=plt.subplots(1,2,figsize=(10,5.4),constrained_layout=True)
        for ax,radius in zip(axes,[8,64]):
            case=next(c for c in meta if c['seed']==48101 and c['params']['radius']==radius);own=trace[trace['case'].eq(case['id'])]
            ax.imshow(truth,cmap='Greys',vmin=0,vmax=1,interpolation='nearest')
            for method,color,style in [('lba_reuse','#d95f02','-'),('md_astar','#1b9e77','--'),('boundary_mesh','#7570b3',':')]:
                path=own[own.method.eq(method)].sort_values('step')
                if path.empty:continue
                ii=[path.iloc[0].start_i,*path.next_i];jj=[path.iloc[0].start_j,*path.next_j]
                ax.plot(jj,ii,style,color=color,linewidth=1.4,label=LABELS[method]+f' ({path.travel_cost.iloc[-1]:.1f})')
            si,sj,_=case['start'];gi,gj,_=case['goal'];ax.scatter([sj],[si],marker='o',color='tab:blue',s=35,zorder=4);ax.scatter([gj],[gi],marker='*',color='red',s=75,zorder=4)
            ax.set_title(f'Radius {radius}');ax.set_xlabel('Column');ax.set_ylabel('Row');ax.legend(fontsize=8,loc='best')
        fig.suptitle(f'Executed primitive endpoints — car16 / {name}, root 48101\nLegend: algorithm (traveled primitive cost); blue start, red fixed goal',fontsize=12)
        save(fig,'trajectories_'+name)
    # All algorithms remain visible in each map's dynamic scorecard.
    for (control,name),a in e[e.kind.eq('dynamic')].groupby(['control','map'],sort=True):
        cr_labels=[]
        for cr in CRS:
            c=next(c for c in context.values() if c['control']==control and c['map']==name and c['kind']=='dynamic' and c['params']['cr']==cr)
            cr_labels.append(f'{cr}\n{c["potential_actual_cr"]:.2f}')
        coverage=np.zeros((15,6));speed=np.full((15,6),np.nan);base=a[a.method.eq('dstar_lattice')].set_index('case');pair_n=np.zeros((15,6),int)
        for i,method in enumerate(METHODS):
            for j,k in enumerate(KS):
                x=a[a.method.eq(method)&a.k.eq(k)].set_index('case');coverage[i,j]=x.complete.sum() if len(x) else np.nan
                ids=x.index[x.complete&x.phaseful&base.loc[x.index,'complete']&base.loc[x.index,'phaseful']&x.online_s.gt(0)&base.loc[x.index,'online_s'].gt(0)];pair_n[i,j]=len(ids)
                speed[i,j]=gm(base.loc[ids,'online_s']/x.loc[ids,'online_s']) or np.nan
        fig,axes=plt.subplots(2,2,figsize=(10,12),constrained_layout=True,gridspec_kw={'height_ratios':[1.6,1]})
        per_column=int(a.groupby(['method','k']).size().max())
        heat(axes[0,0],coverage,KS,[LABELS[m] for m in METHODS],f'Reached goal / {per_column} configurations',per_column)
        labels=[[('—' if not np.isfinite(speed[i,j]) else f'{speed[i,j]:.2g}')+f'\n({pair_n[i,j]})' for j in range(6)] for i in range(15)]
        im=heat(axes[0,1],speed,KS,[LABELS[m] for m in METHODS],'Online speedup vs D* lattice (pairs)',text=labels)
        axes[0,0].set_xlabel('k = n');axes[0,1].set_xlabel('k = n')
        cb=fig.colorbar(im,ax=axes[0,1],fraction=.025,pad=.02,ticks=[-4,-2,0,2,4],extend='both');cb.ax.set_yticklabels(['≤1/16×','1/4×','1×','4×','≥16×'])
        parameters=tables['dynamic_pairs'];parameters=parameters[parameters.control.eq(control)&parameters['map'].eq(name)]
        for ax,method,baseline,title in [(axes[1,0],'md_astar','lba_reuse','MD-A* vs LBA* reuse'),(axes[1,1],'boundary_mesh','dstar_lattice','Boundary-Mesh vs D* lattice')]:
            data=np.full((6,6),np.nan);text=[['—\n(0)']*6 for _ in KS]
            for i,k in enumerate(KS):
                for j,cr in enumerate(CRS):
                    z=parameters[parameters.method.eq(method)&parameters.baseline.eq(baseline)&parameters.k.eq(k)&parameters.cr.eq(cr)]
                    if z.empty:text[i][j]='·';continue
                    row=z.iloc[0];n=int(row.paired_online)
                    if n and pd.notna(row.online_speedup):data[i,j]=row.online_speedup;text[i][j]=f'{row.online_speedup:.2g}\n({n})'
            im=heat(ax,data,cr_labels,KS,title+'\nOnline speedup (paired roots)',text=text)
            ax.set_xlabel('Requested / actual cr (%)');ax.set_ylabel('k = n')
        cb=fig.colorbar(im,ax=axes[1,:],fraction=.025,pad=.02,ticks=[-4,-2,0,2,4],extend='both');cb.ax.set_yticklabels(['≤1/16×','1/4×','1×','4×','≥16×'])
        scope='Full k/cr grid' if control=='grid8' else 'Four prespecified anchor pairs'
        fig.suptitle(f'Dynamic fixed-goal navigation — {control} / {name}\n{scope}; · unmeasured, — no eligible pair',fontsize=12)
        save(fig,'dynamic_'+control+'_'+name)
    # Received batch size is distinct from the nominal global change rate.
    work=pd.read_csv(directory/'analysis/work_by_observed_changes.csv')
    bins=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024']
    selected=['lba_reuse','dstar_lattice','mpgaa','md_astar','cmesh_dstar','boundary_mesh']
    styles=['-','--','-.',':','-','--'];colors=plt.get_cmap('tab10').colors
    strata=[('car16','MA_room96'),('grid8','MA_room512'),('grid8','random50_p30')]
    fig,axes=plt.subplots(3,3,figsize=(12,9),constrained_layout=True)
    for i,(control,name) in enumerate(strata):
        own=work[work.control.eq(control)&work['map'].eq(name)]
        for j,(field,title) in enumerate([('median_ms','Median query latency (ms)'),('expansions','Median expanded states'),('checked_cells','Median collision cell reads')]):
            ax=axes[i,j]
            for k,method in enumerate(selected):
                values=own[own.method.eq(method)].set_index('change_bin')[field].reindex(bins)
                ax.plot(range(len(bins)),values,styles[k],marker='o',markersize=3,linewidth=1.2,color=colors[k],label=LABELS[method])
            ax.set_yscale('symlog',linthresh=.01 if field=='median_ms' else 1);ax.grid(alpha=.25)
            ax.set_xticks(range(len(bins)),bins,rotation=45,ha='right',fontsize=8)
            ax.set_title(control+' / '+name+'\n'+title,fontsize=10)
            if i==2:ax.set_xlabel('Observed blocked + opened cells per online query',fontsize=9)
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=6,fontsize=9)
    save(fig,'work_by_observed_changes')
    # Prior data retain their original timing cohorts and coverage.
    prior=tables['prior_by_map']
    for cohort in ['previous11','contemporary15']:
        a=prior[prior.cohort.eq(cohort)&prior.control.eq('car16')&prior['mode'].eq('replay')]
        cols=sorted(set(zip(a['map'],a.family)));methods=[m for m in METHODS if m in set(a.method)];data=np.full((len(methods),len(cols)),np.nan);text=[['—']*len(cols) for _ in methods]
        for j,(name,family) in enumerate(cols):
            group=a[a['map'].eq(name)&a.family.eq(family)].set_index('method');b=group.loc['dstar_lattice']
            for i,method in enumerate(methods):
                x=group.loc[method];text[i][j]=f'{int(x.completed)}/{int(x.cases)}'
                if x.completed==x.cases and b.completed==b.cases and x.online_s>0:
                    data[i,j]=b.online_s/x.online_s;text[i][j]+=f'\n{data[i,j]:.2g}×'
        fig,axes=plt.subplots(2,1,figsize=(10,11),constrained_layout=True)
        split=(len(cols)+1)//2
        for ax,indices in zip(axes,[list(range(split)),list(range(split,len(cols)))]):
            im=heat(ax,data[:,indices],[cols[j][0].replace('MA_','')+'\n'+cols[j][1].replace('unknown_replay','unknown').replace('off_path','off').replace('on_path','on') for j in indices],[LABELS[m] for m in methods],
                       'Previous car16 replay: completion and online speedup',text=[[row[j] for j in indices] for row in text])
            ax.tick_params(axis='x',labelsize=8);fig.colorbar(im,ax=ax,fraction=.015,pad=.01,label='log₂ speedup',extend='both')
        save(fig,'prior_'+cohort)
    manifest=dict(status='passed',analysis_sha256=digest(directory/'analysis/analysis.json'),source_sha256=digest(Path(__file__)),files=files)
    (directory/'analysis/figures.json').write_text(json.dumps(manifest,indent=2)+'\n')
