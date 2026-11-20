#!/usr/bin/env python3
"""Create and execute a small analysis notebook without repeating measurements."""
from pathlib import Path
import os
import hashlib
import nbformat as nbf
from nbclient import NotebookClient
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEST=ROOT/'docs/mpgaa_mesh'

def main():
    for name,path in [('JUPYTER_RUNTIME_DIR','/tmp/mpgaa-mesh-jupyter'),('IPYTHONDIR','/tmp/mpgaa-mesh-ipython')]:
        os.environ.setdefault(name,path);Path(os.environ[name]).mkdir(parents=True,exist_ok=True)
    cells=[nbf.v4.new_markdown_cell('''# Mesh и MPGAA*: четыре варианта

Этот ноутбук читает проверенные сохранённые данные новой серии. Повторять временные запуски не требуется. Полный протокол, инварианты и ограничения находятся в [report.pdf](report.pdf) и [README](../../cpp/mpgaa_mesh/README.md).

Boundary совместно проверяет префиксы; Selective использует допустимый incumbent и границы ветвей; Delta подписывается на свободные префиксы и препятствия-свидетели; Policy ищет tight-цепочку среди нескольких альтернатив. После освобождений все варианты сначала восстанавливают допустимость эвристики.'''),
    nbf.v4.new_code_cell('''from pathlib import Path
import json
import pandas as pd
from IPython.display import display, Image
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'cpp/mpgaa_mesh').is_dir())
AD = ROOT/'cpp/mpgaa_mesh/results/full/analysis'
checks = json.loads((AD/'analysis.json').read_text())
display({k:checks[k] for k in ['status','timed_runs','memory_runs','scenarios','timed_planner_calls','exact_cost_disagreements','independent_dijkstra_comparisons','capped_calls','memory_matched_rows']})
cases = pd.read_csv(AD/'case_metrics.csv')
summary = pd.read_csv(AD/'summary.csv')
new = ['boundary_mpgaa','selective_mpgaa','delta_mpgaa','policy_mpgaa']'''),
    nbf.v4.new_markdown_cell('''## Полное время и полнота

Сначала берётся медиана трёх повторов внутри конфигурации, затем геометрическое среднее парных отношений. Значение больше 1 выгодно кандидату. Ускорения условны на завершении обоих методов; replay считает доказанную недостижимость корректным ответом, миссии требуют достижения цели. Интервалы — описательный bootstrap по картам, не оценка независимых запросов.'''),
    nbf.v4.new_code_cell('''display(summary[summary.method.isin(new) & summary.baseline.eq('mpgaa')][['cohort','control','method','episode_speedup','episode_speedup_lo','episode_speedup_hi','online_speedup','paired','configurations']])
display(cases[cases.method.isin(new)].groupby(['cohort','control','method']).complete.agg(['sum','size']))
display(Image(filename=str(ROOT/'docs/mpgaa_mesh/figures/episode_speedup.png'), width=960))'''),
    nbf.v4.new_markdown_cell('''## Карты и сильные контроли

`best_control` выбирает самый быстрый по полному эпизоду завершившийся контроль в каждой конфигурации. Это описательная огибающая, выбранная после измерений. В навигации у методов собственные траектории и наблюдения; парными являются конфигурации симулятора, а не тождественные последовательности запросов.'''),
    nbf.v4.new_code_cell('''maps = pd.read_csv(AD/'map_pairs.csv')
view = maps[maps.cohort.eq('navigation_dynamic') & maps.baseline.eq('best_control') & maps.method.isin(new)]
display(view[['control','map','method','episode_speedup','online_speedup','paired','configurations']])
display(Image(filename=str(ROOT/'docs/mpgaa_mesh/figures/navigation_maps.png'), width=900))'''),
    nbf.v4.new_markdown_cell('''## Абляции и память

`selective_no_prune` отключает только отсечение, сохраняя incumbent. `selective_geom` использует геометрическую оценку в границах ветвей, сохраняя обученный A*. Память получена отдельным проходом запрошенных C++ heap-байтов и не является RSS. Времена этого прохода не сравниваются.'''),
    nbf.v4.new_code_cell('''display(summary[summary.cohort.eq('replay') & summary.method.eq('selective_mpgaa') & summary.baseline.isin(['selective_no_prune','selective_geom'])][['control','baseline','episode_speedup','online_speedup','paired']])
display(pd.read_csv(AD/'work.csv').query('method in @new'))
display(cases[cases.method.isin(new)].groupby(['control','method']).peak_heap_bytes.agg(['median','max'])/2**20)
display(Image(filename=str(ROOT/'docs/mpgaa_mesh/figures/memory.png'), width=900))''')]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    notebook=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
        'mpgaa_mesh_artifact':{'analysis_sha256':sha(HERE/'results/full/analysis/analysis.json'),'source_sha256':sha(Path(__file__))}})
    NotebookClient(notebook,timeout=300,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    target=DEST/'analysis.ipynb';nbf.write(notebook,target);print(target)

if __name__=='__main__':main()
