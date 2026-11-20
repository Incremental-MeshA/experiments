#!/usr/bin/env python3
"""Build and execute a compact notebook for the map-separated navigation data."""
import argparse
import hashlib
from pathlib import Path
import nbformat as nbf
from nbclient import NotebookClient

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def main(directory=HERE/'results/full'):
    directory=directory.resolve();relative=str(directory.relative_to(ROOT))
    notebook=nbf.v4.new_notebook()
    notebook.metadata['kernelspec']=dict(display_name='Python 3',language='python',name='python3')
    notebook.metadata['navigation_artifact']=dict(analysis_sha256=hashlib.sha256((directory/'analysis/analysis.json').read_bytes()).hexdigest(),
                                                 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),directory=relative)
    cells=[nbf.v4.new_markdown_cell('''# Incremental MeshA*: движение и раскрытие карты

Все 15 C++ методов; n = k; одинаковое ограничение обеих сторон обмена. Полный grid8-протокол содержит 36 k/cr на десяти картах; дополнительная car16-динамика содержит четыре заранее выбранные опорные пары на шести картах. Статическое раскрытие содержит четыре радиуса на шести car16-картах. Пары времени требуют общей цели, а online — фактических фаз и ненулевого ремонта у обоих методов. Полные графики по каждой карте находятся в `navigation_by_map.pdf`. Проезды имеют собственные траектории и могут отличаться картой из-за защиты текущей клетки. Временные серии прежних экспериментов не объединяются с новой.''')]
    code=[
'''from pathlib import Path
import json
import pandas as pd
from IPython.display import display, Image
study_relative = @@STUDY@@
root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/study_relative/'analysis/analysis.json').exists())
directory = root/study_relative/'analysis'
audit = json.loads((directory/'analysis.json').read_text())
display({k:audit[k] for k in ['status','timed_runs','memory_runs','planner_calls','terminal_counts','stale_dead_ends','dynamic_zero_phase_goals','exact_cost_disagreements','allocation_decision_parity']})''',
'''episodes = pd.read_csv(directory/'episode_metrics.csv')
maps = pd.read_csv(directory/'map_summary.csv')
display(maps.pivot_table(index=['control','kind','map'], columns='method', values='goals', aggfunc='first'))''',
'''static = pd.read_csv(directory/'static_radius.csv')
display(static[static['map'].eq('Berlin')].pivot(index='method',columns='radius',values=['goals','episode_s','expansions']))
display(Image(filename=str(root/'docs/experiments/navigation_figures/static_Berlin.png')))''',
'''pairs = pd.read_csv(directory/'dynamic_pairs.csv')
view = pairs[pairs.control.eq('grid8') & pairs['map'].eq('MA_room512') & pairs.method.eq('md_astar') & pairs.baseline.eq('dstar_lattice')]
display(view.pivot(index='k',columns='cr',values=['paired_online','online_speedup']))
display(Image(filename=str(root/'docs/experiments/navigation_figures/dynamic_grid8_MA_room512.png')))''',
'''dynamic = episodes[episodes.kind.eq('dynamic') & episodes.phases.gt(0)]
display(dynamic.groupby(['control','map','cr']).agg(actual_cr=('actual_cr','median'),clamped_phases=('clamped_phases','sum'),episodes=('case','size')).reset_index())''',
'''work = pd.read_csv(directory/'work_by_observed_changes.csv')
display(work[work['map'].eq('MA_random512') & work.control.eq('grid8') & work.method.isin(['lba_reuse','dstar_lattice','md_astar','boundary_mesh'])])''',
'''prior = pd.read_csv(directory/'prior_by_map.csv')
display(prior[prior.cohort.eq('contemporary15') & prior.control.eq('car16') & prior['map'].eq('Berlin') & prior['mode'].eq('replay')].pivot(index='method',columns='family',values=['completed','online_s']))''',
'''display(episodes[episodes.repeats.eq(3)].groupby(['control','kind']).agg(configurations=('case','size'),median_relative_mad=('repeat_relative_mad','median')))
display({k:audit[k] for k in ['repeat_decision_parity','grid_mesh_projection_parity','manifest_sha256','selection_sha256','verification_sha256']})''']
    cells.extend(nbf.v4.new_code_cell(c.replace('@@STUDY@@',repr(relative))) for c in code)
    cells.append(nbf.v4.new_markdown_cell('''Полные остановки, сырые времена, хеши и воспроизводимые команды сохранены в артефакте. Один широкий временной повтор вне четырёх опорных точек и два корня на карту ограничивают статистические выводы. Отношение длины динамического пути к начальному оптимуму не является competitive ratio.'''))
    notebook.cells=cells
    NotebookClient(notebook,timeout=300,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    target=ROOT/'docs/experiments/navigation_analysis.ipynb';nbf.write(notebook,target);print('Executed',len(code),'code cells:',target)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,default=HERE/'results/full');main(parser.parse_args().directory)
