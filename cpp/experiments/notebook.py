#!/usr/bin/env python3
"""Create and execute a compact, portable companion to the scientific report."""
from pathlib import Path
import nbformat as nbf
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[2]


def main():
    nb=nbf.v4.new_notebook();cells=[]
    def md(s):cells.append(nbf.v4.new_markdown_cell(s.strip()))
    def code(s):cells.append(nbf.v4.new_code_cell(s.strip()))
    md('''# Инкрементальный MeshA*: расширенные C++-эксперименты

11 методов; replay на одинаковых запросах и отдельная навигация по неизвестному миру. Этот ноутбук читает готовые нативные измерения, проверяет их хеши и позволяет менять парное сравнение. Времена Python и первого остановленного прохода не участвуют.

[Полный отчёт](report.md) · [PDF](report.pdf) · [Протокол](protocol.md) · [Исходники и словарь данных](../../cpp/experiments/README.md)

Параметризованные случаи с одним корнем зависимы. Превышение бюджета не равно недостижимости; короткий неоконченный проезд не считается высоким качеством.''')
    code('''from pathlib import Path
import csv, hashlib, json, statistics
from IPython.display import display, Markdown, Image

root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'cpp/experiments/frozen/manifest.json').exists())
directory = root / 'cpp/experiments/results/expanded'
analysis = json.loads((directory / 'analysis/analysis.json').read_text())
state = json.loads((directory / 'experiment.json').read_text())
assert analysis['status'] == state['status'] == 'passed'
for name, sha in analysis['raw_sha256'].items():
    assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == sha, name
with (directory / 'analysis/episode_metrics.csv').open() as f:
    episodes = list(csv.DictReader(f))
print(f"{analysis['replay_cases']} replay, {analysis['mission_cases']} missions; "
      f"{analysis['timed_episode_runs']} timed runs; {analysis['cap_rows']} capped attempts (repeats included)")
print('Memory decisions:', analysis['allocation_decision_parity'])''')
    code('''def table(headers, rows):
    text = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    text += ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]
    display(Markdown('\\n'.join(text)))

def ratio(z):
    return '—' if not z['n'] else f"{z['median']:.3f}× ({z['n']}/{z['total']})"

table(['Group', 'MPGAA/MD episode', 'MPGAA/MD repairs', 'LBA reuse/MD episode'],
      [[key, ratio(info['md_vs_mpgaa']['episode_s']), ratio(info['md_vs_mpgaa']['online_s']),
        ratio(info['md_vs_reuse']['episode_s'])] for key, info in analysis['groups'].items()])''')
    md('''## Где выигрывает ремонт

Значения больше 1 означают ускорение MD. Отношения считаются только на парах, завершённых обоими методами; доли завершения обязательно учитывать отдельно. На чистых вставках сохранение допустимого оптимального суффикса доступно стандартному A*. Неизвестная статическая карта не содержит освобождений, поэтому на ней не проверяется новый механизм их отсрочки.''')
    code('''table(['Control', 'Map', 'Regime', 'Fastest complete exact', 'MPGAA/MD', 'Reuse/MD'],
      [[r['control'], r['map'], r['family'], r['best_complete_exact'], ratio(r['md_vs_mpgaa']),
        ratio(r['md_vs_reuse'])] for r in analysis['map_results']])''')
    code('''display(Image(filename=str(root / 'docs/experiments/figures/map_regimes.png')))
display(Image(filename=str(root / 'docs/experiments/figures/all_methods.png')))''')
    md('''## Завершение и неизвестная карта

В replay доказанный `no_path` — полный корректный вычисленный ответ. В миссии завершение означает достижение цели. При навигации методы получают разные наблюдения, потому что выбирают разные пути. Отношение пройденной длины к оптимуму с полной информацией описывает цену исследования.''')
    code('''table(['Control/task', 'Method', 'Complete/all', 'Cap', 'Step limit', 'No path'],
      [[r['control'] + '/' + r['mode'], r['method'], f"{r['completed']}/{r['total']}", r['capped'],
        r['step_limit'], r['no_path']] for r in analysis['outcomes']])
display(Image(filename=str(root / 'docs/experiments/figures/performance_profiles.png')))
display(Image(filename=str(root / 'docs/experiments/figures/unknown_visibility.png')))''')
    md('''## Настраиваемое парное сравнение

Измените переменные в следующей ячейке. Сравниваются медианные эпизодные суммы на одних и тех же случаях. `metric='online_s'` исключает первичный поиск, `episode_s` включает конструктор и первый поиск. `peak_heap_bytes` — отдельный проход запрошенной C++ heap-памяти, не RSS. Не смешивайте replay и собственную навигацию.''')
    code('''control, family = 'car16', 'churn'
candidate, baseline, metric = 'md_astar', 'mpgaa', 'online_s'
meta = {}
for path in (root / 'cpp/experiments/frozen').glob('*.contexts.json'):
    for c in json.loads(path.read_text())['cases']:
        meta[c['id']] = c
selected = [r for r in episodes if r['control'] == control and r['family'] == family]
if control == 'car16' and family in ['on_path', 'off_path', 'churn', 'unknown_replay']:
    selected = [r for r in selected if 'main' in meta[r['case']]['panels']]
index = {(r['case'], r['method']): r for r in selected}
ratios, total = [], len({r['case'] for r in selected})
for case in sorted({r['case'] for r in selected}):
    a, b = index[case, candidate], index[case, baseline]
    if a['complete'] == b['complete'] == 'True' and float(a[metric]) > 0 and float(b[metric]) > 0:
        ratios.append((case, float(b[metric]) / float(a[metric])))
table(['Scenario', f'{baseline}/{candidate}'], [[name, f'{v:.3f}×'] for name, v in ratios])
print('Paired complete:', len(ratios), '/', total)
print('Median:', statistics.median(v for _, v in ratios) if ratios else None)''')
    md('''## Масштабирование и воспроизводимость

Ось числа правок использует доставленные изменения карты знаний. Номинальная доля глобальных изменений не равна этому числу; при недостатке исходно занятых клеток бюджет ограничивается доступным пулом. Графики задержек условны на запросах, закончившихся в бюджете. Все 16 фигур доступны отдельно в PNG/PDF в `figures/`.

Для полного повторения используйте `cpp/experiments/run_all.py` в новый каталог. Подготовка и модель заморожены до замеров. В экспериментальном D* Lite исправлена численная граница остановки; первый остановленный проход сохранён отдельно и исключён из этих результатов.''')
    code('''display(Image(filename=str(root / 'docs/experiments/figures/change_scaling.png')))
print('Measured source hashes:')
for path, sha in state['source_sha256'].items():
    assert hashlib.sha256((root / path).read_bytes()).hexdigest() == sha
    print(path, sha[:16])''')
    nb.cells=cells;nb.metadata.kernelspec={'display_name':'Python 3','language':'python','name':'python3'}
    NotebookClient(nb,timeout=120,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    dest=ROOT/'docs/experiments/analysis.ipynb';nbf.write(nb,dest);print(dest)


if __name__=='__main__':main()
