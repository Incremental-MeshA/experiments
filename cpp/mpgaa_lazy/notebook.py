#!/usr/bin/env python3
"""Execute an analysis notebook against saved measurements, never rerun timing."""
import hashlib
import os
from pathlib import Path
import nbformat as nbf
from nbclient import NotebookClient
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEST=ROOT/'docs/mpgaa_lazy'
def main():
    for name,path in [('JUPYTER_RUNTIME_DIR','/tmp/mpgaa-lazy-jupyter'),('IPYTHONDIR','/tmp/mpgaa-lazy-ipython')]:
        os.environ.setdefault(name,path);Path(os.environ[name]).mkdir(parents=True,exist_ok=True)
    cells=[nbf.v4.new_markdown_cell('''# Stamp, Batch и Witness

Этот выполненный notebook читает сохраненные результаты новой серии. Он не запускает измерения. [Отчет](report.pdf) и [протокол C++](../../cpp/mpgaa_lazy/README.md) описывают инварианты и ограничения. Stamp использует версии плиток, Batch выбирает способ начального ремонта при освобождениях, Witness хранит компактное сечение препятствий.'''),
        nbf.v4.new_code_cell('''from pathlib import Path
import json
import pandas as pd
from IPython.display import display, Image
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'cpp/mpgaa_lazy').is_dir())
AD = ROOT/'cpp/mpgaa_lazy/results/full/analysis'
checks = json.loads((AD/'analysis.json').read_text())
display({k:checks[k] for k in ['status','timed_runs','memory_runs','scenarios','timed_planner_calls','exact_cost_disagreements','capped_calls','independent_dijkstra_comparisons','memory_matched_rows']})
cases = pd.read_csv(AD/'case_metrics.csv')
summary = pd.read_csv(AD/'summary.csv')
new = ['stamp_mpgaa','batch_mpgaa','witness_mpgaa']'''),
        nbf.v4.new_markdown_cell('''## Полное время, online и полнота

Время — медиана трех повторов внутри конфигурации. В таблицах — геометрическое среднее парных отношений baseline / candidate. Больше 1 выгодно кандидату. Пары требуют завершения обоих методов; replay считает корректное отсутствие пути завершением, навигация требует достижения цели.'''),
        nbf.v4.new_code_cell('''display(summary[summary.method.isin(new) & summary.baseline.eq('boundary_mpgaa')][['cohort','control','method','episode_speedup','episode_speedup_lo','episode_speedup_hi','online_speedup','paired','configurations']])
display(cases[cases.method.isin(new)].groupby(['cohort','control','method']).complete.agg(['sum','size']))
display(Image(filename=str(ROOT/'docs/mpgaa_lazy/figures/episode_speedup.png'), width=950))'''),
        nbf.v4.new_markdown_cell('''## Карты, радиусы и сильные контроли

`best_control` выбирает самый быстрый завершившийся прежний метод по полному эпизоду после измерения. В closed-loop навигации методы исполняют собственные маршруты и могут получать разные наблюдения. Два корня и конфигурации одной карты не являются независимыми новыми картами.'''),
        nbf.v4.new_code_cell('''maps = pd.read_csv(AD/'map_pairs.csv')
display(maps[maps.cohort.eq('navigation_dynamic') & maps.baseline.eq('best_control') & maps.method.isin(new)][['control','map','method','episode_speedup','online_speedup','paired','configurations']])
display(pd.read_csv(AD/'navigation_points.csv'))
display(Image(filename=str(ROOT/'docs/mpgaa_lazy/figures/unknown_radius.png'), width=950))'''),
        nbf.v4.new_markdown_cell('''## Механизмы, абляции и память

Batch против Stamp меняет выбор начального ремонта; Witness против Batch добавляет сечение. `stamp_cell` использует версии отдельных клеток; `batch_scan` всегда просматривает обученные состояния. Память получена отдельным проходом C++ allocation bytes, не RSS. Нулевые обратные уведомления при блокировках не означают нулевую работу планировщика.'''),
        nbf.v4.new_code_cell('''display(summary[summary.cohort.eq('replay') & summary.method.isin(new) & summary.baseline.isin(['stamp_cell','batch_scan','stamp_mpgaa','batch_mpgaa'])][['control','method','baseline','episode_speedup','online_speedup','memory_ratio','paired']])
display(pd.read_csv(AD/'repair_work.csv').query('method in @new and edit_kind == "blocks"'))
display(cases[cases.method.isin(new)].groupby(['control','method']).peak_heap_bytes.agg(['median','max'])/2**20)
display(Image(filename=str(ROOT/'docs/mpgaa_lazy/figures/ablations.png'), width=950))''')]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    notebook=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
        'mpgaa_lazy_artifact':{'analysis_sha256':sha(HERE/'results/full/analysis/analysis.json'),'source_sha256':sha(Path(__file__))}})
    NotebookClient(notebook,timeout=300,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    target=DEST/'analysis.ipynb';nbf.write(notebook,target);print(target)
if __name__=='__main__':main()
