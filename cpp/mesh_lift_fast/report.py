#!/usr/bin/env python3
"""Russian audit report from the validated fresh measurements."""
import argparse
import json
import math
import os
import re
import subprocess
from pathlib import Path

os.environ.setdefault('XDG_CACHE_HOME', '/tmp/lift_fast_cache')
import pandas as pd
from analyze import HERE, ROOT, DEST, LABEL, gm, sha

def number(value, digits=2):
    return f'{value:.{digits}f}' if pd.notna(value) and math.isfinite(float(value)) else '—'

def table(header, rows):
    def clean(value):
        return str(value).replace('|', '/').replace('\n', ' ')
    return '\n'.join(['| '+' | '.join(map(clean, header))+' |',
                      '| '+' | '.join(['---']*len(header))+' |',
                      *['| '+' | '.join(map(clean, row))+' |' for row in rows]])

def figure(name, caption):
    return f'![{caption}](figures/{name}.png){{width=99%}}'

def render(path, body):
    header = '''---
title: "Lift на исходном mesh: аудит и упрощение"
author: "C++17 research artifact"
lang: ru-RU
documentclass: article
fontsize: 10pt
geometry: [a4paper, margin=21mm]
mainfont: Noto Serif
monofont: Noto Sans Mono
colorlinks: true
toc: true
toc-depth: 2
---

'''
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]*`)', body)
    body = ''.join(part if i % 2 else re.sub(r'(?<=\w)\*(?!\*)', r'\\*', part)
                   for i, part in enumerate(parts))
    path.write_text(header+body.rstrip()+'\n')
    command = ['pandoc', str(path), '-o', str(path.with_suffix('.pdf')), '--pdf-engine=xelatex',
               '--resource-path='+str(DEST), '--include-in-header='+str(ROOT/'docs/experiments/layout.tex'),
               '--lua-filter='+str(ROOT/'cpp/mpgaa_mesh/vector_images.lua')]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    if 'Missing character' in result.stderr:
        raise RuntimeError(result.stderr)
    if result.stderr:
        print(result.stderr)
    return dict(markdown_sha256=sha(path), pdf_sha256=sha(path.with_suffix('.pdf')), command=command)

def main(directory):
    ad = directory/'analysis'
    validation = json.loads((ad/'analysis.json').read_text())
    assert validation['status'] == 'passed' and validation['source_sha256'] == sha(HERE/'analyze.py')
    for name, digest in validation['tables_sha256'].items():
        assert sha(ad/name) == digest, name
    for name, digest in validation['figures_sha256'].items():
        assert sha(ROOT/name) == digest, name
    data = {name:pd.read_csv(ad/(name+'.csv')) for name in [
        'summary', 'map_pairs', 'family_pairs', 'case_metrics', 'completion', 'work',
        'allocation_requests', 'navigation_quality', 'actual_changes', 'setup',
        'initial_pairs', 'caps', 'latency', 'edits_latency']}
    summary, maps, metrics = [data[n] for n in ['summary', 'map_pairs', 'case_metrics']]
    work, allocation = data['work'], data['allocation_requests']
    manifest = json.loads((HERE/'frozen/manifest.json').read_text())
    state = json.loads((directory/'experiment.json').read_text())
    correct = json.loads((HERE/'validation/correctness.json').read_text())
    main = summary[summary.cohort.eq('replay') & summary.control.eq('car16') & summary.panel.eq('main')]
    def result(method, baseline, frame=main):
        d = frame[frame.method.eq(method) & frame.baseline.eq(baseline)]
        assert len(d) == 1, (method, baseline)
        return d.iloc[0]
    fast_lift = result('fast_lift', 'lift_mesh')
    fast_cascade = result('fast_cascade', 'cascade_lift')
    zero_lift = result('zero_lift', 'lift_mesh')
    zero_cascade = result('zero_cascade', 'cascade_lift')
    out = []
    put = out.append
    put('# Результат аудита')
    put('**Перевзвешивание в последних Lift действительно не требуется.** Новые `fast_lift` и '
        '`fast_cascade` работают с исходными нулевыми prefix-дугами и положительной стоимостью '
        'завершения примитива. Удалены потенциалы и лишние шаблоны графа, отдельный флаг '
        '`learned`, копии CLOSED, повторные вычисления base и часть временных выделений памяти. '
        'Все проверки корректности сохранены. Поиск, обучение и политика остаются на полном исходном mesh.')
    put(f"В основной car16 replay-панели упрощённый Lift даёт **{number(fast_lift.full_speedup)}× "
        f"по эпизоду / {number(fast_lift.repair_speedup)}× по ремонту** к прежнему Lift "
        f"({int(fast_lift.pairs)}/48 общих завершённых пар); упрощённый Cascade — "
        f"**{number(fast_cascade.full_speedup)}× / {number(fast_cascade.repair_speedup)}×** "
        f"к прежнему Cascade ({int(fast_cascade.pairs)}/48). Здесь и далее ускорение — время "
        'контроля, делённое на время указанного кандидата; больше 1 выгодно кандидату.')
    put(f"Контроль только без потенциала: Lift **{number(zero_lift.full_speedup)}× full / "
        f"{number(zero_lift.repair_speedup)}× repair**, Cascade **{number(zero_cascade.full_speedup)}× / "
        f"{number(zero_cascade.repair_speedup)}×**. Эти отношения не включают остальные "
        'оптимизации fast и не означают сохранения прежнего порядка раскрытия.')
    put(f"Новая серия содержит {validation['unique_scenarios']} уникальные конфигурации и "
        f"{validation['scheduled_scenarios']} запланированных случаев с учётом отдельной повторной "
        f"абляционной панели: {validation['timed_runs']:,} временных эпизодов и "
        f"{validation['memory_runs']:,} отдельных эпизодов памяти. Расхождений завершённых "
        f"стоимостей с точным эталоном: **{validation['exact_cost_disagreements']}**. "
        f"Остановок по лимиту в одном логическом повторе: {validation['capped_calls']}; "
        'они не засчитываются как ответ «пути нет».')
    put('# Что было лишним')
    put(table(['Деталь прежней реализации', 'Изменение и причина'], [
        ['Потенциал и преобразованные стоимости', 'Одна исходная стоимость; нулевые дуги допустимы.'],
        ['Общие positive/contracted/reverse/boundary шаблоны', 'Самостоятельный Index читает Model.configs; fast их не требует.'],
        ['Флаг learned', 'Участие в ремонте определяется h > initial; исходная оценка уже кэширована.'],
        ['Новый vector для проверки каждой политики', 'Пустая политика проверяется сразу; цепочки используют общий буфер.'],
        ['Новый CLOSED и его копия для closure', 'Один буфер между запросами, сжатие на месте, затем тот же буфер как стек.'],
        ['Closure по всему CLOSED', 'Только выросшие метки; у plain — отсечённые, у Cascade — также обычные для подписок.'],
        ['Повторные min/hypot для base при ремонте', 'Неизменная при фиксированной цели initial хранится в записи.'],
        ['Хеш тройки координат и повторный lookup', 'Целочисленный ключ и try_emplace; проверка границ и переполнения.'],
        ['Поиск slot обратной дуги через std::find', 'Slot хранится в дуге; ремонтная очередь содержит (h,id).'],
        ['Повторяющиеся конечные клетки', 'Для h минимум стоимости по клетке; для отсечения все разные конечные направления.'],
        ['Неиспользуемые finals граничных узлов', 'Не материализуются в новом индексе.'],
        ['Строка ошибки на успешной проверке', 'const char*; строка создаётся только при исключении.'],
        ['Хеш извлечений в каждом поиске', 'Отключён по умолчанию; доступен отдельной trace-абляцией.'],
    ]))
    put('Это инженерное упрощение прежнего метода. Приоритет в литературе или новый алгоритм '
        'только на основании удаления потенциала не заявляются. Оптимизации включены в отдельную '
        'ветку `perf/lift-zero-cost`; исходная версия `49b1df9` и её результаты сохранены.')
    put('# Почему перевзвешивание можно удалить')
    put(r'''В исходном mesh внутренние дуги префикса имеют цену 0, завершения примитивов —
положительную исходную цену. Конфигурационный подграф нулевых дуг является DAG, что новый
индекс проверяет один раз. Поэтому каждый цикл полного графа включает положительное
завершение. A* с согласованной эвристикой и обратный ремонт допускают неотрицательные
стоимости. В tight-политике вдоль положительной дуги строго уменьшается $h$, а нулевые
дуги продвигаются по конечному DAG. Цикл tight-политики невозможен. Строгая положительность
каждой внутренней дуги для этого не требуется.

При точной арифметике старое преобразование давало $g'=g+\phi$,
$h'=h-\phi$ и $f'=g+h$ (у граничного старта $\phi=0$). Но второй ключ $-g'$
не совпадает с $-g$: он также предпочитал глубокие префиксы. Поэтому zero-only использует
$(f,-g,seq)$, а fast — $(f,-g,-depth,seq)$. Последний ключ явно задаёт глубину только
при равных $f,g$ и не воспроизводит прежний смешанный ключ побитово. Отдельная абляция
`fast_no_depth` проверяет цену такого выбора. Кроме того, удаление сложения/вычитания
потенциала меняет округление float-ключей; идентичность раскрытий старой версии не обещается.''')
    put('## Что удалять нельзя')
    put(r'''Необходимы локальный подъём пропущенных внутренних оценок, обратный ремонт
после освобождений, проверка tight-политики, терминальное отсечение с учётом конечного
направления и подпись нарушенных заблокированных неравенств у Cascade. После успешного
поиска с ценой $C$ обновление $h(u)=\max(h(u),C-g(u))$ само по себе может нарушить
согласованность в пропущенном mesh-префиксе. Closure устраняет это нарушение.

Сам бит learned избыточен при наличии неизменной initial: достаточно $h>initial$.
Смысл прежнего инварианта остаётся: поднятый без раскрытия узел обязан участвовать
в ремонте. Если оценка уменьшилась до initial, она всё ещё распространяет уменьшение
назад как элемент очереди; пропускаются только предшественники, которые сами равны base.
На детерминированном C++-контрпримере после двух освобождений все шесть проверяемых
вариантов дают оптимальную цену 4. Прежние мутации без closure или без участия поднятых
узлов в ремонте давали цену 5; их результаты сохранены в предыдущем отчёте.''')
    put(r'''Сужение closure следует из обычного адаптивного обновления. Для раскрытого $u$
свободный ребёнок $v$ либо CLOSED с новой оценкой не меньше $C-g(v)$, либо остаётся
в OPEN с $f(v)\ge C$. В обоих случаях $h(v)\ge C-g(u)-c(u,v)$. Поэтому новое свободное
нарушение возникает только у отсечённого узла. У Cascade выросшие обычные CLOSED
тоже проверяются для новых подписок на заблокированных дугах. Невыросшие метки
не создают новых нарушений; дополнительная топологическая очередь не требуется.
Подробности: [design.md](design.md).''')
    put('# Протокол и пределы сравнения')
    put('Основная replay-панель car16: шесть карт, два прежних корня, четыре семейства '
        '(изменения на эталонном маршруте, вне маршрута, смешанные блокировки/освобождения, '
        'раскрытие неизвестной карты), всего 48 конфигураций. Grid8: четыре плотности '
        'random50, все сочетания `cr=1,5,10,30%` и `k=2,8,32`, один корень; `n=k`, '
        'всего 48 конфигураций. Это одинаковые фиксированные последовательности входов '
        'для всех методов. Двенадцать car on-path/churn случаев первого корня повторены '
        'с отдельными ID для компонентной абляции и не объединяются с основной панелью.')
    put('Автономная навигация: те же шесть car-карт, один корень, раскрытие с радиусами '
        '8, 32 и 64 клетки и динамика `(k,cr)=(2,5%), (8,10%), (32,20%)`, `n=k`. '
        'Статический радиус — квадратная окрестность; динамическая видимость — глубина '
        'по свободной решётке примитивов с учётом направления и всех клеток их трасс. '
        'Move означает один примитив. При каждой фазе блокируются и освобождаются равные '
        'числа случайных клеток; число правок ограничено доступными клетками, фактический '
        'cr показан ниже. Связанные n и k не позволяют приписать эффект одному параметру.')
    put('Карты Berlin, AR0700 и arena используются в прежнем размере; MA_maze96, '
        'MA_room96 и MA_random96 — прежние фиксированные кропы Moving AI. Control set '
        'car16 и его стоимости неизменны; это примитивы данного репозитория, а не '
        'официальный оптимизированный набор из статьи MeshA*. Grid8 не имеет длинных '
        'общих префиксов и служит структурным контролем. Все входы уже использовались '
        'раньше; независимый holdout не заявляется.')
    put(f"Срез и исходники заморожены {manifest['frozen_utc']}; измерения начаты "
        f"{state['utc']} на commit `{state['source_commit'][:12]}`. CPU: {state['cpu']}; "
        f"{state['platform']}; один процесс, affinity {state['affinity']}. Контроли собраны "
        'заново тем же GCC и флагами `-O3 -DNDEBUG -std=c++17`; точные флаги и хеши '
        'есть в JSON. Три последовательных повтора со случайным порядком методов и '
        'отдельный allocation-проход. Эталон и проверка пути не входят во время поиска.')
    put('Full включает конструктор планировщика и все запросы; initial — конструктор '
        'и запрос 0; repair — запросы после 0. Общая подготовка шаблонов исключена '
        'из этих часов одинаково для всех методов и измерена отдельным микробенчмарком. '
        'Таблицы используют медиану трёх времён каждой конфигурации, затем геометрическое '
        'среднее парных отношений по общим завершённым конфигурациям. В replay точное '
        '«пути нет» — завершённый ответ; в навигации завершение требует достичь цели. '
        'Разная политика равностоимостных путей меняет наблюдения и иногда последующую '
        'динамику: навигационные времена не являются сравнением на одинаковых запросах.')
    put(f"Бюджет — {manifest['cap']:,} раскрытий на вызов; допуск стоимости $10^{{-6}}$. "
        f"Медиана относительного MAD полных времён — {100*validation['repeat_relative_mad_median']:.2f}%, "
        f"p95 — {100*validation['repeat_relative_mad_p95']:.2f}%. Три повтора характеризуют "
        'шум этой машины, а не независимые карты или доверительный интервал переносимости.')
    put('# Результаты по времени')
    rows = []
    for control in ['car16', 'grid8']:
        d = summary[summary.cohort.eq('replay') & summary.control.eq(control) & summary.panel.eq('main')]
        for method, baseline in [('zero_lift','lift_mesh'), ('zero_cascade','cascade_lift'),
                                 ('fast_lift','lift_mesh'), ('fast_cascade','cascade_lift')]:
            v = result(method, baseline, d)
            rows.append([control, LABEL[method], f'{int(v.pairs)}/48', number(v.full_speedup),
                         number(v.initial_speedup), number(v.repair_speedup), number(v.memory_multiplier)])
    put(table(['Модель','Кандидат к прежнему','Пары','Full ×','Initial ×','Repair ×','Peak / old'], rows))
    put('Initial в этой таблице условен на завершение всего эпизода. Для проверки '
        'возможного смещения отдельный файл `initial_pairs.csv` сохраняет все общие '
        'завершённые первые поиски независимо от исхода позднего ремонта.')
    rows = []
    for method, baseline in [('fast_lift','lift_mesh'), ('fast_cascade','cascade_lift'),
                             ('zero_lift','lift_mesh'), ('zero_cascade','cascade_lift')]:
        d = data['initial_pairs'];d = d[d.cohort.eq('replay') & d.control.eq('car16') & d.method.eq(method) & d.baseline.eq(baseline)]
        rows.append([LABEL[method], f'{int(d.complete.sum())}/{len(d)}', number(gm(d.speedup))])
    put(table(['Первые поиски car16','Пары','Ускорение initial ×'], rows))
    put(figure('maps', 'Новые и zero-only варианты относительно соответствующей прежней weighted-версии. Средние по восьми случаям каждой car-карты; неполные пары исключены из отношений, но отражены в таблицах завершения.'))
    rows = []
    for control in ['car16', 'grid8']:
        d = maps[maps.cohort.eq('replay') & maps.control.eq(control) & maps.panel.eq('main')]
        for name, group in d.groupby('map'):
            for method, baseline in [('fast_lift','lift_mesh'), ('fast_cascade','cascade_lift')]:
                v = result(method, baseline, group)
                rows.append([name, 'Lift' if method=='fast_lift' else 'Cascade',
                             f'{int(v.pairs)}/{int(v.configurations)}', number(v.full_speedup),
                             number(v.repair_speedup), number(v.memory_multiplier)])
    put(table(['Карта','Fast к old','Пары','Full ×','Repair ×','Peak / old'], rows))
    put('## Сравнение с остальными контролями')
    rows = []
    for control, cohort in [('car16','replay'), ('grid8','replay'),
                            ('car16','navigation_unknown'), ('car16','navigation_dynamic')]:
        d = summary[summary.control.eq(control) & summary.cohort.eq(cohort) & summary.panel.ne('ablation')]
        for method in ['fast_lift', 'fast_cascade']:
            for baseline in ['mesha_reuse', 'batch_mpgaa', 'octile_reuse']:
                g = d[d.method.eq(method) & d.baseline.eq(baseline)]
                if len(g):
                    v = g.iloc[0]
                    rows.append([control+'/'+cohort.replace('navigation_', ''),
                                 'Lift' if method=='fast_lift' else 'Cascade', LABEL[baseline],
                                 f'{int(v.pairs)}/{int(v.configurations)}', number(v.full_speedup), number(v.repair_speedup)])
    put(table(['Набор','Fast','Контроль','Пары','Full ×','Repair ×'], rows))
    put('Обе fast-версии сохранены независимо от того, какая быстрее в конкретном режиме. '
        'Преимущество над старой неоптимизированной реализацией не доказывает превосходство '
        'над Batch-MPGAA* или MeshA* reuse. Полные парные отношения, включая проигрыши, '
        'сохранены в `paired_cases.csv`; разбиение по семействам — в `family_pairs.csv`.')
    put('# Завершение и качество пути')
    put(figure('completion', 'Replay: точное решение или доказанное отсутствие пути. Навигация: достижение цели. Zero-only не запускался в автономной навигации; соответствующие клетки отмечены явно.'))
    rows = []
    for _, v in data['completion'].sort_values(['control','cohort','panel','method']).iterrows():
        if v.panel == 'ablation':
            continue
        rows.append([v.control, v.cohort.replace('navigation_', ''), LABEL[v.method], f'{int(v.complete)}/{int(v.configurations)}'])
    put(table(['Модель','Сценарий','Метод','Завершено'], rows))
    caps = data['caps']
    if len(caps):
        put(table(['Метод','Фаза','Остановки'], [[LABEL[m], phase, len(g)] for (m,phase),g in caps.groupby(['method','phase'])]))
    else:
        put('Остановок по числу раскрытий в этой серии нет.')
    put('## Раскрытие карты с разным радиусом')
    put(figure('radius', 'Полное время планировщика по каждой карте и радиусу. Крестики означают незавершённую миссию; малое время такого случая не интерпретируется как ускорение решения.'))
    quality = data['navigation_quality']
    rows = []
    for case, g in metrics[metrics.cohort.eq('navigation_unknown')].groupby('case'):
        d = g.set_index('method');a, b = d.loc['fast_cascade'], d.loc['cascade_lift']
        qa = quality[quality['case'].eq(case) & quality.method.eq('fast_cascade')].iloc[0]
        rows.append([a['map'], int(a.radius), qa.status, number(1000*a.full_s),
                     number(b.full_s/a.full_s) if a.complete and b.complete else '—', number(qa.static_stretch)])
    put(table(['Карта','Радиус','Fast Cascade','Full, мс','К old ×','Путь / truth opt'], rows))
    put('Отношение пути к оптимуму полной статической карты описывает цену неизвестности, '
        'а не подоптимальность каждого запроса: все завершённые планы точны на текущей '
        'известной карте. Для динамического мира такое отношение к начальному оптимуму '
        'не используется; абсолютные длины, шаги и статусы всех методов есть в `navigation_quality.csv`.')
    put('## Динамика при n=k и фактическом cr')
    rows = []
    for case, g in metrics[metrics.cohort.eq('navigation_dynamic')].groupby('case'):
        d = g.set_index('method');a, b = d.loc['fast_cascade'], d.loc['cascade_lift']
        change = data['actual_changes'];v = change[change['case'].eq(case) & change.method.eq('fast_cascade')].iloc[0]
        qa = quality[quality['case'].eq(case) & quality.method.eq('fast_cascade')].iloc[0]
        rows.append([a['map'], int(a.k), int(a.cr), number(v.actual_cr),
                     f'{int(v.clamped)}/{int(v.phases)}', qa.status, number(b.full_s/a.full_s) if a.complete and b.complete else '—'])
    put(table(['Карта','k=n','cr, %','Факт., %','Clamp/фаз','Fast Cascade','К old ×'], rows))
    put('Если фаз нет, фактический cr не определён и обозначен тире. Недостижение цели '
        'при динамике может означать реальную разрывность текущей карты; это не автоматически '
        'ошибка поиска. `no_path_diagnostics.csv` сохраняет проверку истинной достижимости '
        'при таких остановках. В статической неизвестной карте ложных отказов при достижимой '
        'истинной цели не обнаружено.')
    put('# Абляции и работа алгоритмов')
    put(figure('ablation', 'Одна компонента изменена относительно fast_cascade на отдельной панели из 12 повторных car-сценариев. Отношение выше 1 показывает пользу соответствующей оптимизации; tie-breaking может менять сам поиск.'))
    rows = []
    d = summary[summary.panel.eq('ablation')]
    for _, v in d.iterrows():
        rows.append([LABEL[v.baseline], f'{int(v.pairs)}/{int(v.configurations)}',
                     number(v.full_speedup), number(v.repair_speedup), number(v.memory_multiplier)])
    put(table(['Возвращённая деталь','Пары','Full ×','Repair ×','Fast peak / ablation'], rows))
    put(f"У абляций одинакового приоритета подтверждено совпадение пути, числа раскрытий, "
        f"стоимости и статуса в {validation['ablation_identical_path_rows']:,} строках. "
        '`fast_no_depth` из этого требования исключён, поскольку меняет правило выбора '
        'равных ключей. Для него действуют те же проверки точной стоимости. Компоненты '
        'целочисленного ключа, компактной ремонтной записи, ленивого сообщения ошибки и '
        'отсутствия learned-бита входят в общий пакет; их отдельный причинный вклад '
        'этой серией не оценивался.')
    put(figure('work', 'Суммы событий только ремонта основной car16 replay-панели, один логический повтор. Единицы разных столбцов не взаимозаменяемы; к значениям добавлена 1 только для логарифмической оси.'))
    rows = []
    for method in ['lift_mesh','cascade_lift','zero_lift','zero_cascade','fast_lift','fast_cascade']:
        d = work[work.panel.eq('main') & work.control.eq('car16') & work.phase.eq('repair') & work.method.eq(method)]
        rows.append([LABEL[method], int(d.expansions.sum()), int(d.lift_edges.sum()),
                     int(d.lift_writes.sum()), int(d.mv_policy_tests.sum()), int(d.checked_cells.sum())])
    put(table(['Метод','Раскрытия','Closure дуги','Подъёмы h','Policy tests','Grid.free'], rows))
    put('`checked_cells` у всех шести Lift/zero/fast считает каждый вызов Grid.free внутри '
        'replan, включая концы и внешние клетки. У MeshA* reuse и Batch-MPGAA* унаследованный '
        'счётчик покрывает лишь часть проверок, поэтому его межсемейное отношение здесь '
        'не используется. Это логические вызовы API, не аппаратные чтения памяти. '
        'Показатели `fast_base_evaluations` и `fast_closure_seeds` инструментированы '
        'только для fast; нули в строках прежних контролей не означают отсутствия такой работы.')
    put('## Выделения памяти и общий индекс')
    rows = []
    for method in ['lift_mesh','cascade_lift','zero_lift','zero_cascade','fast_lift','fast_cascade']:
        d = allocation[allocation.panel.eq('main') & allocation.control.eq('car16') & allocation.method.eq(method)]
        values = d.groupby('phase').allocation_calls.sum()
        rows.append([LABEL[method], int(values.get('initial', 0)), int(values.get('repair', 0))])
    put(table(['Метод','Запросы allocation: initial','Запросы allocation: repair'], rows))
    put('Запросы new считаются строго внутри replay replan в отдельном allocation-бинаре. '
        'Конструктор планировщика, эталон и форматирование CSV в этот счётчик не входят. '
        'Навигационные allocation requests не измерялись. Requested peak/retained heap '
        'включает рабочие записи и возвращённые пути, исключает общий заранее построенный '
        'индекс; это не RSS. Новая запись хранит initial и потому сама может быть крупнее '
        'старой; уменьшение числа временных выделений не гарантирует уменьшения peak.')
    rows = []
    for _, v in data['setup'].sort_values(['model','method']).iterrows():
        rows.append([v.model, v.method.replace('_',' '), number(1e6*v.time_s),
                     int(v.peak_heap_bytes), int(v.retained_heap_bytes), int(v.allocation_calls)])
    put(table(['Модель','Построение индекса','Медиана, мкс','Peak, B','Retained, B','New calls'], rows))
    put('Этот микробенчмарк выполнен после основной временной фазы: 100 повторов каждого '
        'конструктора со случайным порядком, отдельный проход памяти. `legacy templates` '
        'включает весь прежний Prepared + MeshIndex; `direct raw` и `direct dedup` '
        'строят только самостоятельный новый индекс. Разница с legacy включает удаление '
        'накопленных общих шаблонов и не приписывается одному потенциалу. В совместном '
        'harness все индексы существуют для доступности контролей; производственный fast '
        'не имеет этой зависимости. Подготовка Model и чтение файла не входят в эти часы.')
    put('# Проверки и оценка работы')
    put(f"Независимый primitive Dijkstra проверил **{correct['comparisons']:,}** ответов "
        '(12 seed-карт на модель, 40 последовательных запросов, десять новых режимов): '
        'движущийся старт, закрытые концы, повторные и смешанные правки, ограничение '
        'по раскрытиям и последующее восстановление с увеличенным бюджетом. Аудируются '
        'свободные неравенства согласованности, нижняя граница base и полнота подписок. '
        'Дополнительный C++-пример проверяет ремонт после освобождений в шести режимах '
        'и явный отказ от конфигурационного нулевого цикла вне класса prefix-DAG. '
        'ASan/UBSan и проверка утечек пройдены для обеих моделей.')
    put(f"В полной серии обычный и allocation-бинарь совпали по логическим полям "
        f"в {validation['allocation_matched_rows']:,} строках вызовов и "
        f"{validation['allocation_matched_episodes']:,} навигационных эпизодах. "
        f"Счётчики подтверждают {validation['terminal_prunes']:,} терминальных отсечений "
        f"и {validation['lift_writes']:,} подъёмов h. Исходные файлы контролей не менялись; "
        'их хеши проверяются вместе с источниками новой версии.')
    put('Корректность поддерживается доказательством для неотрицательного prefix-mesh, '
        'независимыми тестами и эталоном на измеренных запросах. Практическая полезность '
        'оценивается по свежим парным временам, завершению и памяти. Готовность к статье '
        'улучшена за счёт более простой постановки и реализации, но сами эти оптимизации '
        'не являются достаточным основанием заявлять новый SOTA-алгоритм. Сильное '
        'сравнение с независимыми оптимизированными реализациями и более широким control set '
        'остаётся отдельной исследовательской задачей.')
    put('Ограничения: фиксированная цель, данный класс prefix-DAG и примитивов; шесть car-карт '
        'и один control set; один корень на автономную параметрическую точку; три временных '
        'повтора; повторное использование известных входов; дешёвые 2D-проверки клеток. '
        'Нет доказательства выигрыша для произвольных моделей, нулевых циклов или дорогой '
        'геометрической проверки. Не все оптимизации аблированы отдельно. Результат '
        'показывает, какие детали реализации можно убрать при сохранении точности.')
    put('# Артефакт и воспроизведение')
    put('Ветка `perf/lift-zero-cost`. Код: [алгоритмы](../../cpp/mesh_lift_fast/algorithms.hpp), '
        '[индекс](../../cpp/mesh_lift_fast/index.hpp), [zero-only](../../cpp/mesh_lift_fast/zero_only.hpp). '
        'Входы и хеши: `cpp/mesh_lift_fast/frozen/manifest.json`; сырые повторы: '
        '`cpp/mesh_lift_fast/results/full`; производные таблицы: подкаталог `analysis`; '
        'протокол проверки: `cpp/mesh_lift_fast/validation`. Полные команды приведены '
        'в [README](../../cpp/mesh_lift_fast/README.md). Секунды предыдущих серий не смешиваются с этой.')
    put('```bash\nmake -C cpp/mesh_lift_fast -j2 all\nmake -C cpp/mesh_lift_fast test\n'
        'python3 cpp/mesh_lift_fast/run_all.py --output /tmp/lift-fast-rerun\n'
        'python3 cpp/mesh_lift_fast/run_setup.py --output /tmp/lift-fast-setup-rerun\n'
        'python3 cpp/mesh_lift_fast/analyze.py --directory /tmp/lift-fast-rerun --setup-directory /tmp/lift-fast-setup-rerun\n'
        'python3 cpp/mesh_lift_fast/report.py --directory /tmp/lift-fast-rerun\n```')
    rendered = render(DEST/'report.md', '\n\n'.join(out))
    rendered.update(status='passed', report_source_sha256=sha(Path(__file__)),
                    analysis_sha256=sha(ad/'analysis.json'))
    (DEST/'report_validation.json').write_text(json.dumps(rendered, ensure_ascii=False, indent=2)+'\n')
    print('REPORT_PASSED', DEST/'report.pdf')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE/'results/full')
    main(parser.parse_args().directory)
