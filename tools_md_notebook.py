#!/usr/bin/env python3
"""Build a lightweight, data-driven notebook; it never reruns expensive searches."""
import argparse
from pathlib import Path

import nbformat as nbf

ROOT=Path(__file__).resolve().parent


def main(execute=False):
    from tools_md_report import stars
    nb=nbf.v4.new_notebook()
    nb.metadata.update(kernelspec={'display_name':'Python 3','language':'python','name':'python3'},language_info={'name':'python','version':'3.12'})
    nb.cells=[
        nbf.v4.new_markdown_cell('# MD-A*: нативный перенос и сравнение\n\nВетка `research/md-astar`, исходный репозиторий `Incremental-MeshA/introduction`, база `cc58898`.\n\n[Статья и оценка качества](docs/md_astar/report.md) · [PDF](docs/md_astar/report.pdf) · [Доказательство](docs/md_astar/method.md) · [Код](mesha/deferred.py).\n\nЗдесь используются только новые Python-измерения на исходном `car16`. Старые C++-артефакты сохранены отдельно и в ускорения не входят.'),
        nbf.v4.new_code_cell("from pathlib import Path\nimport json, hashlib\nfrom IPython.display import display, Markdown, Image\nROOT=Path.cwd()\na=json.loads((ROOT/'results/md_astar/analysis.json').read_text())\nassert a['status']=='passed'\nfor path,sha in a['environment']['sha256'].items():\n    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,path\nprint({k:a[k] for k in ['cases','snapshot_records','runs','query_calls']})\nprint({k:a['environment'][k] for k in ['python','numpy','cpu','workers']})"),
        nbf.v4.new_markdown_cell('## Прямое сравнение с общим ядром\n\nОтношение времени MPGAA* к MD-A*: больше единицы означает выигрыш оболочки. Сначала суммируются перепланирования эпизода, затем берутся медиана трёх повторений и медиана парных отношений. Это не отношение двух несвязанных средних и не сравнение с историческими секундами.'),
        nbf.v4.new_code_cell("rows=['| Набор | Ускорение | Выигрыши | Весь эпизод |','|---|---:|---:|---:|']\nfor co in ['original','mixed','validation','diagnostic']:\n    x=a['comparisons'][co+':mpgaa']['online_s'];y=a['comparisons'][co+':mpgaa']['episode_s']\n    rows.append(f'| {co} | {x[\"median\"]:.3f} | {x[\"wins\"]}/{x[\"n\"]} | {y[\"median\"]:.3f} |')\ndisplay(Markdown('\\n'.join(rows)))"),
        nbf.v4.new_code_cell("display(Image(filename=str(ROOT/'docs/md_astar/figures/comparison.png')))\ndisplay(Image(filename=str(ROOT/'docs/md_astar/figures/transfer.png')))"),
        nbf.v4.new_markdown_cell('## Механизм и абляции\n\n`md64` меняет силу клеточной оценки, `md_scan` — только просмотр отложенных клеток. Базовый MPGAA* общий. Приближённый Mesh/ParallA* оценивается вместе со стоимостью пути; его скорость не является преимуществом точного поиска.'),
        nbf.v4.new_code_cell("display(Image(filename=str(ROOT/'docs/md_astar/figures/mechanism.png')))\nfor co in ['original','mixed','validation','diagnostic']:\n    m=a['cohorts'][co]['methods']['mesh_parall']\n    print(co,'Mesh/Parall max cost/optimum:',m['max_suboptimality_global'],'nonoptimal query records:',m['nonoptimal_queries'])"),
        nbf.v4.new_markdown_cell('## Проверка корректности и качество работы\n\nНезависимый Dijkstra не использует эвристику или классы графов планировщиков. Отдельная проверка охватывает все 561 исходных запроса. Проверены покрытые клетки, курсы и стоимость примитивов, разрез/открытие карты, возвраты старта и реактивация старого освобождения. Математическая теорема относится к идеальной арифметике; float-реализация проверяется с допуском `1e-6`.'),
        nbf.v4.new_code_cell("for name in ['verification.json','full_verification.json']:\n    x=json.loads((ROOT/'results/md_astar'/name).read_text());assert x['status']=='passed'\n    print(name,{k:v for k,v in x.items() if k in ['status','oracle_snapshots','instances','queries','comparisons','path_validations']})\nprint('Compiler milliseconds:',1000*a['environment']['certificate_compile_s'])"),
        nbf.v4.new_markdown_cell('Сильные стороны: нативная интеграция, отдельный причинный контроль, зафиксированные данные, последовательные повторения, независимые проверки. Ограничения: четыре карты, один основной набор примитивов, небольшой временной поднабор, фиксированная цель, 2D-проверки коллизий, не подтверждённый внешний приоритет. Исходные задачи специально ломают путь и не содержат освобождений: диагностический выигрыш нельзя переносить на эту постановку.\n\nДля нового измерения нужно сохранить старые `raw.jsonl`, `environment.json`, `completion_*.json` под другими именами и выполнить команды из [README](docs/md_astar/README.md). Этот ноутбук читает зафиксированные данные, а не запускает поиск заново.')
    ]
    for cell in nb.cells:
        if cell.cell_type=='markdown':cell.source=stars(cell.source)
    target=ROOT/'md_astar.ipynb'
    if execute:
        from nbclient import NotebookClient
        nb=NotebookClient(nb,timeout=120,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbf.write(nb,target)
    print('Wrote',target,'executed' if execute else 'unexecuted')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args();main(args.execute)
