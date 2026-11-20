#!/usr/bin/env python3
"""Audit the matched stronger-baseline cohort, separately from the main study."""
import argparse
import json
import re
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];NAV=HERE.parent/'navigation_sweeps'
sys.path.insert(0,str(NAV))
import analyze as base
import numpy as np
import pandas as pd
from study import read_manifest,digest

METHODS=['lba_reuse','mpgaa','md_astar','octile_astar','octile_reuse']
LABELS={'lba_reuse':'LBA* reuse','mpgaa':'MPGAA*','md_astar':'MD-A*','octile_astar':'Octile A*','octile_reuse':'Octile A* reuse'}

def load(directory,primary):
    state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed' and state['workers']==1
    m=read_manifest();assert state['manifest_sha256']==digest(NAV/'frozen/manifest.json') and state['selection_sha256']==m['selection_sha256']
    for p,sha in state['control_source_sha256'].items():assert digest(ROOT/p)==sha,p
    assert state['source_sha256']==m['source_sha256']
    verification=json.loads((HERE/'results/verification.json').read_text());assert verification['status']=='passed'
    assert digest(HERE/'results/build_and_sanitizer.log')==verification['log_sha256']
    for p,sha in verification['source_sha256'].items():assert digest(ROOT/p)==sha,p
    original=(NAV/'bench.cpp').read_text();assert (HERE/'bench.cpp').read_text()==original.replace('namespace nav=ima::navigation;','namespace nav=ima::navigation_controls;')
    meta={}
    for r in m['records']:
        if r['control']!='grid8':continue
        for c in json.loads((ROOT/r['contexts']).read_text())['cases']:
            if c['id'] in r['memory_cases']:meta[c['id']]=c
    assert len(meta)==80
    rows={False:[],True:[]};queries={False:[],True:[]};hashes={}
    for job in state['plan']:
        record=state['jobs'][job['name']];assert record['status']=='passed'
        for p,sha in record['output_sha256'].items():assert digest(ROOT/p)==sha,p;hashes[p]=sha
        prefix=directory/job['name'];a=pd.read_csv(str(prefix)+'_runs.csv',dtype=base.HASHES);b=pd.read_csv(str(prefix)+'_calls.csv',dtype=base.HASHES)
        assert set(a.method)==set(METHODS) and len(a)==job['expected_runs']==record['completion']['runs']
        assert len(b)==record['completion']['calls'] and b.n.eq(b.k).all()
        assert not a.duplicated(['case','method','repeat']).any() and not b.duplicated(['case','method','repeat','query']).any()
        assert a.groupby(['case','method']).fingerprint.nunique().eq(1).all()
        fields=[c for c in b.columns if c not in base.IGNORE and c not in ['case','method','query']]
        ref=b[b.repeat.eq(0)].set_index(['case','method','query'])
        for rep in sorted(set(b.repeat)-{0}):
            other=b[b.repeat.eq(rep)].set_index(['case','method','query'])
            pd.testing.assert_frame_equal(ref.loc[other.index,fields],other[fields],check_dtype=False,check_exact=True)
        ok=b.status.ne('capped');assert b.loc[ok,'cost'].notna().eq(b.loc[ok,'expected'].notna()).all()
        exact=ok&b.expected.notna();assert ((b.cost-b.expected).abs()[exact]<1e-6).all()
        rows[job['memory']].append(a);queries[job['memory']].append(b)
    for profile in [False,True]:
        jobs=[state['jobs'][j['name']] for j in state['plan'] if j['memory']==profile]
        assert len({j['binary_sha256'] for j in jobs})==1
        assert len({(j['completion']['compiler'],j['completion']['flags']) for j in jobs})==1
    runs=pd.concat(rows[False],ignore_index=True);calls=pd.concat(queries[False],ignore_index=True)
    memory=pd.concat(rows[True],ignore_index=True);memcalls=pd.concat(queries[True],ignore_index=True)
    assert len(runs)==1200 and len(memory)==400
    for a,b,keys in [(runs,memory,['case','method']),(calls,memcalls,['case','method','query'])]:
        a=a[a.repeat.eq(0)].set_index(keys);b=b.set_index(keys);fields=[c for c in b.columns if c not in base.IGNORE]
        pd.testing.assert_frame_equal(a.loc[b.index,fields],b[fields],check_dtype=False,check_exact=True)
    primary_state=json.loads((primary/'experiment.json').read_text());assert primary_state['status']=='passed'
    assert primary_state['cpu']==state['cpu'] and primary_state['platform']==state['platform']
    primary_hashes={};old=[]
    for job in primary_state['plan']:
        if job['memory'] or job['control']!='grid8':continue
        p=primary/(job['name']+'_runs.csv');sha=primary_state['jobs'][job['name']]['output_sha256'][str(p.relative_to(ROOT))]
        assert digest(p)==sha;primary_hashes[str(p.relative_to(ROOT))]=sha
        a=pd.read_csv(p,dtype=base.HASHES);old.append(a[a.repeat.eq(0)&a.method.isin(METHODS[:3])&a['case'].isin(meta)])
    reference=pd.concat(old).set_index(['case','method']).fingerprint.sort_index()
    current=runs[runs.repeat.eq(0)&runs.method.isin(METHODS[:3])].set_index(['case','method']).fingerprint.sort_index()
    pd.testing.assert_series_equal(reference,current)
    initial=calls[calls['query'].eq(0)]
    assert ((initial.expected-initial['case'].map(lambda c:meta[c]['initial_optimum'])).abs()<1e-6).all()
    return state,meta,runs,calls,memory,hashes,primary_hashes

