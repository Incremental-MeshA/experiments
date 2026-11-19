#!/usr/bin/env python3
"""Generate the mesh-variant supplement and an includable report chapter."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from analyze import HERE,ROOT,LABELS,METHODS,NEW,VARIANTS,FOCUS,MAIN,digest

TITLES={'car16:on_path':'Car16: вставки на пути','car16:off_path':'Car16: вставки вне пути',
        'car16:churn':'Car16: блокировки и освобождения','car16:unknown_replay':'Car16: раскрытие карты (replay)',
        'grid8:paper_dynamic':'Grid8: локально наблюдаемая динамика',
        'car16:unknown_mission':'Car16: собственная навигация','grid8:unknown_mission':'Grid8: собственная навигация','car16:history':'Car16: диагностика истории'}


def num(v,n=2):return '—' if v is None else f'{v:,.{n}f}'.replace(',',' ')
def label(m):return LABELS[m].replace('*',r'\*') if m else 'нет'
def ratio(z):return ('—' if z['median'] is None else num(z['median'])+'×')+f' ({z["n"]}/{z["total"]})'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def figure(name,caption):return f'![{caption}](mesh_figures/{name}.png){{width=100%}}'


def build(directory,pdf=True):
    analysis_path=directory/'analysis/analysis.json';a=json.loads(analysis_path.read_text());assert a['status']=='passed'
    assert a['analysis_source_sha256']==digest(HERE/'analyze.py')
    assert a['shared_analysis_sha256']==digest(ROOT/'cpp/experiments/analyze.py')
    assert a['manifest_sha256']==digest(HERE/'frozen/manifest.json')
    assert a['episode_metrics_sha256']==digest(directory/'analysis/episode_metrics.csv')
    for name,sha in a['raw_sha256'].items():assert digest(directory/name)==sha,name
    figures=json.loads((directory/'analysis/figures.json').read_text());assert figures['status']=='passed'
    assert figures['analysis_sha256']==digest(analysis_path) and figures['source_sha256']==a['analysis_source_sha256']
    for path,sha in figures['files'].items():assert digest(ROOT/path)==sha,path
    verification=json.loads((HERE/'results/verification.json').read_text());assert verification['status']=='passed'
    state=json.loads((directory/'experiment.json').read_text());manifest=json.loads((HERE/'frozen/manifest.json').read_text())
    for path,sha in {**manifest['source_sha256'],**manifest['contexts_sha256']}.items():assert digest(ROOT/path)==sha,path
    g=a['groups'];out=[]
    def add(s):out.append(s.strip()+'\n')
    add('# Дополнение: C-Mesh-D* Lite, Suffix-Mesh и Boundary-Mesh')
    add(f'''Добавлены три ранее предложенных алгоритма и контроль `prefix_positive`. Все прежние 11 методов повторно запущены вместе с ними: **15 методов, {num(a['timed_runs'],0)} измеряемых запусков, {num(a['timed_rows'],0)} строк, {num(a['planner_calls'],0)} вызовов планировщика**. Отдельный проход памяти содержит {num(a['memory_runs'],0)} запусков и {num(a['memory_rows'],0)} строк. Здесь и далее в этой главе используются только результаты новой совместной серии `cpp/mesh_variants/results/full`; ускорения не вычисляются из времён предыдущей серии.

Входы побайтно совпадают с прежними: 186 replay-эпизодов и 40 параметризованных миссий, три временных повтора, один отдельный проход памяти. Два корня на карту и повторное использование корней при разных параметрах ограничивают независимость выборки. Для всех точных завершённых запросов стоимость сверена с эталоном на той же карте знаний; расхождений **{a['exact_disagreements']}**. Бюджеты, правила движения и определения метрик сохранены.''')
    add('Mesh здесь — граф расширенных клеток, который разделяет collision traces примитивов движения в модели MeshA* (Agranovskiy, Yakovlev). Все новые представления используют тот же физический набор car16: 284 примитива и 16 направлений; вспомогательная grid8 содержит восемь одношаговых движений.')
    mixed=g['car16:churn']
    add('Главный положительный результат — основная car16-серия смешанных правок. Относительно D* Lite lattice ускорение C-Mesh полного эпизода составляет '+ratio(mixed['comparisons']['cmesh_dstar']['dstar_lattice']['episode_s'])+', ремонта — '+ratio(mixed['comparisons']['cmesh_dstar']['dstar_lattice']['online_s'])+'; Boundary-Mesh — '+ratio(mixed['comparisons']['boundary_mesh']['dstar_lattice']['episode_s'])+' и '+ratio(mixed['comparisons']['boundary_mesh']['dstar_lattice']['online_s'])+' соответственно. Ускорение означает время контроля, делённое на время кандидата; число завершённых пар указано в скобках.')
    add('Этот выигрыш не переносится автоматически на более сильные контроли. В той же группе отношение полных времён MD/C-Mesh равно '+ratio(mixed['comparisons']['cmesh_dstar']['md_astar']['episode_s'])+', MD/Boundary — '+ratio(mixed['comparisons']['boundary_mesh']['md_astar']['episode_s'])+'; reuse/C-Mesh — '+ratio(mixed['comparisons']['cmesh_dstar']['lba_reuse']['episode_s'])+', reuse/Boundary — '+ratio(mixed['comparisons']['boundary_mesh']['lba_reuse']['episode_s'])+'. Значения меньше 1 выгодны контролю. Вставки без освобождений и раскрытие карты дают другое ранжирование; далее приведены все режимы, завершение, память и качество проезда.')
    replay_outcomes={r['method']:r for r in a['outcomes'] if r['control']=='car16' and r['mode']=='replay'}
    add('При общем лимите миллиона раскрытий C-Mesh завершил '+str(replay_outcomes['cmesh_dstar']['completed'])+'/90 car16 replay-эпизодов, Suffix-Mesh — '+str(replay_outcomes['suffix_mesh']['completed'])+'/90, Boundary-Mesh — '+str(replay_outcomes['boundary_mesh']['completed'])+'/90; исходный D* Lite mesh и положительный префиксный контроль — '+str(replay_outcomes['dstar_mesh']['completed'])+'/90 и '+str(replay_outcomes['prefix_positive']['completed'])+'/90. Число раскрытий зависит от представления; это преимущество по завершению именно в заданном бюджете, совместно с которым рассматривается время.')
    add('В основной mixed-серии медианное парное отношение пиков requested heap lattice/C-Mesh равно '+ratio(mixed['comparisons']['cmesh_dstar']['dstar_lattice']['peak_heap_bytes'])+', lattice/Boundary-Mesh — '+ratio(mixed['comparisons']['boundary_mesh']['dstar_lattice']['peak_heap_bytes'])+'. Общая модель и подготовка исключены из этих пиков и показаны отдельно; это не RSS процесса.')
    add('## Точные определения алгоритмов')
    add(r'''**C-Mesh-D\* Lite** сжимает префиксный mesh: сохраняются все начальные конфигурации примитивов и узлы, у которых входящая или исходящая степень не равна единице. Цепочка между ними заменяется одной дугой. Её стоимость — сумма весов цепочки, а collision trace содержит **все** внутренние клетки. D\* Lite хранит метки только на оставшихся расширенных состояниях. Это сокращает операции с очередью и таблицей меток, но одна коллизионная проверка макродуги становится длиннее.

**Suffix-Mesh D\* Lite** строится в три шага: развернуть каждый физический примитив; построить префиксный mesh развёрнутого набора; развернуть его дуги и их traces обратно. Полученный граф по-прежнему представляет **прямые исходные** примитивы, но поиск D\* Lite от цели получает общие суффиксы. Метка завершённого примитива расположена на первой прямой дуге, после которой граф обязывает пройти оставшуюся часть примитива. Это не кеш суффикса пути `lba_reuse` и не разрешение движения задним ходом.

**Boundary-Mesh D\* Lite** хранит метки только на `(клетка, heading)` решётки. Для каждой такой исходной позы кешируется маска допустимых полных примитивов. При первом обращении после инвалидации один обход префиксного mesh вычисляет всю маску, проверяя общие начала трасс совместно. Изменение любой клетки поддержки инвалидирует соответствующую маску целиком. Возможен выигрыш в числе проверок клеток, но повторный пересчёт всей маски бывает дороже точечного кеша отдельного примитива у D\* Lite lattice.

**Контроль Positive prefix D\* Lite** использует исходный префиксный mesh, положительные веса и то же новое ядро. Он отделяет изменение представления C-Mesh/Suffix-Mesh от различий нового ядра с прежним D\* Lite mesh. У всех четырёх адаптеров одинаковы очередь, остановка, политика геометрических предшественников и индекс уведомлений.''')
    add('## Сохранение стоимости и корректность ремонта')
    add(r'''Пусть $c_0$ — вес исходной mesh-дуги: ноль на внутреннем переходе и полная стоимость на завершении примитива. В префиксном mesh задаётся потенциал $\rho(q)=\delta\,depth(q)$ для регулярного узла и ноль для начальной конфигурации. Используется

$$c_\rho(u,v)=c_0(u,v)+\rho(v)-\rho(u).$$

$\delta$ выбирается степенью двойки, не большей $c_{min}/[4(d_{max}+1)]$. Внутренние веса положительны, завершающие остаются положительными, а потенциалы полного примитива телескопически сокращаются. Примитивы сохраняют исходные float-стоимости и supercover traces: округления в микростоимости прежнего прототипа нет. В суффиксном графе положительные веса наследуются при развороте, потенциал меняет знак.

Для prefix/C-Mesh обратная эвристика равна евклидову расстоянию от текущего старта до восстановленного начала примитива плюс $\rho$. Для регулярного суффиксного узла берётся минимум «стоимость возможного исходного примитива + расстояние от его исходной позы до текущего старта» минус потенциал развёрнутого префикса. На начальных конфигурациях используется обычное евклидово расстояние. Согласованность следует из неравенства треугольника и ограничения длиной примитива; проверка каждой шаблонной дуги дополнительно включена в артефакт.

Каждый полный переход между начальными конфигурациями соответствует физическому примитиву с исходной ценой и trace. Сжатие удаляет только узлы без выбора, разворот сохраняет язык допустимых последовательностей, а граничная маска точно воспроизводит коллизионную допустимость полных примитивов. Поэтому поиск на этих графах решает исходную задачу при тех же предположениях D\* Lite.

Индекс инвалидации содержит начало, конец и **внутренние** клетки дуг, в том числе запрещённых. Геометрические предшественники регистрируются и через бесконечные дуги: иначе освобождение прохода могло бы не обнаружить ранее недостижимый компонент. Ограничение миллиона раскрытий одинаково по числу, но раскрытие решётки, обычного mesh и макродуги имеет разную цену. Поэтому сокращение раскрытий само по себе не считается ускорением.''')
    add('## Размеры графов и стоимость подготовки')
    add(table(['Модель','Представление','Конфигурации','Дуги','Группы поддержки'],
        [[control,name,num(z['configurations'],0),num(z['edges'],0),num(z['support_groups'],0)]
         for control,info in a['models'].items() for name,z in info['models'].items()]))
    add(table(['Модель','Медиана подготовки 4 шаблонов, мс','Общий retained, KiB','Общий peak, KiB'],
        [[control,num(info['compile_s_median']*1000,3),num(info['common_retained_bytes']/1024,1),num(info['common_peak_bytes']/1024,1)] for control,info in a['models'].items()]))
    add(r'''Общая подготовка выполняется до таймеров планировщиков, отдельно от конструктора каждого экземпляра. В таблице показаны сразу четыре шаблона, их индексы и служебные данные проверки проекций, а не минимальная память одного производственного адаптера. Медиана времени получена по запускам заданий, не по специальному микробенчмарку. В requested heap алгоритма общая подготовка исключена и потому приведена явно.

В car16 C-Mesh содержит 188 вместо 412 конфигураций и 456 вместо 680 дуг. Суффиксный граф содержит 428 конфигураций и 696 дуг, то есть он не меньше префиксного. В grid8 все примитивы одношаговые: prefix, C-Mesh и Suffix-Mesh имеют одинаковый граф из одной конфигурации и восьми дуг. Результаты grid8 характеризуют ремонт и накладные расходы; они не доказывают пользу сжатия или разделения суффиксов.''')
    add('## Совместное сравнение всех 15 методов')
    add('Все ускорения ниже — время бейзлайна, делённое на время кандидата. Сначала берётся медиана трёх сумм по повторам, затем медиана парных отношений по эпизодам. Полный эпизод включает конструктор, первый поиск и ремонт. Время ремонта исключает первый запрос. Числа в скобках — завершённые обоими методы пары из всех задач группы; быстрый отказ не считается решением.')
    add('Mesh/ParallA* — приближённый контроль; остальные 14 методов проверяются как точные. Поисковая стоимость относится к текущей карте знаний; в миссиях отдельно оценивается фактический проезд по истинной карте.')
    add(table(['Метод','На пути','Вне пути','Mixed','Unknown','Grid8'],
        [[label(m),*[num(g[k]['methods'][m]['episode_ms'],3)+f" [{g[k]['methods'][m]['completed']}/{g[k]['methods'][m]['total']}]" for k in MAIN]] for m in METHODS]))
    add('Значения в таблице — медианные **миллисекунды полного эпизода на завершённых задачах**; квадратные скобки показывают завершение. Сравнивать независимые медианы разных завершённых подмножеств как парное ускорение нельзя.')
    add(table(['Режим','Mesh/ParallA*: максимум цена / оптимум текущего запроса'],
        [[TITLES[k],num(g[k]['methods']['mesh_parall']['max_plan_ratio'],4)] for k in MAIN]))
    add('Это наблюдаемый максимум приближённого контроля на завершённых запросах, а не теоретическая граница. Остальные методы проверены на оптимальность каждой завершённой поисковой задачи с допуском 1e-6.')
    add(figure('all_methods','Полный эпизод: парное ускорение против LBA* в новом совместном запуске. Для точек с разной долей завершения необходима таблица исходов.'))
    dispersion=[]
    for m in NEW:
        values=[g[k]['methods'][m]['repeat_relative_mad'] for k in MAIN if g[k]['methods'][m]['repeat_relative_mad'] is not None]
        if values:dispersion.append(label(m)+': '+num(100*min(values),1)+'–'+num(100*max(values),1)+'%')
    add('Медианный относительный MAD трёх повторных времён полного эпизода по основным группам лежит в диапазонах: '+ '; '.join(dispersion)+'. Это диапазоны групповых медиан, не доверительные интервалы; три повтора описывают шум измерения, а не число независимых карт. Близкие к единице ускорения требуют осторожной интерпретации.')
    for base in ['dstar_mesh','dstar_lattice','md_astar','lba_reuse']:
        add('### Новые варианты относительно '+label(base))
        add(table(['Режим','Алгоритм','Эпизод: ускорение','Ремонт: ускорение'],
            [[TITLES[k],label(m),ratio(g[k]['comparisons'][m][base]['episode_s']),ratio(g[k]['comparisons'][m][base]['online_s'])] for k in MAIN for m in NEW]))
    add('### Контроль положительного префикса')
    add(table(['Режим','Алгоритм','Prefix / вариант: эпизод','Prefix / вариант: ремонт'],
        [[TITLES[k],label(m),ratio(g[k]['comparisons'][m]['prefix_positive']['episode_s']),ratio(g[k]['comparisons'][m]['prefix_positive']['online_s'])] for k in MAIN for m in NEW]))
    add(figure('topology_ablation','Три представления относительно общего Positive prefix D* Lite. Значение выше 1 выгодно варианту; пары включают только завершённые обоими эпизоды.'))
    add('### Ремонт конечного пути и доказательство недостижимости')
    add('Чтобы отделить локальный ремонт существующего решения от широкого доказательства отсутствия пути, первичные replay-запросы после первого плана разделены по эталонной достижимости. Для парного времени берутся медианы трёх измерений запроса, затем их суммы внутри каждого случая на общих завершённых запросах и медиана отношений по случаям. Здесь один случай может внести только часть своих запросов; это условная диагностика, которая не заменяет полное время эпизода и профиль с отказами. Покрытие учитывает каждый лимит и пропуск.')
    add(table(['Запросы','Алгоритм','Ответы / все','Лимиты / пропуски','Mesh / вариант','Lattice / вариант','MD / вариант'],
        [[key,label(m),f"{v['methods'][m]['completed']}/{v['snapshots']}",
          f"{v['methods'][m]['capped']} / {v['methods'][m]['skipped']}",
          ratio(v['comparisons'][m]['dstar_mesh']),ratio(v['comparisons'][m]['dstar_lattice']),ratio(v['comparisons'][m]['md_astar'])]
         for key,v in a['reachability_panels'].items() for m in VARIANTS]))
    add('Скобки в трёх последних столбцах показывают число случаев с хотя бы одним общим завершённым запросом из всех случаев, содержащих такую категорию. Точное число парных запросов также сохранено в `analysis.json`. `finite` означает конечную эталонную стоимость на текущей карте знаний, `no_path` — доказанную недостижимость; включены 48 основных car16-сценариев и 96 grid8-сценариев.')
    add('## Карты и область наблюдаемого преимущества')
    add(table(['Карта','Режим','Самый быстрый точный метод'],
        [[r['map'],TITLES[r['group']].replace('Car16: ','').replace('Grid8: ',''),label(r['winner'])] for r in a['map_results'] if r['group'] in MAIN]))
    add('Победитель строки минимизирует сумму медианных времён среди точных методов, завершивших **все** эпизоды строки. Это описательное ранжирование, не тест значимости при близких временах. Строки car16 содержат только два корня; grid8 — параметры на общих корнях.')
    for r in a['map_results']:
        if r['group'] not in MAIN or r['winner'] not in NEW:continue
        eligible=[(r['methods'][m]['sum_episode_s'],m) for m in METHODS if m not in VARIANTS and m!='mesh_parall' and r['methods'][m]['completed']==r['cases']]
        if eligible:
            baseline_time,baseline=min(eligible);own=r['methods'][r['winner']]['sum_episode_s']
            add('На '+r['map']+'/'+r['group'].split(':')[1]+' '+label(r['winner'])+' имеет сумму медианных полных времён '+num(own,6)+' с против '+num(baseline_time,6)+' с у самого быстрого полностью завершившего прежнего контроля '+label(baseline)+'. Отношение этих сумм — '+num(baseline_time/own)+'× на '+str(r['cases'])+' случаях. Это критерий ранжирования строки; медиана парных отношений является другой оценкой.')
    add(figure('map_regimes','Карты car16: парное ускорение новых вариантов относительно D* Lite lattice; в каждой ячейке число завершённых пар. Общая цветовая шкала — log2 ускорения.'))
    for m in NEW:
        wins=[r for r in a['map_results'] if r['group'] in MAIN and r['winner']==m]
        vs=[(k,g[k]['comparisons'][m]['dstar_lattice']['episode_s']) for k in MAIN]
        full=[(k,z) for k,z in vs if z['median'] is not None and z['median']>1 and z['n']==z['total']]
        add(label(m)+': минимальная сумма среди всех полностью завершивших точных методов в '+str(len(wins))+' строках карты/режима'+(': '+ '; '.join(r['map']+'/'+r['group'].split(':')[1] for r in wins) if wins else '')+'. Относительно D* Lite lattice медианное преимущество полного эпизода на полностью парно завершённых группах: '+('; '.join(TITLES[k]+' '+ratio(z) for k,z in full) if full else 'не наблюдается')+'.')
    add('## Работа, задержки и память')
    add(table(['Режим','Метод','Ремонт: раскрытия','Чтения клеток','Просмотры уведомлений','p95 ремонта, мс','Peak, MiB'],
        [[TITLES[k],label(m),num(g[k]['methods'][m]['online_expansions'],0),num(g[k]['methods'][m]['online_checked_cells'],0),
          num(g[k]['methods'][m]['online_notify_probes'],0),num(g[k]['methods'][m]['p95_ms'],3),num(g[k]['methods'][m]['peak_mib'],3)] for k in MAIN for m in FOCUS]))
    add(r'''Работа показана медианой по завершённым эпизодам; p95 условен на завершённых запросах после первого поиска. Пик requested heap берётся по всем эпизодам, включая остановленные. Это не RSS: стек, allocator-метаданные, общая модель и внешняя проверка исключены. Память измеряется только отдельным replay-проходом; его пути и счётчики совпали с обычным бинарником.

У новых вариантов `notify_probes` считает просмотр групп зависимости от изменённых клеток; у MPGAA/MD это их собственная инструментированная работа уведомлений. Счётчики не эквивалентны по цене. Время включает обновления, поиск и извлечение пути; сенсор и контрольная проверка находятся вне таймера.''')
    add(table(['Режим','Метод','Peak lattice / вариант','Peak prefix / вариант','Peak MD / вариант'],
        [[TITLES[k],label(m),ratio(g[k]['comparisons'][m]['dstar_lattice']['peak_heap_bytes']),
          ratio(g[k]['comparisons'][m]['prefix_positive']['peak_heap_bytes']),ratio(g[k]['comparisons'][m]['md_astar']['peak_heap_bytes'])]
         for k in MAIN for m in NEW]))
    add('Отношения памяти — медианы парных отношений наблюдаемых пиков только на эпизодах, полностью завершённых обоими методами. Значение больше 1 означает меньший пик у кандидата. Это отдельная оценка от медианы пиков по всем эпизодам выше; ранняя остановка по бюджету не создаёт ложной экономии в парном отношении.')
    w=a['work_tradeoff_witness']
    if w:
        add(f"Контрпример связи «меньше чтений — быстрее»: {w['map']}/{w['family']}, seed {w['seed']}, запрос {w['query']}. Оба метода доказали недостижимость. Boundary-Mesh выполнил {num(w['reads']['boundary_mesh']/1e6,2)} млн чтений против {num(w['reads']['dstar_lattice']/1e6,2)} млн у D* Lite lattice, но медианное время трёх повторов составило {num(w['times_s']['boundary_mesh'],3)} против {num(w['times_s']['dstar_lattice'],3)} с. Очередь, кеши, повторные Bellman-обновления и представление графа тоже имеют цену. Это выбранный конкретный контрпример, а не оценка частоты такого эффекта.")
    add(figure('work_memory_completion','Раскрытия и чтения клеток ремонта, память и завершение. Представления имеют разные единицы раскрытия. Нули в логарифмических панелях показаны на нижнем уровне.'))
    add('## Размер и частота пакетов изменений')
    add(figure('parameters','Контролируемые car16-панели: пакет mixed, интервал движения mixed и радиус unknown replay. Показана медиана среднего времени ремонта внутри завершённого эпизода.'))
    add('Размер пакета и доля cr — запрошенные параметры; фактически доставленные правки сохранены для каждого запроса. Большой пакет может раньше сделать цель недостижимой и сократить эпизод. Интервал k меняет продвижение старта и число вызовов; радиус меняет знания и последующие пути. Поэтому полное время и среднее время ремонта на запрос рассматриваются вместе, а разные параметры на одном корне не считаются независимыми проездами.')
    add(table(['Панель / режим','Значение','Алгоритм','Эпизод vs lattice','Ремонт vs lattice','Ремонт, мс/вызов'],
        [[p['panel']+'/'+p['family'],str(p['value']),label(m),ratio(p['comparisons'][m]['dstar_lattice']['episode_s']),
          ratio(p['comparisons'][m]['dstar_lattice']['online_s']),num(p['methods'][m]['online_ms_per_query'],3)]
         for p in a['parameters'] if p['panel'] in ['batch','frequency','visibility'] and (p['panel']!='batch' or p['family']=='churn') for m in NEW]))
    add(figure('change_scaling','Задержка по фактически доставленному числу правок. Это описательное объединение карт и режимов, а не причинный эксперимент с фиксированной геометрией. Начальный запрос исключён, завершённые запросы условны на бюджете.'))
    add('### Динамическая grid8-серия по мотивам MPGAA*')
    add(table(['k / cr, %','Алгоритм','Завершено','Эпизод vs lattice','Ремонт, мс/вызов'],
        [[str(p['value'][0])+' / '+str(p['value'][1]),label(m),f"{p['methods'][m]['completed']}/{p['cases']}",
          ratio(p['comparisons'][m]['dstar_lattice']['episode_s']),num(p['methods'][m]['online_ms_per_query'],3)]
         for p in a['parameters'] if p['panel']=='literature_dynamic' for m in NEW]))
    add('Используются те же адаптированные режимы MPGAA* (Hernández, Asín, Baier, AAAI 2015): глобальные изменения мира, локальные наблюдения, k=2/8/32, cr=1/5/10/30%. Карты 50×50 и короткие проезды не воспроизводят оригинальную масштабную постановку. Важны фактические, а не только запрошенные изменения. У трёх mesh-представлений одношаговой grid8 одинаковая топология.')
    add('### Диагностическая история освобождений')
    history=g['car16:history']
    add(table(['Алгоритм','Завершено','Эпизод vs lattice','Ремонт vs lattice','Эпизод vs MD'],
        [[label(m),f"{history['methods'][m]['completed']}/{history['cases']}",
          ratio(history['comparisons'][m]['dstar_lattice']['episode_s']),ratio(history['comparisons'][m]['dstar_lattice']['online_s']),
          ratio(history['comparisons'][m]['md_astar']['episode_s'])] for m in VARIANTS]))
    add('Эти четыре эпизода на открытой карте — диагностический стресс истории, а не репрезентативный навигационный набор. В прежней проверке сертификаты MD с новыми освобождениями в этом тесте совпадали с глобальной евклидовой нижней оценкой. Поэтому большой выигрыш кеша в такой геометрии не доказывает необходимость mesh-сертификата; обычный контроль глобальной LB тоже мог бы решать эти запросы.')
    add('## Полностью неизвестная карта')
    add(table(['Модель','Радиус','Метод','До цели','Проезд / оптимум','Раскрытая доля','Ремонт, мс/вызов'],
        [[p['control'],str(p['value']),label(m),f"{p['methods'][m]['completed']}/{p['cases']}",num(p['methods'][m]['travel_ratio']),
          num(p['methods'][m]['known_fraction']),num(p['methods'][m]['online_ms_per_query'],3)] for p in a['parameters'] if p['panel']=='closed_loop' for m in FOCUS]))
    add(figure('unknown_navigation','Собственное движение на исходно неизвестной карте. Время на завершённых миссиях рассматривается вместе с числом целей и стоимостью фактического проезда.'))
    add('Равностоимостные планы могут вести к разным наблюдениям и разным реальным маршрутам. Для миссий парное время относится к общему миру, а не к одной последовательности запросов. Квадратный сенсор не моделирует окклюзию. Планирование вызывается в начале и при обнаружении препятствий; перед каждым движением примитив проверяется на истинной карте вне таймера.')
    add('## Незавершённые задачи и профили производительности')
    add(table(['Модель / режим','Метод','Завершено','Терминальные исходы'],
        [[r['control']+'/'+r['mode'],label(r['method']),f"{r['completed']}/{r['total']}",'; '.join(k+': '+str(v) for k,v in r['terminals'].items())] for r in a['outcomes']]))
    add(f"В измеряемых строках: {a['cap_rows']} превышений бюджета, {a['skipped_rows']} запросов после остановки по бюджету и {a['step_limited']} остановок движения. Счётчики включают три повтора и не являются числом независимых задач. Недостижимость в replay считается корректно решённой задачей; остановка по бюджету — нет.")
    if a['cap_witnesses']:
        add(table(['Метод','Первый replay-контрпример','Запрос','Раскрытия','Lattice: исход / раскрытия'],
            [[label(r['method']),r['map']+'/'+r['family']+'/'+str(r['seed']),str(r['query']),num(r['variant_expansions'],0),
              r['lattice_status']+' / '+num(r['lattice_expansions'],0)] for r in a['cap_witnesses']]))
        add('Таблица показывает по одному первому зафиксированному превышению бюджета на новый адаптер, без повторного счёта трёх таймингов. Поисковый лимит зависит от представления: миллион mesh-вершин и миллион решётчатых поз не являются одинаковым объёмом физического пространства. Раннюю остановку mesh после части доказательства недостижимости нельзя считать преимуществом перед завершённым доказательством lattice.')
    add('### Преимущество сжатия или ориентации по завершению')
    add(table(['Метод','Контроль','Выигрыши / потери','Пример','Запрос / ответ','Раскрытия: вариант / контроль'],
        [[label(r['method']),label(r['baseline']),str(r['wins'])+' / '+str(r['losses']),
          r['example']['map']+'/'+r['example']['family'] if r['example'] else '—',
          str(r['example']['query'])+' / '+r['example']['own_status'] if r['example'] else '—',
          num(r['example']['own_expansions'],0)+' / '+num(r['example']['baseline_expansions'],0) if r['example'] else '—'] for r in a['completion_pairs']]))
    add('Попарное покрытие рассчитано по всем 90 car16 replay-случаям. «Выигрыш» означает завершённый кандидатом эпизод при остановке контроля; «потеря» — обратное. Для примера по возможности выбран запрос с конечным эталонным путём. Контроль остановился на миллионе раскрытий, кандидат дал проверенный ответ и завершил весь эпизод. Его частичное время не сравнивается с полным временем кандидата. Параметры с общими корнями остаются зависимыми.')
    add(figure('performance_profiles','Профили восьми фокусных методов относительно лучшего завершённого времени среди всех 14 точных. Незавершённая задача имеет бесконечное отношение и не исключается.'))
    add('## Проверки, выводы и ограничения')
    audits=[r for r in verification['model_audits'] if r['binary']=='test_models']
    add(f"Независимый Python Dijkstra работает по исходным физическим примитивам, без mesh-адаптера, кеша и эвристики: {verification['dynamic_snapshots']} динамических снимков, все 16 направлений car16, {verification['normal_query_checks']} проверок ответов обычного бинарника. Дополнительно проверены {sum(r['projection_checks'] for r in audits)} проекций примитивов, {sum(r['heuristic_checks'] for r in audits)} условий согласованности и {sum(r['support_close_open_checks'] for r in audits)} циклов закрытия и открытия опорных клеток. Те же проверки прошли ASan/UBSan; инструментирование памяти сохраняет решения и работу. Проверены перемещение старта, внутренние клетки макродуги и открытие ранее недостижимого компонента. Проверены закрытие и повторное открытие начальной и целевой клеток.")
    add(r'''Перенос завершён и проверяем, но сами структурные идеи не превращаются автоматически в универсальное преимущество над A\*, MPGAA\* или MD-A\*. C-Mesh сокращает число меток, Suffix-Mesh меняет направление разделения трасс, Boundary-Mesh меняет гранулярность кеша коллизий. Их полезность определяется геометрией, локальностью изменений и стоимостью уведомлений. В результатах выше показаны и сильные режимы, и случаи проигрыша.

Positive prefix — контроль общей реализации, а не доказательство, что всё отличие от прежнего D\* Lite mesh вызвано топологией. Для car16 сравнение Boundary-Mesh с ним включает переход к решётке и пакетный кеш; чтобы строго приписать весь выигрыш маске, нужна дополнительная решётчатая версия с точечным кешем в новом ядре. Прежний D\* Lite lattice служит практическим сильным контролем, но ядра отличаются. В одношаговой grid8 Positive prefix уже тождествен решётке с точечным кешем в том же ядре: сравнение Boundary/Positive prefix здесь выделяет гранулярность кеша и пакетную проверку. Совпадение путей и раскрытий четырёх новых адаптеров на grid8 проверяется отдельно; различаться могут чтения клеток и ресурсы.

Сжатие цепочек, разворот автомата и кеширование допустимости сами по себе известные приёмы. Исследовательская идея здесь — их применение и сравнение в конкретной incremental MeshA\*-модели; мировой приоритет этих комбинаций не установлен. Сильная сторона работы — исполняемый и проверяемый артефакт, а не подтверждённая новая общая теорема или лидерство над всеми опубликованными реализациями.

Для выделения пользы именно префиксного обхода Boundary-Mesh нужен ещё контроль с той же маской и тем же ядром, который вычисляет её независимыми проходами полных traces. Он отделил бы совместную проверку mesh от упаковки кеша и гранулярности инвалидации. Текущее преимущество памяти маски нельзя целиком приписывать mesh-структуре.

Репрезентативность ограничена прежними корнями и окнами карт. Официальные Moving AI карты уже применялись в исследованиях поиска, но новые числа не воспроизводят опубликованные реализации авторов. Bootstrap по четырём–шести картам, сохранённый в JSON для основных сравнений, описательный. Мелкие различия времени сопоставляются с разбросом повторов; все 15 методов выполнялись последовательно в перемешанном порядке, отдельного второго компьютера и аппаратных счётчиков нет. Нельзя переносить победу в отдельных строках на все инкрементальные mesh-задачи.''')
    add('## Воспроизведение дополнения')
    add(f"Машина: `{a['cpu']}`; платформа: `{a['platform']}`. Исходники, команды, версии компилятора, флаги, хеши бинарников, входов и каждой CSV сохранены в `cpp/mesh_variants/frozen/manifest.json` и `results/full/experiment.json`. Старые результаты `cpp/experiments/results/expanded` сохранены.")
    add('''```bash
make -C cpp/mesh_variants -j2 all
make -C cpp/mesh_variants sanitize
python cpp/mesh_variants/test_variants.py
python cpp/mesh_variants/run_all.py --output cpp/mesh_variants/results/reproduction
python cpp/mesh_variants/analyze.py --directory cpp/mesh_variants/results/reproduction
python cpp/mesh_variants/report.py --directory cpp/mesh_variants/results/reproduction
python cpp/experiments/report.py --mesh-directory cpp/mesh_variants/results/reproduction
```

Сохранённые результаты можно заново проанализировать и собрать командами `analyze.py` и `report.py` без параметра `--directory`. Основной объединённый отчёт из сохранённых данных собирается так:

```bash
python cpp/experiments/report.py
```

Словарь CSV и определения метрик: `cpp/experiments/README.md`.

Новая семантика уведомлений и стоимость общей модели: `cpp/mesh_variants/README.md`.''')
    literature='\n## Литература\n\n'+r'''1. Agranovskiy, Yakovlev. *MeshA\*: Efficient Path Planning With Motion Primitives*. [arXiv:2412.10320](https://arxiv.org/abs/2412.10320).
2. S. Koenig, M. Likhachev. *D\* Lite*. AAAI 2002. [PDF](https://www.cs.cmu.edu/~motionplanning/papers/sbp_papers/integrated3/koenig_dstarlite_aaai02b.pdf).
3. C. Hernández, R. Asín, J. A. Baier. *Reusing Previously Found A\* Paths for Fast Goal-Directed Navigation in Dynamic Terrain*. AAAI 2015. [PDF](https://classpages.cselabs.umn.edu/Fall-2021/csci4511-001/misc/HernandezAB15.pdf).
4. N. Sturtevant. *Benchmarks for Grid-Based Pathfinding*. IEEE TCIAIG 4(2), 144–148, 2012. [Moving AI](https://www.movingai.com/benchmarks/grids.html).'''
    dest=ROOT/'docs/experiments';body='\n'.join(out);(dest/'mesh_variants_body.md').write_text(body)
    metadata='''---
title: "C-Mesh-D* Lite, Suffix-Mesh и Boundary-Mesh"
subtitle: "Совместные C++-эксперименты с 15 алгоритмами"
date: "19 ноября 2026"
lang: ru-RU
fontsize: 10pt
geometry: margin=18mm
mainfont: Noto Serif
monofont: Noto Sans Mono
colorlinks: true
toc: true
toc-depth: 2
---
'''
    markdown=metadata+'\n'+body+literature+'\n';(dest/'mesh_variants.md').write_text(markdown)
    if pdf:
        cache=Path(tempfile.gettempdir())/'ima_exp_fontcache';cache.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.md') as f:
            f.write(markdown.replace('.png){width=','.pdf){width='));f.flush()
            subprocess.run(['pandoc',f.name,'--resource-path='+str(dest),'--pdf-engine=xelatex','--include-in-header=layout.tex','-o','mesh_variants.pdf'],cwd=dest,check=True,env={**os.environ,'XDG_CACHE_HOME':str(cache)})
    provenance=dict(status='passed',analysis_sha256=digest(analysis_path),source_sha256=digest(Path(__file__)),body_sha256=digest(dest/'mesh_variants_body.md'),
                    figures_manifest_sha256=digest(directory/'analysis/figures.json'),
                    verification_sha256=digest(HERE/'results/verification.json'),
                    markdown_sha256=digest(dest/'mesh_variants.md'),pdf_sha256=digest(dest/'mesh_variants.pdf') if pdf else None)
    (directory/'analysis/report_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('Wrote mesh supplement to',dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--no-pdf',action='store_true');args=p.parse_args()
    build(args.directory,not args.no_pdf)
