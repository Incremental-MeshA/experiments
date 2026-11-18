#!/usr/bin/env python3
"""Analyze complete C++ runs only; Python execution times never enter ratios."""
import argparse
import csv
import hashlib
import json
import re
import statistics as stats
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def analyze(path):
    path = path.resolve()
    meta = json.loads(Path(str(path)+'.json').read_text())
    provenance = json.loads(Path(str(path)+'.provenance.json').read_text())
    assert meta['status'] == provenance['status'] == 'passed'
    assert not meta['verify_only'] and meta['ndebug'] and not meta['fast_math'], 'Use an unsanitized release run for timings'
    assert digest(path) == provenance['csv_sha256']
    assert digest(Path(str(path)+'.json')) == provenance['completion_sha256']
    for name, sha in provenance['source_sha256'].items():
        assert digest(ROOT/name) == sha, name
    input_path = ROOT/provenance['input_relative'] if provenance.get('input_relative') else Path(meta['input'])
    assert digest(input_path) == provenance['input_sha256']
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == meta['queries']
    keys = {(r['case'], r['method'], int(r['repeat']), int(r['query'])) for r in rows}
    assert len(keys) == len(rows), 'Duplicate query rows'
    grouped = defaultdict(list)
    cohorts = defaultdict(set)
    for r in rows:
        grouped[r['case'], r['method'], int(r['repeat'])].append(r)
        cohorts[r['cohort']].add(r['case'])
    cases = {r['case'] for r in rows}
    assert len(cases) == meta['episodes'] and len(grouped) == meta['runs']
    for case in cases:
        for method in meta['methods']:
            for repeat in range(meta['repeats']):
                assert (case, method, repeat) in grouped, 'Incomplete paired episode'
    per_case = {}
    sequence_rows = []
    for case in sorted(cases):
        for method in meta['methods']:
            values = []
            for repeat in range(meta['repeats']):
                q = grouped[case, method, repeat]
                assert sorted(int(r['query']) for r in q) == list(range(len(q)))
                values.append((sum(float(r['time_s']) for r in q if int(r['query']) > 0),
                               sum(float(r['time_s'])+float(r['setup_s']) for r in q)))
            online = stats.median(v[0] for v in values)
            episode = stats.median(v[1] for v in values)
            per_case[case, method] = dict(online_s=online, episode_s=episode)
            sequence_rows.append(dict(case=case, method=method, online_s=online, episode_s=episode))
    result = dict(status='passed', csv_sha256=digest(path), runs=meta['runs'], queries=meta['queries'],
                  compiler=meta['compiler'], flags=meta['build_flags'], cpu=provenance['cpu'],
                  numerical_tolerance=1e-6, cohorts={})
    text = '# C++: результаты самостоятельного прогона\n\n'
    text += (f'Компилятор: {meta["compiler"]}; флаги: `{meta["build_flags"]}`; CPU: {provenance["cpu"]}. '
             f'{meta["runs"]} полных запусков, {meta["queries"]} вызовов, {meta["repeats"]} повтора. '
             'Все точные стоимости совпали с контролем с допуском `1e-6`, каждый путь проверен по покрытым клеткам и курсам. '
             'Mesh/ParallA* остаётся приближённым.\n\n'
             'Онлайн — запросы после первичного. Эпизод включает конструктор и первичный поиск. '
             'В каждой паре берётся медиана трёх сумм (или указанного числа повторов), затем медиана отношений по эпизодам. '
             'Ускорение больше единицы означает преимущество кандидата. Это описательные измерения на фиксированной коллекции; '
             'интервалы обобщения на другие карты не оцениваются. Времена Python и старого C++-артефакта не используются.\n\n')
    for cohort, ids in sorted(cohorts.items()):
        info = {}
        text += f'## {cohort}: {len(ids)} эпизодов\n\n'
        text += '| Метод | К LBA*, онлайн | К LBA*, эпизод | Макс. стоимость / оптимум |\n|---|---:|---:|---:|\n'
        for method in meta['methods']:
            own = [r for r in rows if r['cohort'] == cohort and r['method'] == method]
            online = [r for r in own if int(r['query']) > 0]
            ratios = [float(r['suboptimality']) for r in own if r['suboptimality']]
            z = dict(max_suboptimality=max(ratios, default=1),
                     certified_fraction=sum(int(r['certified']) for r in online)/len(online) if online else 0)
            for metric in ['online_s', 'episode_s']:
                if 'lba' in meta['methods']:
                    z[metric+'_speedup_lba'] = stats.median(per_case[c, 'lba'][metric]/per_case[c, method][metric] for c in ids)
            info[method] = z
            if 'lba' in meta['methods']:
                text += f'| {method} | {z["online_s_speedup_lba"]:.3f} | {z["episode_s_speedup_lba"]:.3f} | {z["max_suboptimality"]:.6f} |\n'
        if {'mpgaa', 'md_astar'} <= set(meta['methods']):
            ratios = [per_case[c, 'mpgaa']['online_s']/per_case[c, 'md_astar']['online_s'] for c in ids]
            z = dict(median=stats.median(ratios), minimum=min(ratios), maximum=max(ratios), wins=sum(x > 1 for x in ratios), n=len(ratios))
            z['episode_median'] = stats.median(per_case[c, 'mpgaa']['episode_s']/per_case[c, 'md_astar']['episode_s'] for c in ids)
            info['md_vs_mpgaa'] = z
            text += (f'\nПрямая пара MD-A* относительно общего MPGAA*: **{z["median"]:.3f}×**, '
                     f'диапазон {z["minimum"]:.3f}–{z["maximum"]:.3f}×; быстрее в {z["wins"]}/{z["n"]} эпизодов. '
                     f'С первичным поиском и конструктором: {z["episode_median"]:.3f}×. '
                     f'Доля ответов MD-A* без вызова ядра: {100*info["md_astar"]["certified_fraction"]:.1f}%.\n\n')
        result['cohorts'][cohort] = info
    text += ('## Границы сравнения\n\nОбщая модель и сертификат подготовлены за таймером; цена подготовки и компилятора '
             'есть в completion JSON. Конструкторы измерены отдельно. Таймер каждого запроса включает правки, '
             'поиск/ремонт, извлечение пути и служебный индекс сохранённого пути. Проверка ответа выполняется за таймером. '
             'Счётчики разных представлений состояний не являются одинаковыми единицами работы. '
             'Открытия D* Lite обновляют и ранее неизвестные источники; этот простой адаптер не заявляется '
             'максимально оптимизированной реализацией. Прямая пара с общим MPGAA* отделяет вклад MD. '
             'Диагностическая семья специально проверяет несущественные изменения и не представляет средний случай.\n')
    text += ('\nНа исходных задачах нет освобождений и доля сертификатов равна нулю. '
             'Небольшая разница времени MD и MPGAA на этом наборе не доказывает пользу нового '
             'механизма отсрочки: возможны эффекты размещения данных, оптимизации компилятора и шума. '
             'Большое ускорение на диагностике относится к последующим запросам; цена первого поиска '
             'учтена отдельно в метрике полного эпизода. На исходном наборе LBA* быстрее MD-A*.\n')
    target = path.with_suffix('.analysis.json')
    target.write_text(json.dumps(result, indent=2)+'\n')
    text = re.sub(r'(?<!\\)(MD-A|Mesh/ParallA|MPGAA|LBA|D)\*', r'\1\\*', text)
    path.with_suffix('.summary.md').write_text(text)
    with path.with_suffix('.sequence.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=sequence_rows[0], lineterminator='\n')
        writer.writeheader(); writer.writerows(sequence_rows)
    print(target)
    for c, z in result['cohorts'].items():
        print(c, z.get('md_vs_mpgaa', {}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv', type=Path)
    analyze(p.parse_args().csv)