def paired(e,keys):
    result=[]
    for values,a in e.groupby(keys,sort=True):
        values=values if isinstance(values,tuple) else (values,);group=dict(zip(keys,values))
        for baseline in ['lba_reuse','mpgaa','octile_reuse']:
            b=a[a.method.eq(baseline)].set_index('case')
            for method in METHODS:
                x=a[a.method.eq(method)].set_index('case');common=x.index.intersection(b.index)
                ids=common[x.loc[common,'complete']&b.loc[common,'complete']]
                online=ids[x.loc[ids,'phaseful']&b.loc[ids,'phaseful']&x.loc[ids,'online_s'].gt(0)&b.loc[ids,'online_s'].gt(0)]
                result.append(dict(**group,method=method,baseline=baseline,cases=len(common),paired_goals=len(ids),paired_online=len(online),
                    episode_speedup=base.gm(b.loc[ids,'episode_s']/x.loc[ids,'episode_s']),online_speedup=base.gm(b.loc[online,'online_s']/x.loc[online,'online_s']),
                    online_min_speedup=base.finite((b.loc[online,'online_s']/x.loc[online,'online_s']).min()),
                    expansion_ratio=base.gm(b.loc[ids,'expansions']/x.loc[ids,'expansions'].replace(0,np.nan)),
                    cell_read_ratio=base.gm(b.loc[ids,'checked_cells']/x.loc[ids,'checked_cells'].replace(0,np.nan))))
    return pd.DataFrame(result)

def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(map(str,r))+' |' for r in rows]])+'\n'
def num(v):return '—' if pd.isna(v) else f'{v:.2f}'

