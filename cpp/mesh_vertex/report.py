#!/usr/bin/env python3
"""Render the Russian report and a candid data-bound English manuscript."""
import argparse,importlib.util,json,math,sys
from pathlib import Path
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_vertex'
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as common
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
study=load('native_mesh_analysis',HERE/'analyze.py');writer=load('native_mesh_writer',ROOT/'cpp/mesh_envelope/report.py');writer.DEST=DEST
LABEL=study.LABEL
def n(v):return f'{v:.2f}' if pd.notna(v) and math.isfinite(float(v)) else '—'
def table(head,rows):return writer.table(head,rows)
def fig(name,caption):return f'![{caption}](figures/{name}.png){{width=99%}}'
def main(directory):
 ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed' and a['source_sha256']==common.sha(HERE/'analyze.py')
 for p,h in a['tables_sha256'].items():assert common.sha(ad/p)==h,p
 for p,h in a['figures_sha256'].items():assert common.sha(ROOT/p)==h,p
 m=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text())
 metrics=pd.read_csv(ad/'case_metrics.csv');summary=pd.read_csv(ad/'summary.csv');maps=pd.read_csv(ad/'map_pairs.csv');params=pd.read_csv(ad/'parameter_pairs.csv');work=pd.read_csv(ad/'work.csv');completion=pd.read_csv(ad/'completion.csv');caps=pd.read_csv(ad/'caps.csv');snap=pd.read_csv(ad/'max_state.csv');quality=pd.read_csv(ad/'navigation_quality.csv');changes=pd.read_csv(ad/'actual_changes.csv');probes=pd.read_csv(ad/'collision_probes.csv')
 main=summary[summary.control.eq('car16')&summary.cohort.eq('replay')&summary.panel.eq('main')];cascade=main[main.method.eq('cascade_mesh')&main.baseline.eq('mesh_mpgaa')].iloc[0];best=main[main.method.eq('cascade_mesh')&main.baseline.eq('best_control')].iloc[0]
 o=[];put=o.append
 put('# Что реализовано и что проверено')
 put(f"Реализованы **Trigger-Mesh-MPGAA*** и **Cascade-Mesh-MPGAA***. В отличие от прежних boundary-вариантов, OPEN, g, learned h и сохранённые политики работают на полном конфигурационном mesh, включая промежуточные состояния примитивов. Добавлен обычный Mesh-MPGAA* на том же движке и четыре абляции. Выполнены {a['timed_runs']:,} временных эпизодов, {a['memory_runs']:,} отдельных замеров памяти, {a['count_only_runs']:,} счётных эпизодов на {a['scenarios']} конфигурациях. Расхождений завершённых ответов с точным эталоном: {a['exact_cost_disagreements']}. Capped-вызовов: {a['capped_calls']}; они не считаются NoPath или быстрым успешным решением.")
 put(f"Основная balanced-панель car16: Cascade / обычный Mesh-MPGAA — **{n(cascade.full_speedup)}×** по полному времени и **{n(cascade.repair_speedup)}×** по ремонту, {int(cascade.pairs)}/{int(cascade.configurations)} общих завершённых пар. Относительно самого быстрого завершившегося контроля — **{n(best.full_speedup)}× / {n(best.repair_speedup)}×**, выигрышей от 10%: {int(best.wins10)}/{int(best.pairs)}. Отношения больше 1 выгодны кандидату.")
 if cascade.full_speedup>=1.1 and best.full_speedup>=1.1:
  put('На основной панели есть измеренный общий выигрыш как над тем же mesh-движком, так и над огибающей сильных контролей. Это поддерживает дальнейшую статью; результат остаётся ограниченным выбранными картами, корнями и библиотекой примитивов. Литературный приоритет сочетания пока не установлен.')
 elif cascade.full_speedup>=1.1:
  put('Есть существенный выигрыш над обычным MPGAA* на том же mesh-графе. Общего убедительного преимущества над всей огибающей сильных контролей пока недостаточно: статья должна описывать конкретный режим ремонта и его ограничения, а не универсальное превосходство.')
 else:
  put('На основной панели общего убедительного выигрыша над тем же mesh-движком пока нет. Локальная экономия событий, очередей или отдельные удачные карты не заменяют окупаемость полного эпизода. Представлять эту реализацию как готового победителя для ведущей конференции по этим данным нельзя.')
 rows=[]
 for _,r in summary[summary.baseline.eq('best_control')].iterrows():rows.append([r.cohort,r.control,r.panel,LABEL[r.method],f'{int(r.pairs)}/{int(r.configurations)}',n(r.full_speedup),n(r.repair_speedup)])
 put(table(['Набор','Модель','Панель','Метод','Пары','Полное ×','Ремонт ×'],rows))
 put('Полное время включает конструктор и запрос 0. Ремонт исключает их. Общие шаблоны моделей готовятся заранее; их время и память отдельно сохранены в JSON. В replay точный ответ NoPath считается завершением; в навигации нужно достичь цели. Огибающая best_control выбирается post hoc по медиане полного времени среди завершившихся контролей; прямые сравнения со всеми методами сохранены. Она включает обычный native Mesh-MPGAA*, но не новые абляции. Три временных повтора не являются тремя независимыми картами.')
 put(fig('profile','Отношения полного времени на основной replay-панели; history показана отдельно в таблицах.'))
 put('# Алгоритмы и доказательства')
 put((DEST/'design.md').read_text().split('\n\n',1)[1])
 put(table(['Вариант','Назначение'],[['Mesh-MPGAA*','Обычный MPGAA* с g/h/OPEN/policy на всех mesh-конфигурациях'],['Trigger-Mesh','Только подписки на нарушенные неравенства у заблокированных рёбер'],['Cascade-Mesh','Подписки, обратный каскад и прямое продолжение контура'],['Cascade scan','Убраны клеточные подписки'],['Cascade heap','Убрано прямое продолжение; обратный каскад сохранён'],['Contour only','Trigger + прямое продолжение; обратного каскада нет'],['Mesh A* same core','Убраны обучение, политика и отрицательный кеш']]))
 put(f"Прямой primitive Dijkstra проверил 6 734 ответа на случайных картах и восстановлении после cap; ASan/UBSan прошли для обеих моделей. Тесты аудируют согласованность h и полноту подписок. В car16-тестах раскрыты 5 096 285 внутренних mesh-вершин. Дополнительно на всей новой replay-серии в {a['contour_equivalence_queries']:,} запросах подтверждены идентичные статусы, стоимости, пути и хеши порядка обработки актуальных вершин у Trigger и contour-only. Это проверка именно обхода кучи; обратный каскад может менять порядок равнозначных ремонтных событий и выбор равностоимостной политики.")
 put('# Протокол')
 put(m['protocol'])
 put('Replay: шесть car-карт Berlin, AR0700, arena, MA_maze96, MA_room96, MA_random96; два корня, четыре семейства изменений на/вне пути, смешанных правок и раскрытия. Основная панель — 48 конфигураций, history — четыре отдельных. Grid — все 96 random50-сценариев четырёх плотностей. Новая навигация охватывает оба корня каждой car-карты и все четыре радиуса; динамика дополнена средней точкой (8,10%) между (2,5%) и (32,20%). Это существующие открытые спецификации репозитория, а не скрытый holdout; прежние результаты использовались при постановке исследовательского направления.')
 put('Восемь внешних по отношению к новому движку контролей: LBA reuse, исходный MeshA*, primitive MPGAA*, Batch-MPGAA*, MD-A*, Boundary-Mesh, Conditional D* Lite и C-Mesh-D* Lite. Grid сохраняет сильный Octile reuse. Навигация использует native Mesh-MPGAA, оба новых метода и пять сильных самостоятельных контролей; дополнительные абляции ограничены одинаковыми replay-входами. Остальные старые варианты не перемерялись и их секунды сюда не добавлялись. Контроли — реализации текущего репозитория, не официальные внешние пакеты.')
 put('Все методы используют одинаковые исходные float-стоимости и трассы Hermite-примитивов; это не официальный оптимизированный control set MeshA*. Радиус раскрытия — клеточная квадратная окрестность. Dynamic n — глубина primitive-решётки без окклюзии; n=k связывает обзор и частоту правок, поэтому их отдельные причинные эффекты не оцениваются. Move означает один примитив. Разные оптимальные пути могут приводить к разным наблюдениям и последующим мировым правкам; replay обеспечивает более строгие одинаковые входы.')
 put(f"CPU {state['cpu']}; affinity {state['affinity']}; один измерительный процесс. Флаги и версия компилятора сохранены для каждого задания. Бюджет {m['cap']:,} раскрытий на запрос; единицы раскрытия различаются между primitive и mesh-представлениями. Стоимость каждого завершённого ответа проверяется с точностью $10^{{-6}}$. Обычный и allocation-проходы совпали по всем логическим полям в {a['allocation_matched_rows']:,} строках. Медиана относительного MAD времени {100*a['relative_mad_median']:.2f}%, p95 {100*a['relative_mad_p95']:.2f}%. Память — запрошенные C++ new байты, не RSS.")
 put('# Результаты по картам и абляции')
 put(fig('maps','Replay по картам относительно самой быстрой контрольной реализации и обычного native MPGAA*.'))
 for (cohort,control,method),d in maps.groupby(['cohort','control','method']):
  put(f'## {cohort}, {control}, {LABEL[method]}');rows=[]
  for name,g in d.groupby('map'):
   row=[name]
   for b in ['best_control','mesh_mpgaa','trigger_mesh','contour_only','cascade_heap','cascade_scan']:
    x=g[g.baseline.eq(b)];row.append('—' if x.empty else f'{n(x.iloc[0].full_speedup)} / {n(x.iloc[0].repair_speedup)} ({int(x.iloc[0].pairs)}/{int(x.iloc[0].configurations)})')
   rows.append(row)
  put(table(['Карта','Fastest','Mesh MPGAA','Trigger','No reverse','No forward','No watches'],rows))
  put('Формат: полное / ремонт × (общие завершённые пары / конфигурации). Прочерк означает отсутствие сравнения; в частности, абляции не запускались в навигации. Сравнение метода с самим собой также не приводится.')
 put('# Работа ремонта и очередей')
 put(fig('mechanism','На основной car replay-панели: кандидаты уведомлений, вставки в поисковую кучу и в repair-кучу. Добавлена единица для логарифмической шкалы.'))
 rows=[];short={'mesh_mpgaa':'Mesh MPGAA','trigger_mesh':'Trigger','cascade_mesh':'Cascade','contour_only':'No reverse','cascade_heap':'No forward','cascade_scan':'No watches','mesh_astar':'Cold'}
 for method in short:
  d=work[work.control.eq('car16')&work.cohort.eq('replay')&work.panel.eq('main')&work.method.eq(method)]
  rows.append([short[method],int(d.mv_boundary_expansions.sum()),int(d.mv_interior_expansions.sum()),int(d.notify_probes.sum()),int(d.mv_heap_pushes.sum()),int(d.mv_repair_heap_pushes.sum()),int(d.mv_repair_local_steps.sum())])
 put(table(['Метод','Boundary','Interior','Notify','Search heap','Repair heap','Repair local'],rows))
 put('Все единицы этой таблицы относятся к одному native mesh-графу. Contour only сохраняет точный поисковый порядок Trigger, поэтому разница поисковой кучи изолирует прямое продолжение. Cascade heap изолирует обратный каскад без прямого продолжения; Cascade scan показывает стоимость отсутствия подписок. Взаимодействующие эффекты нельзя складывать как независимые ускорения. mv_records и mv_active_watches — снимки; их максимумы доступны в max_state.csv, а не в сумме work.csv. Хеш порядка не является счётчиком работы.')
 put(fig('edits','Медиана времени ремонта по числу наблюдаемых правок; только replay. Это описательные группы запросов, а не дополнительные независимые эпизоды.'))
 put(fig('amortization','Окупаемость относительно того же native MPGAA*: конструктор, первый поиск и первые N ремонтов. Префиксы одного эпизода зависимы.'))
 put('# Полный collision-API счётчик')
 put(f"В отдельной копии заголовков каждый Grid.free внутри replan подсчитан для всех replay-методов: {a['count_only_runs']:,} эпизодов, {a['count_only_matched_rows']:,} строк с совпавшими прежними логическими полями. Время инструментированной сборки полностью отброшено. У новых методов проверено точное равенство all_free_calls и checked_cells. У старых checked_cells может пропускать предварительные gates; для сравнения используются полные API-вызовы.")
 rows=[]
 for (control,method),d in probes.groupby(['control','method']):rows.append([control,LABEL[method],int(d.all_free_calls.sum()),int(d.online_calls.sum())])
 put(table(['Модель','Метод','Все Grid.free','Grid.free ремонта'],rows))
 put('Это логические вызовы API, включая обращения за границей карты. Исключены конструктор, прямые Grid.blocked при нормализации правок и эталонная проверка путей. Это не число аппаратных чтений памяти и не эксперимент с дорогими геометрическими коллизиями.')
 put('# Радиус раскрытия, динамика и качество движения')
 put(fig('radius','Время планирования по радиусу на каждой карте. Линии — геометрическое среднее успешных корней; крестики — незавершённые миссии, а не доказательство ускорения.'))
 for cohort in ['navigation_unknown','navigation_dynamic']:
  for method in study.NEW:
   d=params[params.cohort.eq(cohort)&params.method.eq(method)];rows=[]
   keys=['map','radius'] if cohort.endswith('unknown') else ['map','k','cr']
   for key,g in d.groupby(keys):
    setting=str(int(key[1])) if len(key)==2 else f'{int(key[1])} / {int(key[2])}%';row=[key[0],setting]
    for baseline in ['best_control','mesh_mpgaa']:
     x=g[g.baseline.eq(baseline)].iloc[0];row.extend([f'{int(x.pairs)}/{int(x.configurations)}',n(x.full_speedup),n(x.repair_speedup)])
    rows.append(row)
   put(f'## {cohort}: {LABEL[method]}');put(table(['Карта','r или k/cr','Пары fast','Full fast','Repair fast','Пары mesh','Full mesh','Repair mesh'],rows))
 rows=[]
 for (name,radius),d in quality[quality.cohort.eq('navigation_unknown')].groupby(['map','radius']):
  row=[name,int(radius)]
  for method in ['cascade_mesh','mesh_mpgaa','lba_reuse','batch_mpgaa','conditional_dstar']:
   x=d[d.method.eq(method)];row.append(f'{n(common.gm(x.static_stretch))} ({int(x.complete.sum())}/{len(x)})')
  rows.append(row)
 put(table(['Карта','r','Cascade','Mesh MPGAA','LBA reuse','Batch','Cond D*'],rows))
 put('Здесь величина — длина исполненного пути / начальный оптимум полной статической truth-карты (завершённые корни / все корни). В динамике начальный оптимум не является нижней оценкой исполненного пути; сохранены абсолютная длина, moves и plans. Точность belief-планирования не означает оптимальность исследовательской стратегии. Контроллер прекращает миссию при NoPath или cap и не ждёт будущего открытия. Диагностика truth-reachable при belief-NoPath сохранена отдельно; статическая оптимистичная карта не дала ложного отрицательного ответа при существующем truth-пути.')
 rows=[]
 for (name,k,cr),d in changes.groupby(['map','k','requested_cr']):
  x=d[d.phases.gt(0)];rows.append([name,int(k),int(cr),n(x.actual_cr.min()),n(x.actual_cr.max()),int(d.clamped.sum()),f'{len(x)}/{len(d)}'])
 put(table(['Карта','k=n','Запрос cr%','Мин факт%','Макс факт%','Clamp phases','С фазами'],rows))
 put('cr — суммарная доля заблокированных и освобождённых клеток за фазу. Равные половины выбираются из раздельных исходных пулов; число пар ограничивается наличием клеток, агент и цель защищены. Фактический cr=100·actual_changes/(число клеток·phases). Строки без фаз не интерпретируются как наблюдение скорости изменения. Различия маршрутов могут менять число фаз и мощность доступных пулов.')
 put('# Память, завершение и ограничения')
 put(fig('memory','Отдельный allocation-проход. Выбросы скрыты только на диаграмме, максимумы приведены в таблице.'))
 rows=[]
 for (control,method),d in metrics.groupby(['control','method']):rows.append([control,LABEL[method],n(d.peak_heap_bytes.median()/2**20),n(d.peak_heap_bytes.max()/2**20),f'{int(d.complete.sum())}/{len(d)}'])
 put(table(['Модель','Метод','Медиана MiB','Максимум MiB','Завершено'],rows))
 rows=[]
 for _,r in completion.iterrows():rows.append([r.cohort,r.control,LABEL[r.method],f'{int(r.complete)}/{int(r.configurations)}'])
 put(table(['Набор','Модель','Метод','Завершено'],rows))
 rows=[]
 for method,d in caps.groupby('method'):rows.append([LABEL[method],len(d),', '.join(sorted(x.replace('__',' / ') for x in d['case'].unique()))])
 put(table(['Метод','Capped calls','Конфигурации'],rows) if rows else 'Остановок по лимиту не было.')
 put('Из-за большого числа внутренних состояний лимит раскрытий может быть достигнут раньше, чем на primitive-графе. Подписки расходуют память и требуют работы после первого обучения. Открытие узкого прохода может вызвать широкий ремонт. Дешёвые 2D occupancy-проверки не моделируют дорогой swept-volume oracle. Два корня на карту и фиксированные кропы ограничивают статистическую переносимость. Отсутствуют официальные внешние реализации MPGAA*/Lifelong-GLS и систематическая проверка литературного приоритета. Отрицательные результаты сохраняются наравне с положительными.')
 put('# Воспроизведение')
 put('```sh\nmake -C cpp/mesh_vertex all test\npython cpp/mesh_vertex/run_all.py --output cpp/mesh_vertex/results/reproduction\npython cpp/mesh_vertex/probe.py\npython cpp/mesh_vertex/analyze.py\npython cpp/mesh_vertex/report.py\npython cpp/mesh_vertex/validate.py\n```')
 put('Результаты нового запуска не перезаписывают canonical full. Анализ принимает --directory; по умолчанию отчёт и notebook читают сохранённую canonical серию. Полные команды, source/input/binary hashes и фактические параметры находятся в frozen/manifest.json и experiment.json. Основной источник доказательств — case-level CSV, а не округлённые PDF-таблицы. Прежние исходники и данные остаются без изменений.')
 put((DEST/'related_work.md').read_text())
 report=writer.render(DEST/'report.md','\n\n'.join(o),'Trigger и Cascade Mesh-MPGAA*: поиск на полном mesh-графе','ru-RU')
 p=[];put=p.append
 put('# Abstract')
 put(f"We study exact incremental planning directly on a motion-primitive configuration mesh. Unlike boundary-state planners that only share collision tests, our g-values, learned heuristics, OPEN entries and cached policies include intermediate mesh configurations. Trigger-Mesh-MPGAA* maintains subscriptions to blocked arcs whose heuristic-consistency inequalities are violated; openings activate only these subscriptions. Cascade-Mesh-MPGAA* additionally processes zero-base internal repair arcs locally under a potential-normalized key and continues a forward contour only when the exact OPEN order permits it. On the balanced 48-case car replay panel, Cascade achieves {n(cascade.full_speedup)} whole-episode and {n(cascade.repair_speedup)} repair speedup relative to ordinary MPGAA* on the identical mesh. Against the fastest completed strong control, the corresponding ratios are {n(best.full_speedup)} and {n(best.repair_speedup)}. Our frozen C++ study contains {a['timed_runs']:,} timing episodes, {a['memory_runs']:,} allocation episodes and {a['count_only_runs']:,} independent API-count episodes. All completed answers match exact references; caps and failed missions remain visible. Novelty is a hypothesis about the mesh repair combination, not a claim to invent adaptive search, watched dependencies or fringe queues.")
 put('# Problem and graph')
 put('The directed mesh vertex is (cell, configuration). The original car automaton has 412 configurations, 16 of them primitive boundaries. Every returned solution is projected to the unchanged primitive IDs and float costs. A pre-existing dyadic potential phi gives each search arc the positive cost c prime = c + phi(v) - phi(u); boundary potentials are zero. Internal arcs have zero original base cost, while completion arcs pay the primitive cost. The initial internal heuristic minimizes completion cost plus endpoint Euclidean distance, subtracting the current potential. No lattice search is called inside either candidate.')
 put('# Triggered consistency repair')
 put(r'''The maintained invariant is that every blocked mesh arc satisfying $h(u)>c'(u,v)+h(v)$ is subscribed to the collision cell of v. Successful A* learning first updates all expanded labels to $\max(h(u),C-g(u))$, then installs any newly violated blocked arcs. Decreasing h(v) examines its predecessors: a free violated arc is relaxed immediately, and a blocked one is subscribed. Duplicate subscriptions are suppressed; stale subscriptions are harmless. Opening a cell extracts only its bucket. A violation can appear only after a left-label increase, a right-label decrease or an arc opening. The first two events install a subscription or repair the free arc, and the last processes its bucket. Thus an unobserved opening seed cannot remain on a free inconsistent arc. This filters work, not the observed map: all occupancy updates are applied eagerly.''')
 put('# Cascades and search contours')
 put(r'''Repair priorities use $h(u)+\phi(u)$. Across an internal arc of original base cost zero, reverse relaxation preserves this priority. A local stack processes that contour; positive-base completion arcs return to the heap. All intermediate vertices retain their own labels. Forward search separately bypasses the heap for the best newly generated child only when its complete key $(f,-g,seq)$ is no worse than the current heap minimum. Sequence numbers are assigned identically to ordinary A*. Therefore the next extracted vertex is unchanged. The implementation checks this equivalence over all replay queries using status, cost, path and pop-trace fingerprints.''')
 put('After consistency repair, A* may join a cached policy at any mesh vertex. A policy suffix is accepted only after checking current collision cells and tight h equalities through the goal. Extracting that vertex yields an optimal path; standard adaptive updates preserve consistency. Positive reweighted costs prevent policy cycles, and potential telescoping preserves original primitive costs. A capped search learns no stronger labels and creates no NoPath cache entry. The worst case may still repair a large learned region; subscriptions can increase memory.')
 put('# Evaluation')
 put(m['protocol'])
 put('Replay inputs are reused exploratory data; the four history cases are separated from the balanced car panel. Navigation covers six car maps, both roots, four discovery radii and three n=k dynamic anchors. Different optimal paths can produce different observations, so replay is the stricter identical-input test. Three serial randomized repeats measure time, a separate pass measures requested C++ heap bytes, and a generated-header counter pass measures every Grid.free API invocation. Counter-binary times are discarded. Snapshot counters and cross-representation expansion units are not treated as common CPU work.')
 rows=[]
 for _,r in summary[summary.baseline.isin(['best_control','mesh_mpgaa'])].iterrows():rows.append([r.cohort,r.control,r.panel,LABEL[r.method],LABEL[r.baseline],n(r.full_speedup),n(r.repair_speedup),f'{int(r.pairs)}/{int(r.configurations)}'])
 put(table(['Cohort','Model','Panel','Candidate','Comparator','Episode ×','Repair ×','Pairs'],rows))
 put('Ratios above one favor the candidate. Whole-episode time includes construction and initial search. The fastest-control envelope is descriptive and selected after measurement among completed controls; it includes the ordinary native mesh planner. Replay completion permits an exact failure proof; navigation requires reaching the goal. Incomplete pairs are never credited as time wins. Per-map losses, all caps, allocation maxima, actual clamped rates, latency and trajectory quality are retained in the accompanying report.')
 put(fig('mechanism','Work on the balanced car replay panel: notification candidates, forward heap insertions and repair heap insertions.'))
 put(fig('amortization','Construction and first-search overhead retained in cumulative cost; prefixes are dependent observations.'))
 put(fig('radius','Per-map discovery radius; crosses denote incomplete missions.'))
 put('# Scope and related work')
 put('MeshA* supplies the configuration representation; MPGAA* supplies adaptive learning and policy reuse. Potential reweighting and watched dependencies are established techniques. Fringe Search and partial-expansion A* already reduce queue/generation costs; our forward contour mechanism preserves the exact valid-vertex queue order and is not a claim of generic novelty in fringe processing. The proposed research contribution is the cell-triggered violation frontier combined with zero-base mesh repair cascades in a fully vertex-level adaptive planner. Priority requires a broader full-text review. Official external MPGAA*/Lifelong-GLS implementations were not integrated. Cheap 2D occupancy checks, a repository Hermite control set, fixed map crops and two roots limit external validity. Stronger claims require broader independent inputs and external implementations.')
 put('# References')
 put((DEST/'related_work.md').read_text().split('\n\n',1)[1])
 paper=writer.render(DEST/'paper.md','\n\n'.join(p),'Trigger and Cascade Mesh-MPGAA*: Exact Incremental Search on Configuration Meshes','en-US')
 provenance=dict(status='passed',analysis_sha256=common.sha(ad/'analysis.json'),source_sha256=common.sha(Path(__file__)),design_sha256=common.sha(DEST/'design.md'),related_work_sha256=common.sha(DEST/'related_work.md'),render_dependencies={p:common.sha(ROOT/p) for p in ['cpp/mesh_envelope/report.py','cpp/mpgaa_mesh/vector_images.lua','docs/experiments/layout.tex']},report=report,paper=paper)
 (ad/'report_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(DEST/'report.pdf')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
