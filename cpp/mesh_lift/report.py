#!/usr/bin/env python3
"""Data-bound report and manuscript for consistent adaptive terminal pruning."""
import argparse,importlib.util,json,math,sys
from pathlib import Path
import pandas as pd
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_lift'
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as common
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
study=load('lift_study_analysis',HERE/'analyze.py');writer=load('lift_study_writer',ROOT/'cpp/mesh_envelope/report.py');writer.DEST=DEST
LABEL=study.LABEL
LABEL.update({'mesh_mpgaa':'Mesh-MPGAA*','best_mesh':'Fastest mesh control'})
def n(v):return f'{v:.2f}' if pd.notna(v) and math.isfinite(float(v)) else '—'
def table(head,rows):return writer.table(head,[[str(value).replace('_',' ') for value in row] for row in rows])
def fig(name,caption):return f'![{caption}](figures/{name}.png){{width=99%}}'
def gm0(values):
 x=np.asarray(values,dtype=float);x=x[np.isfinite(x)&(x>=0)]
 return 0.0 if np.any(x==0) else common.gm(x)
def main(directory):
 ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed' and a['source_sha256']==common.sha(HERE/'analyze.py')
 for p,h in a['tables_sha256'].items():assert common.sha(ad/p)==h,p
 for p,h in a['figures_sha256'].items():assert common.sha(ROOT/p)==h,p
 manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text())
 data={x:pd.read_csv(ad/(x+'.csv')) for x in ['summary','paired_cases','map_pairs','family_pairs','parameter_pairs','case_metrics','completion','work','max_state','navigation_quality','actual_changes','collision_pairs','latency','edits_latency','caps','initial_summary','cap_summary']}
 summary=data['summary'];pairs=data['paired_cases'];metrics=data['case_metrics'];work=data['work'];quality=data['navigation_quality'];changes=data['actual_changes']
 main=summary[summary.cohort.eq('replay')&summary.control.eq('car16')&summary.panel.eq('main')]
 primary=main[main.baseline.eq('best_control')].sort_values(['pairs','full_speedup'],ascending=False).iloc[0];candidate=primary.method
 def result(method,baseline):return main[main.method.eq(method)&main.baseline.eq(baseline)].iloc[0]
 prev=result(candidate,'cascade_mesh');mesh=result(candidate,'best_mesh');cold=result(candidate,'cascade_cold');meshreuse=result(candidate,'mesha_reuse');batch=result(candidate,'batch_mpgaa')
 completed=metrics[metrics.cohort.eq('replay')&metrics.control.eq('car16')&metrics.panel.eq('main')&metrics.method.eq(candidate)].complete.sum()
 strong=primary.full_speedup>=1.1 and primary.pairs==primary.configurations
 verdict=('Есть общий измеренный выигрыш от 10% над огибающей контролей при завершении всех основных конфигураций. Это поддерживает статью о данном режиме, но не универсальное превосходство.' if strong else 'По этим данным общего убедительного превосходства над всей огибающей контролей нет. Статья должна опираться на доказательство совместимости и конкретные выигрышные режимы; представлять метод универсальным победителем нельзя.')
 o=[];put=o.append
 put('# Результат исследования')
 put(f"Реализованы **Lift-Mesh-MPGAA*** и **Cascade-Lift-Mesh-MPGAA***. Поиск, обучение и политики работают на всех вершинах исходного mesh, включая внутренние состояния примитивов. Основная новая идея: совместить терминальное отсечение MeshA* с MPGAA* через локальное восстановление согласованности h в пропущенном mesh-DAG. Оператор pathmax известен; предложена его конкретная роль и локальность в этой комбинации.")
 put(f"Новая совместная серия: {a['scenarios']} конфигурации, {a['timed_runs']:,} временных эпизодов, {a['memory_runs']:,} отдельных эпизодов памяти и {a['count_only_runs']:,} счётных эпизодов. Завершённые стоимости расходятся с точным эталоном в {a['exact_cost_disagreements']} случаях. Capped-вызовов: {a['capped_calls']}. {verdict}")
 put(f"Из двух кандидатов по завершению, затем полному времени на основной панели выбран **{LABEL[candidate]}** (этот выбор сделан после измерений, результаты обоих сохранены). Он завершает {int(completed)}/48 основных car16-конфигураций. На общих завершённых парах: к предыдущему Cascade-Mesh **{n(prev.full_speedup)}× full / {n(prev.repair_speedup)}× repair** ({int(prev.pairs)}/48), к быстрейшему mesh-контролю **{n(mesh.full_speedup)}× / {n(mesh.repair_speedup)}×** ({int(mesh.pairs)}/48), ко всем сильным контролям **{n(primary.full_speedup)}× / {n(primary.repair_speedup)}×** ({int(primary.pairs)}/48). Значение выше 1 выгодно кандидату. Условные отношения не заменяют долю завершения.")
 put(f"Прямые mesh-сравнения: {LABEL[candidate]} / MeshA* reuse — **{n(meshreuse.full_speedup)}× full / {n(meshreuse.repair_speedup)}× repair**, {int(meshreuse.pairs)}/48 общих пар; к тому же cold-движку с contour — **{n(cold.full_speedup)}× / {n(cold.repair_speedup)}×**, {int(cold.pairs)}/48. Это показывает пользу полного адаптивного повторного использования в данной реализации. К Batch-MPGAA* отношение составляет **{n(batch.full_speedup)}× / {n(batch.repair_speedup)}×**, {int(batch.pairs)}/48; сильный primitive-контроль нельзя исключать из вывода.")
 put('Предыдущая серия Trigger/Cascade сохранена отдельно в docs/mesh_vertex. В ней Cascade ускорял ремонт относительно обычного mesh-MPGAA* в 1,26 раза, но полное время составляло лишь 0,93 от скорости контроля и 12 из 48 основных car-конфигураций достигали лимита. Именно ограничение первого поиска мотивировало второй этап; секунды двух этапов не объединяются.')
 put('## Где есть преимущество, а где его нет')
 put('Следующий разбор описательно выбран после измерений; все карты, промежуточные отношения и неполные пары приведены ниже, без отбора только победителей.')
 for method in study.NEW:
  for baseline in ['best_control','best_mesh']:
   d=pairs[pairs.cohort.eq('replay')&pairs.control.eq('car16')&pairs.panel.eq('main')&pairs.method.eq(method)&pairs.baseline.eq(baseline)];wins=[];repairwins=[];losses=[]
   for name,g in d.groupby('map'):
    full=common.gm(g.full_speedup);repair=common.gm(g.repair_speedup);count=int(g.complete.sum());entry=f'{name}: full {n(full)} / repair {n(repair)} ×, {count}/{len(g)} пар'
    if full>=1.1:wins.append(entry)
    if repair>=1.1:repairwins.append(entry)
    if full<=.9:losses.append(entry)
   put(f'{LABEL[method]} относительно {LABEL[baseline]}. Полный выигрыш от 10%: '+('; '.join(wins) or 'нет')+'. Выигрыш ремонта от 10%: '+('; '.join(repairwins) or 'нет')+'. Полные потери от 10%: '+('; '.join(losses) or 'нет')+'.')
 put(fig('completion','Доли завершения car16: replay требует точного ответа, навигация — достижения цели.'))
 put('# Алгоритм, инварианты и доказательство')
 put((DEST/'design.md').read_text().split('\n\n',1)[1])
 put('```text\nReplan(start, blocks, openings):\n  apply changes; repair lowered h through newly free arcs\n  A* on (cell, mesh configuration):\n    accept a validated tight policy to goal, if available\n    if every free terminal of an internal node is CLOSED:\n      mark this node CLOSED; skip its outgoing expansion\n    else expand its free mesh arcs\n  on successful solution of cost C:\n    for u in CLOSED: h[u] = max(h[u], C - g[u])\n    locally lift free descendants to h[u] - cost(u,v)\n    record lifted labels as learned; install policy\n```')
 put(table(['Метод','Назначение'],[['Lift-Mesh','Терминальное отсечение + локальный подъём; обычный opening scan'],['Cascade-Lift','Lift + подписки на нарушенные заблокированные неравенства и каскады'],['Lift cold','То же отсечение без обучения, политики и отрицательного кеша'],['Cascade cold','Cold + точное продолжение контура без операций OPEN'],['No-prune','Cascade-Lift без терминального отсечения; контроль на том же новом движке'],['Cascade-Mesh','Предыдущий полный mesh-MPGAA без терминального отсечения'],['MeshA* reuse','Исходный MeshA* + стандартный оптимальный суффикс; сильный контроль без заявления новизны']]))
 put(f"Тесты: **4 810** сравнений с прямым primitive Dijkstra, 12 seed-карт на модель и по 40 последовательных запросов, включая блокированные концы, дубликаты правок, движущийся старт и восстановление после cap. ASan/UBSan прошли для grid8 и car16. Аудируются все свободные неравенства h и полнота подписок. В car16-тестах 676 834 терминальных отсечения и 22 422 локальных записи h. Контрольная мутация с отключённым подъёмом воспроизводит несогласованность на seed=0 после 93 отсечений; исходный код не содержит публичного небезопасного режима. В измеренных вызовах счётчики подтверждают {a['terminal_prunes']:,} отсечений и {a['lift_writes']:,} подъёмов (один временной повтор).")
 put(fig('lift_example','Перевзвешенная схема контрпримера: u и w внутренние; подписи показывают h до обучения и после Lift.'))
 put('Дополнительный детерминированный тест настоящего C++-движка проверяет уже оптимальность после освобождений: primitive Dijkstra, Lift и Cascade-Lift дают стоимость 4; копии без closure либо без learned-пометки поднятых узлов возвращают допустимый, но подоптимальный путь 5. Это отдельный формальный восьмиконфигурационный fixture с повторными клетками, не car16-бенчмарк и не временной результат. Его исходник, хеши и результат сохранены в repair_counterexample.py и validation/repair_counterexample.json.')
 put('# Протокол и сравнимость')
 put(manifest['protocol'])
 put('Replay: шесть car16-карт Berlin, AR0700, arena, MA_maze96, MA_room96, MA_random96, по два старта/цели и четыре семейства: блокировки на пути, вне пути, mixed edits, unknown discovery. Старт и правки в replay задаёт один контрольный агент; «на пути/вне пути» относится к его трассе, а другой метод может выбрать равностоимостный маршрут. Попадание в контрольную трассу не обязательно повышает оптимальную стоимость. Это 48 основных конфигураций плюс четыре history отдельно. Grid8: 96 random50-конфигураций четырёх плотностей, отрицательный контроль пользы длинного mesh. Навигация: все шесть car-карт, два корня, радиусы раскрытия 8,16,32,64 и три динамические точки (k,cr)=(2,5%),(8,10%),(32,20%); n=k. Это повтор выбранных существующих открытых спецификаций, без новых независимых карт и без holdout.')
 put('При dynamic cr/2 процентов клеток блокируются и столько же исходно заблокированных освобождаются. Число правок ограничивается доступными клетками; фактический cr выводится ниже. Один move — примитив. Static radius — квадратная клеточная окрестность; dynamic n — глубина primitive-решётки без окклюзии. Связь n=k не позволяет разделить эффект обзора и частоты; в выбранных anchors cr тоже меняется вместе с k, поэтому сравниваются совместные режимы, а не отдельный причинный эффект cr. Разные равностоимостные траектории меняют наблюдения и последующие динамические миры: replay обеспечивает более строгое сравнение одинаковых входов.')
 put('Во втором этапе заново измерены пять новых вариантов, предыдущий native Cascade, LBA reuse, MeshA*, MeshA* reuse, primitive MPGAA*, Batch-MPGAA*, MD-A*, Boundary-Mesh, Conditional D* Lite, C-Mesh-D* Lite и grid Octile reuse. Навигация использует 11 методов из манифеста; отсутствующие контроли не подставляются из прежних замеров. Реализации контролей принадлежат этому репозиторию, не официальным внешним пакетам.')
 put('Car16: 284 неизменённых Hermite-примитива, 412 конфигураций, из них 16 граничных; отдельный старый boundary forest имеет 572 узла и не является графом нового поиска. Grid8: восемь одноклеточных переходов. Оригинальные float-стоимости, ID и клеточные трассы одинаковы. Уже существующий dyadic potential делает mesh-дуги положительными; на границах потенциал нулевой. Это не официальный оптимизированный control set MeshA*.')
 put(f"CPU: {state['cpu']}; affinity {state['affinity']}; один измерительный процесс. Три последовательных повтора со случайным порядком, отдельно один allocation pass. Полное время включает конструктор и первый поиск; repair исключает их. Общее построение шаблонов исключено одинаково для методов и сохранено в JSON. Cap: {manifest['cap']:,} раскрытий на запрос; prunes измеряются отдельно, лимит раскрытий не является CPU-бюджетом. Peak — запрошенные байты C++ new, не RSS. Медиана относительного MAD: {100*a['relative_mad_median']:.2f}%, p95: {100*a['relative_mad_p95']:.2f}%. Три повтора не являются независимыми задачами.")
 put('Времена агрегируются медианой внутри конфигурации и геометрическим средним парных отношений между конфигурациями. best_control и best_mesh выбираются post hoc по полному времени только завершившихся контролей; их repair-отношение относится к тому же выбранному методу. NoPath — успешный точный ответ replay, но прекращение навигационной миссии. Незавершённые пары исключаются из отношений и остаются в таблицах completion/caps.')
 put('Сравнение с MeshA* reuse относится к двум готовым реализациям: часть ускорения может быть связана с организацией C++-движка. Cold-контроли на том же движке одновременно убирают обучение, policy reuse и отрицательный кеш; они не изолируют одно только обучение h. No-prune сохраняет эти механизмы и отделяет эффект отсечения с closure. Формальный контрпример проверяет корректность ремонта, а не его скорость.')
 put('# Основная replay-панель и абляции')
 rows=[]
 for _,r in summary[summary.cohort.eq('replay')&summary.panel.eq('main')].iterrows():
  rows.append([r.control,LABEL[r.method],LABEL[r.baseline],f'{int(r.pairs)}/{int(r.configurations)}',n(r.full_speedup),n(r.initial_speedup),n(r.repair_speedup),n(r.memory_multiplier)])
 put(table(['Модель','Метод','Контроль','Пары','Full ×','Init ×','Repair ×','Heap new/base'],rows))
 put('## Первый поиск отдельно от последующих ремонтов')
 rows=[]
 ini=data['initial_summary'];ini=ini[ini.cohort.eq('replay')&ini.panel.eq('main')&ini.baseline.isin(['cascade_mesh','mesha_reuse','lift_cold','cascade_cold','lift_noprune'])]
 for _,r in ini.iterrows():rows.append([r.control,LABEL[r.method],LABEL[r.baseline],f'{int(r.pairs)}/{int(r.configurations)}',n(r.initial_speedup)])
 put(table(['Модель','Метод','Контроль','Завершённых первых пар','Init ×'],rows))
 put('Эта таблица требует завершения только первого поиска: эпизод с поздним cap здесь сохраняется. Init в общей таблице выше условен на завершении всего эпизода. В обоих случаях конструктор включён; точный первый NoPath считается завершённым ответом.')
 put(fig('profile','Распределение полного ускорения основной replay-панели; только общие завершённые пары.'))
 put(fig('maps','Основная car-панель по картам; отсутствие общей завершённой пары не является выигрышем.'))
 put(fig('mesh_comparisons','Прямое сравнение с MeshA* reuse по каждой карте, отдельно полный эпизод и ремонт. Все отношения условны на завершении; знаменатели пар даны в таблицах.'))
 put('## По каждой карте и семейству')
 rows=[]
 for key,d in pairs[pairs.baseline.isin(['best_control','best_mesh','cascade_mesh'])].groupby(['cohort','control','panel','map','method','baseline']):
  rows.append([*key[:4],LABEL[key[4]],LABEL[key[5]],f'{int(d.complete.sum())}/{len(d)}',n(common.gm(d.full_speedup)),n(common.gm(d.repair_speedup))])
 put(table(['Cohort','Модель','Панель','Карта','Метод','Контроль','Пары','Full ×','Repair ×'],rows))
 rows=[]
 for _,r in data['family_pairs'][data['family_pairs'].baseline.isin(['best_control','best_mesh'])].iterrows():rows.append([r.cohort,r.control,r.family,LABEL[r.method],LABEL[r.baseline],f'{int(r.pairs)}/{int(r.configurations)}',n(r.full_speedup),n(r.repair_speedup)])
 put(table(['Cohort','Модель','Семейство','Метод','Контроль','Пары','Full ×','Repair ×'],rows))
 put('# Работа, память и окупаемость')
 put(fig('mechanism','Логическая работа основной car-панели: внутренние раскрытия, вставки в OPEN и подъёмы h. Сырые суммы включают выполненные префиксы cap.'))
 rows=[]
 for (control,method),d in work[work.cohort.eq('replay')&work.panel.eq('main')&work.method.isin(study.NATIVE)].groupby(['control','method']):rows.append([control,LABEL[method],int(d.mv_boundary_expansions.sum()),int(d.mv_interior_expansions.sum()),int(d.lift_terminal_prunes.sum()),int(d.lift_terminal_tests.sum()),int(d.lift_writes.sum()),int(d.mv_heap_pushes.sum())])
 put(table(['Модель','Метод','Гран. exp','Внутр. exp','Prunes','Terminal tests','h writes','OPEN push'],rows))
 put('Prune — обработанная внутренняя вершина без генерации исходящих рёбер; она всё ещё требует извлечения, terminal tests и адаптивного обновления. Подъём и терминальные проверки могут свести экономию раскрытий к нулю. Нули lift-счётчиков у старых методов означают отсутствие этой инструментации. Max records и active watches — снимки состояния, а не складываемая работа.')
 put(fig('memory','Пиковые запрошенные байты, включая незавершённые эпизоды; парные множители даны в основной таблице.'))
 put(fig('amortization','Полное накопленное время относительно предыдущего Cascade-Mesh. У каждого префикса свой набор общих завершённых пар; префиксы одного эпизода зависимы.'))
 put(fig('edits','Repair latency по числу наблюдаемых правок, без capped-запросов; состав задач между корзинами различается.'))
 put(f"Полный Grid.free внутри replan подсчитан в отдельной копии заголовков для всех replay-методов: {a['count_only_runs']:,} эпизодов, {a['count_only_matched_rows']:,} совпавших логических строк. Время счётной сборки отброшено; у всех новых вариантов и старого native Cascade проверено точное равенство checked_cells и all_free_calls. Конструктор, прямые Grid.blocked при нормализации правок и эталон исключены. Это API-вызовы, не аппаратные чтения и не дорогие геометрические коллизии.")
 rows=[]
 cp=data['collision_pairs']
 for key,d in cp[cp.panel.eq('main')&cp.baseline.isin(['best_control','best_mesh','cascade_mesh','mesha_reuse'])].groupby(['control','method','baseline']):rows.append([key[0],LABEL[key[1]],LABEL[key[2]],f'{int(d.complete.sum())}/{len(d)}',n(gm0(d.full_api_ratio)),n(gm0(d.repair_api_ratio))])
 put(table(['Модель','Метод','Контроль','Пары','Все API ×','Repair API ×'],rows))
 put('Нулевое число вызовов у контроля учитывается как нулевое отношение, а не удаляется как неудобная пара; отсутствие самого ремонта отмечается NaN. Число раскрытий несопоставимо как одинаковая единица работы между mesh и primitive-графами.')
 put('# Навигация по каждой карте и параметрам')
 put(fig('radius','Раскрытие статической неизвестной карты: время по радиусу; линии по завершённым корням, кресты — незавершённые миссии.'))
 for cohort in ['navigation_unknown','navigation_dynamic']:
  rows=[];d=data['parameter_pairs'];d=d[d.cohort.eq(cohort)&d.baseline.isin(['best_control','best_mesh','cascade_mesh','mesha_reuse'])]
  for _,r in d.iterrows():rows.append([r['map'],str(int(r.radius)) if cohort.endswith('unknown') else f'{int(r.k)}/{int(r.cr)}',LABEL[r.method],LABEL[r.baseline],f'{int(r.pairs)}/{int(r.configurations)}',n(r.full_speedup),n(r.repair_speedup)])
  put('## '+cohort);put(table(['Карта','r или k/cr%','Метод','Контроль','Goal-пары','Full ×','Repair ×'],rows))
 rows=[]
 for (name,radius),d in quality[quality.cohort.eq('navigation_unknown')].groupby(['map','radius']):
  row=[name,int(radius)]
  for method in ['lift_mesh','cascade_lift','mesha_reuse','batch_mpgaa','conditional_dstar']:
   v=d[d.method.eq(method)];row.append(f'{n(common.gm(v.static_stretch))} ({int(v.complete.sum())}/{len(v)})')
  rows.append(row)
 put(table(['Карта','r','Lift stretch','Cascade-Lift','MeshA reuse','Batch','Cond D*'],rows))
 put('Stretch — исполненный путь / начальный оптимум полной статической truth-карты; только завершённые корни. В динамике начальный оптимум не является корректной нижней оценкой длины всего движения; абсолютные travel_cost, moves и plans сохранены в CSV. Оптимальность каждого belief-плана не означает оптимальность исследования карты.')
 rows=[]
 for key,d in changes.groupby(['map','k','requested_cr']):rows.append([key[0],int(key[1]),int(key[2]),n(d.actual_cr.min()),n(d.actual_cr.max()),int(d.clamped.sum()),int(d.phases.sum())])
 put(table(['Карта','k=n','cr requested%','cr actual min','cr actual max','Clamped phases','All phases'],rows))
 put('Фактический cr вычислен как суммарное число мировых правок / (клетки × фазы). Если фаз не было, значение не определено (NaN), а не равно нулю; наблюдаемые агентом blocks/opens могут быть меньше. Диапазон отражает разные методы/траектории; суммы фаз — не независимые карты.')
 put('# Завершение, точность и ограничения')
 rows=[]
 for _,r in data['completion'].iterrows():rows.append([r.cohort,r.control,LABEL[r.method],f'{int(r.complete)}/{int(r.configurations)}'])
 put(table(['Cohort','Модель','Метод','Завершено'],rows))
 rows=[]
 for _,r in data['cap_summary'].iterrows():rows.append([r.cohort,r.control,LABEL[r.method],r.phase,int(r.configurations),int(r.calls)])
 put(table(['Cohort','Модель','Метод','Фаза cap','Конфигурации','Вызовы (repeat 0)'],rows))
 put('Все cap-вызовы и их queries сохранены в caps.csv; static NoPath дополнительно сверяется с truth reachability. Большой лимит moves и остановка при первом NoPath — свойства контроллера, а не доказательство способности переждать временное закрытие прохода. На основных replay одинаковые входы; в навигации даже точные алгоритмы могут выбирать разные оптимальные пути.')
 put('Сильные стороны: поиск действительно на полном mesh; небольшой локальный механизм; проверяемый инвариант и воспроизводимая мутация; сравнение с cold, reuse и no-prune; учёт первого поиска, cap, памяти, столкновений и траекторий. Ограничения: выбранные ранее открытые карты, два корня и один control set; корреляция семейств; три временных повтора; дешёвые occupancy-проверки; одинаковый лимит expansions не равен CPU-бюджету; внешние официальные MPGAA*/Lifelong-GLS не интегрированы. Независимый holdout и более широкий обзор нужны перед сильной конференционной заявкой.')
 put((DEST/'related_work.md').read_text())
 put('# Воспроизведение')
 put('Сборка: make -C cpp/mesh_lift all. Тесты: make -C cpp/mesh_lift test. Новый запуск: python3 cpp/mesh_lift/run_all.py --output /tmp/lift-fresh. Последующие probe.py и analyze.py принимают --directory, probe.py также --output; для альтернативных данных путь count-only набора задаётся --probes у analyze.py. Канонические отчёт и notebook читают сохранённый full. Все source/input/binary hashes, команды и параметры сохранены; прежние исходники и результаты не изменены.')
 report=writer.render(DEST/'report.md','\n\n'.join(o),'Lift-Mesh-MPGAA*: согласованное обучение с терминальным отсечением','ru-RU')
 p=[];put=p.append
 put('# Abstract')
 put(f"We introduce Lift-Mesh-MPGAA* and Cascade-Lift, exact incremental planners whose search and learned state live on every configuration of the original motion-primitive mesh. Directly combining MeshA* terminal-closed pruning with MPGAA* learning can leave skipped descendants inconsistent. A local directed pathmax closure restores consistency without raising already settled terminal labels. Pathmax itself is known; our contribution hypothesis is this compatibility mechanism, its locality argument and exact incremental opening repair. On the reused balanced 48-case car replay panel, the post hoc selected candidate {LABEL[candidate]} completes {int(completed)}/48 configurations. Against MeshA* with suffix reuse it achieves {n(meshreuse.full_speedup)} episode / {n(meshreuse.repair_speedup)} repair speedup on {int(meshreuse.pairs)}/48 common completed cases; against the same cold contour engine the ratios are {n(cold.full_speedup)} / {n(cold.repair_speedup)} on {int(cold.pairs)}/48. It remains slower than Batch-MPGAA* on this panel: {n(batch.full_speedup)} / {n(batch.repair_speedup)} relative speedup, {int(batch.pairs)}/48 pairs. The frozen second-stage study contains {a['timed_runs']:,} timing, {a['memory_runs']:,} allocation and {a['count_only_runs']:,} count-only episodes, with zero completed reference-cost disagreements. The results support incremental mesh reuse but not universal superiority over strong primitive planners.")
 put('# Setting and motivation')
 put('A vertex is (cell, mesh configuration), including primitive interiors. The original car automaton has 412 configurations and 16 boundary roots; the unchanged 284 motion primitives retain their original IDs, float costs and collision traces. The pre-existing dyadic potential makes mesh arc costs positive and telescopes to zero at boundaries. Initial h at roots is Euclidean; internal h is the minimum primitive completion cost plus endpoint Euclidean distance minus the current potential. No primitive-level A* runs inside the candidates. Plain mesh-MPGAA and earlier Trigger/Cascade use this full representation, but can explore many prefixes whose terminal states have already been settled.')
 put('# Consistent adaptive terminal pruning')
 put(r'''An internal vertex u is terminal-closed when every free in-map boundary completion of its current primitive is CLOSED in the current search. Following MeshA*, such a vertex need not generate outgoing arcs: its valid terminal outcomes have already been settled no more expensively. We still mark u CLOSED. After finding an optimal solution of cost C, the usual adaptive batch sets $h(u)\leftarrow\max(h(u),C-g(u))$ for every CLOSED vertex. Applying this batch without visiting skipped children may violate $h(u)\le c'(u,v)+h(v)$. The generated no-lifting mutant demonstrates this failure on the first test fixture.''')
 put(r'''Lift propagates $h(v)\leftarrow h(u)-c'(u,v)$ only when this raises a free child's label, using a local stack. Every materialized lifted label is marked learned, including unexpanded vertices. Blocked violations create cell subscriptions in Cascade-Lift. The path policy is installed after closure. A cap installs neither stronger learned labels nor a false NoPath certificate.''')
 put(r'''**Locality lemma.** Let u be pruned and v a valid boundary completion at reweighted distance d. Since v was settled first under a consistent heuristic, $g(v)\le g(u)+d$. After the adaptive batch, $h_{new}(v)\ge C-g(v)\ge C-g(u)-d$. Therefore v already supports every new adaptive floor propagated from u. If the old h dominates the adaptive floor, its inequalities already held, and raising right labels cannot violate them. Expanded ordinary vertices have children CLOSED or OPEN with f at least C, as in adaptive A*. Extra propagation is confined to skipped internal regions and cannot raise a boundary root. The implementation asserts this boundary condition. The argument applies to the frozen prefix-configuration mesh with finite internal DAGs; arbitrary quotient meshes are outside its scope.''')
 put(r'''**Correctness.** Each raise is admissible because $h(u)-c'(u,v)\le d_t(v)$ follows from admissibility and the arc triangle bound. Closure restores every free consistency inequality; raising a right label cannot invalidate unchanged predecessors. Incremental openings repair lowered h through free predecessors, and any newly threatened blocked inequality is subscribed. Thus subsequent A* starts with admissible consistent h, terminal pruning remains sound, and a validated tight policy can be accepted at an internal vertex. Positive reweighted costs prevent policy cycles, and telescoping preserves original primitive cost. Worst-case repair can still cover a large learned region.''')
 put(fig('lift_example','A pruned prefix and its local consistency closure; labels show h before learning and after Lift.'))
 put('The implementation initially scans outgoing arcs of every CLOSED vertex; only the additional label raises are confined to skipped regions. If T is the number of inspected arcs over all stack visits, closure costs O(T). A vertex may be lifted repeatedly; the locality lemma is not a linear-time guarantee in the number of map edits. Persistent storage is proportional to materialized records and watches, in addition to the current search frontier.')
 put(r'''Opening repair also requires the learned-state invariant $h(u)>base(u) \Rightarrow learned(u)$. An unlearned label equals the initial consistent base and cannot become a violated predecessor when a child decreases but remains above its base. Repair may therefore skip unlearned predecessors. Every lifted label above base must be marked learned; the second mutant below violates this invariant even though its initial free-edge consistency closure was performed.''')
 put('A deterministic actual-engine fixture demonstrates the incremental consequence. Four boundary headings at one cell represent r,s,v,t; free primitives r-to-s, r-to-v, s-to-v and v-to-t cost 1,2,3,10. The s-to-v primitive has two internal configurations. Initially blocked shortcut primitives v-to-t and s-to-t cost 1 and 5 and have private collision cells. The first query from r costs 12 and prunes the internal prefix after v is CLOSED. Opening both shortcuts and moving the start to s gives optimum 4. The no-closure mutant returns the valid but suboptimal cost 5 because the low skipped label masks the backward repair wave. A second mutant that performs lifting but omits the learned mark also returns 5. Both full algorithms and independent primitive Dijkstra return 4. This is an eight-configuration formal prefix fixture with repeated cells, not an additional kinodynamic benchmark or timing sample.')
 put('# Variants and evaluation')
 put('Lift uses standard opening-seed scans. Cascade-Lift adds the previous cell-triggered violated-arc subscriptions, local reverse zero-base cascades and an exact-priority forward continuation. Controls include both cold pruning variants, the same engine without pruning, previous Cascade-Mesh, original MeshA* and MeshA* with standard suffix reuse, and eight repository incremental comparators. The suffix rule and pathmax are not claimed as new.')
 put(manifest['protocol'])
 put('The 232 public configurations contain 52 car replay episodes (48 balanced, four history), 96 grid replay episodes and 84 car navigation missions. Navigation uses six maps, two roots, radii 8/16/32/64 and dynamic (k,cr) anchors (2,5%), (8,10%), (32,20%), with n=k and clamped balanced edits. Reused inputs and second-stage design are disclosed; there is no independent holdout. The selected anchors also couple cr to k, so they compare joint regimes rather than isolate a causal change-rate effect. Three serial randomized timing repeats, one allocation pass and one separately compiled all-Grid.free replay pass are kept distinct. Full episode time includes construction and initial search. Replay starts and edits come from one frozen reference agent; on/off-path refers to that reference trajectory, not necessarily to each chosen planner trajectory. Common-completion filtering precedes every paired ratio. Expansions are representation-specific, and prunes, terminal tests and lift work are counted separately.')
 rows=[]
 for _,r in summary[summary.baseline.isin(['best_control','best_mesh','cascade_mesh','mesha_reuse','batch_mpgaa','conditional_dstar','cmesh_dstar'])&summary.panel.ne('history')].iterrows():rows.append([r.cohort,r.control,LABEL[r.method],LABEL[r.baseline],f'{int(r.pairs)}/{int(r.configurations)}',n(r.full_speedup),n(r.repair_speedup)])
 put(table(['Cohort','Model','Candidate','Control','Pairs','Episode ×','Repair ×'],rows))
 ini=data['initial_summary'];rows=[]
 for _,r in ini[ini.cohort.eq('replay')&ini.control.eq('car16')&ini.panel.eq('main')&ini.baseline.isin(['cascade_mesh','mesha_reuse','cascade_cold','lift_noprune'])].iterrows():rows.append([LABEL[r.method],LABEL[r.baseline],f'{int(r.pairs)}/{int(r.configurations)}',n(r.initial_speedup)])
 put(table(['Candidate','First-search control','Solved initial pairs','Initial ×'],rows))
 put('This table conditions only on completion of the initial search, including an exact NoPath answer, and retains episodes that later cap during repair. Initial ratios in the episode-level table instead condition on whole-episode completion.')
 put(fig('completion','Completion is reported separately from conditional speedups.'))
 put(fig('mechanism','Work on the balanced car panel, including executed prefixes of capped runs.'))
 put(fig('maps','Per-map episode speedup on the balanced panel.'))
 put(fig('mesh_comparisons','Direct comparison with MeshA* plus suffix reuse, by map and cost component.'))
 put('MeshA* reuse is an implementation-level comparator: kernel organization can account for part of the speedup. The same-engine cold controls jointly disable adaptive learning, policy reuse and negative caching, so they do not isolate heuristic learning alone. The no-pruning ablation retains those mechanisms. The formal counterexample establishes repair correctness rather than a runtime advantage.')
 put('# Evidence, limitations and related work')
 put(f"All five new modes passed 4,810 direct primitive-Dijkstra comparisons and ASan/UBSan on both models. The no-lift mutation triggers an inconsistency after 93 prunes; normal/allocation logical fields match in {a['allocation_matched_rows']:,} rows, and count-only fields match in {a['count_only_matched_rows']:,} rows. The full cohort has {a['capped_calls']} capped calls, never classified as proof of disconnection. Relative timing MAD has median {100*a['relative_mad_median']:.2f}% and p95 {100*a['relative_mad_p95']:.2f}%. Detailed per-map/radius/change-rate results, path lengths, observed edits, latency, memory and all failures accompany the Russian report.")
 put('MeshA* provides the graph and terminal pruning; MPGAA* provides learning and policy reuse. Directed pathmax and inconsistency propagation are established techniques (Felner et al., 2011). Our proposed contribution is a consistency closure bounded by settled mesh terminals, enabling this combination with exact opening repair. Fringe Search, partial expansion and lazy incremental planning are related; this limited review does not establish priority. Terminal tests, lifted records and watches may cost more time or memory than they save. Two roots, correlated reused scenarios, cheap occupancy checks, one repository Hermite control set and repository-specific controls limit external validity. A broader independent benchmark and official external implementations are needed before claiming conference-level empirical superiority.')
 put('# References');put((DEST/'references.md').read_text())
 paper=writer.render(DEST/'paper.md','\n\n'.join(p),'Lift-Mesh-MPGAA*: Consistent Adaptive Pruning on Motion-Primitive Meshes','en-US')
 provenance=dict(status='passed',analysis_sha256=common.sha(ad/'analysis.json'),source_sha256=common.sha(Path(__file__)),design_sha256=common.sha(DEST/'design.md'),related_work_sha256=common.sha(DEST/'related_work.md'),render_dependencies={p:common.sha(ROOT/p) for p in ['cpp/mesh_envelope/report.py','cpp/mpgaa_mesh/vector_images.lua','docs/experiments/layout.tex','docs/mesh_lift/references.md']},report=report,paper=paper)
 (ad/'report_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(DEST/'report.pdf')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