def main(directory,primary):
    state,meta,runs,calls,memory,hashes,primary_hashes=load(directory,primary)
    e=base.aggregate(meta,runs,calls,memory);s=base.summarize(e,['map','method']);p=paired(e,['map']);details=paired(e,['map','k','cr'])
    ad=directory/'analysis';ad.mkdir(exist_ok=True);tables={'episode_metrics.csv':e,'map_summary.csv':s,'map_pairs.csv':p,'parameter_pairs.csv':details}
    for name,frame in tables.items():frame.to_csv(ad/name,index=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    maps=sorted(set(e['map']));fig,axes=plt.subplots(2,1,figsize=(8.6,8),layout='constrained')
    goals=np.array([[int(s[(s['map']==m)&s.method.eq(method)].goals.iloc[0]) for m in maps] for method in METHODS])
    speed=np.array([[p[(p['map']==m)&p.method.eq(method)&p.baseline.eq('octile_reuse')].online_speedup.iloc[0] for m in maps] for method in METHODS],dtype=float)
    for ax,data,title,log in [(axes[0],goals,'Goals / 8 configurations',False),(axes[1],speed,'Online speed vs Octile A* reuse (paired goals with phases)',True)]:
        shown=np.ma.masked_invalid(np.log2(data) if log else data);ax.imshow(shown,aspect='auto',cmap='RdYlGn' if log else 'Blues',vmin=-4 if log else 0,vmax=4 if log else 8)
        ax.set_xticks(range(len(maps)),[m.replace('MA_','').replace('random50_','r50_') for m in maps],rotation=45,ha='right',fontsize=10)
        ax.set_yticks(range(len(METHODS)),[LABELS[m] for m in METHODS],fontsize=10);ax.set_title(title,fontsize=11)
        for i in range(len(METHODS)):
            for j in range(len(maps)):
                if log:
                    row=p[(p['map']==maps[j])&p.method.eq(METHODS[i])&p.baseline.eq('octile_reuse')].iloc[0]
                    label='—' if np.isnan(data[i,j]) else f'{data[i,j]:.2f}×\n({int(row.paired_online)})'
                else:label=str(int(data[i,j]))
                ax.text(j,i,label,ha='center',va='center',fontsize=9,color='white' if not log and data[i,j]>=6 else 'black')
    files={};dest=ROOT/'docs/experiments/navigation_figures'
    for ext in ['png','pdf']:
        path=dest/('strong_grid_controls.'+ext);fig.savefig(path,dpi=180);files[str(path.relative_to(ROOT))]=digest(path)
    plt.close(fig)
    out=['## Контроль с усиленным сеточным A*',
         'Отдельная серия добавляет два известных бейзлайна: обычный A* с октильной эвристикой, плотными массивами со штампами поколений и выбором большего g при равных f; и тот же A* с сохранением допустимого оптимального суффикса при отсутствии открытий. Это усиление реализации стандартного поиска, а не новый алгоритм. Диагонали и коллизионные проверки совпадают с основным grid8-протоколом. Конструктор плотных массивов включён в полное время и память.',
         'На всех десяти grid8-картах взяты только четыре ранее заданные опорные точки (2,5), (8,10), (32,20), (64,30), по два тех же корня. Дополнительный контроль назначен после основной серии; сами четыре точки были выбраны до её измерений для повторов и памяти. Вместе с новыми бейзлайнами заново измерены LBA* reuse, MPGAA* и MD-A*: **1 200 проездов времени** (три повтора) и **400 проездов памяти**. Это самостоятельная серия с единым бинарником в каждом проходе; её времена сравниваются только внутри неё. Порядок пяти методов перемешивается. Симулятор, сенсор, таймеры, лимит и независимый эталон совпадают с основной серией: копия harness отличается только выбором фабрики. Отпечатки траекторий, миров, ответов и работы трёх прежних методов точно совпали с основной серией на этих входах.',
         'В таблице: цели / 8 конфигураций, медиана полного времени в мс среди успешных проездов, online-ускорение относительно Octile A* reuse и число допустимых пар в скобках. Раскрытия, чтения и память здесь также являются медианами среди успешных проездов; все остановки сохранены в CSV. Пары требуют обеих целей, состоявшихся фаз и положительного online-времени. Отсутствие пар не означает равенство методов. Повторы не увеличивают число независимых корней.']
    for name in maps:
        rows=[]
        for method in METHODS:
            z=s[(s['map']==name)&s.method.eq(method)].iloc[0];q=p[(p['map']==name)&p.method.eq(method)&p.baseline.eq('octile_reuse')].iloc[0]
            rows.append([LABELS[method],f'{int(z.goals)}/{int(z.cases)}',num(1000*z.episode_s),f'{num(q.online_speedup)} ({int(q.paired_online)})',num(z.expansions),num(z.checked_cells),num(z.peak_heap_bytes/1048576)])
        out+=['### Усиленный контроль / '+name,table(['Метод','Цели','Поиск, мс','Online × (пар)','Раскрытия','Чтения','Пик MiB'],rows)]
    md=details[details.method.eq('md_astar')&details.baseline.eq('octile_reuse')];eligible=md[md.paired_online.eq(2)]
    wins=eligible[eligible.online_min_speedup.ge(1.1)];losses=eligible[eligible.online_min_speedup.lt(1)]
    out+=['![Отдельная серия пяти методов: покрытие и online-скорость на общих успешных проездах. Числа в скобках — пары конфигураций; цвет скорости обрезан на 1/16 и 16.](navigation_figures/strong_grid_controls.png){width=100%}',
          f'Из {len(md)} измеренных точек карта/k/cr, {len(eligible)} допускают online-сравнение MD-A* и Octile A* reuse на обоих корнях. На **{len(wins)}** из них MD-A* быстрее минимум в 1.1 раза на каждом корне; на **{len(losses)}** он проигрывает хотя бы на одном корне. Это описательный итог на выбранном срезе, без заявления статистической значимости. Полный набор отношений и проигрышей сохранён в `cpp/navigation_controls/results/full/analysis/parameter_pairs.csv`.',
          'Такой контроль отделяет выигрыш над исходной реализацией LBA* от выигрыша над более сильным стандартным A*. Октильная эвристика, плотные массивы и правило равных f изменены вместе; их отдельные вклады здесь не разделены. Повторно измеренные MPGAA*/MD-A* сохраняют исходную евклидову основу эвристики. Контроль не заменяет оптимизацию и настройку всех известных инкрементальных методов. Особенно нельзя переносить результаты grid8 на car16: октильная эвристика и один курс применимы только к grid8. Сохраняются ограничения двух корней, зависимых от траектории миров и связки n = k.']
    if len(wins):
        out+=['Полный список точек с online-выигрышем MD минимум 10% на обоих корнях приведён ниже. Это выбранная по результатам область выигрыша, а не оценка среднего эффекта всей серии. Параметры k/cr были заданы заранее.',
              table(['Карта','k = n','cr, %','Полное ×','Online ×','Мин. online ×'],[[r.map,int(r.k),int(r.cr),num(r.episode_speedup),num(r.online_speedup),num(r.online_min_speedup)] for r in wins.itertuples()])]
    body=re.sub(r'(?<=\w)\*(?!\*)',r'\\*','\n\n'.join(out)).rstrip()+'\n';body_path=ROOT/'docs/experiments/navigation_controls_body.md';body_path.write_text(body)
    a=dict(status='passed',timed_runs=len(runs),memory_runs=len(memory),planner_calls=len(calls),cases=len(meta),exact_cost_disagreements=0,
           allocation_decision_parity='passed',repeat_decision_parity='passed',primary_decision_parity='passed',source_sha256=digest(Path(__file__)),
           primary_analyzer_sha256=digest(NAV/'analyze.py'),experiment_sha256=digest(directory/'experiment.json'),verification_sha256=digest(HERE/'results/verification.json'),raw_sha256=hashes,
           primary_run_sha256=primary_hashes,tables_sha256={name:digest(ad/name) for name in tables},figures_sha256=files,body_sha256=digest(body_path),
           md_octile_eligible_points=len(eligible),md_octile_wins_10pct_both_roots=len(wins),md_octile_points_with_loss=len(losses))
    (ad/'analysis.json').write_text(json.dumps(a,indent=2)+'\n');print(json.dumps({k:v for k,v in a.items() if k.endswith('runs') or k.startswith('md_') or k=='status'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,default=HERE/'results/full');parser.add_argument('--primary-directory',type=Path,default=NAV/'results/full');args=parser.parse_args();main(args.directory.resolve(),args.primary_directory.resolve())
