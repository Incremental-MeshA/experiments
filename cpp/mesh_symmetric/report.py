#!/usr/bin/env python3
"""Data-bound SMD-A* report and a focused manuscript; all losses stay visible."""
import argparse,importlib.util,json,math,sys
from pathlib import Path
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_symmetric'
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as base
spec=importlib.util.spec_from_file_location('mesh_envelope_writer',ROOT/'cpp/mesh_envelope/report.py');writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer);writer.DEST=DEST
LABEL={**base.LABEL,'smd_batch':'SMD-A*','smd_plain':'SMD без gap','md_batch':'MD + Batch','lazy_blocks_batch':'Lazy blocks / eager opens','conditional_dstar':'Conditional D* Lite'}
def num(x):return f'{x:.2f}' if pd.notna(x) and math.isfinite(float(x)) else '—'
def figure(name,text):return f'![{text}](figures/{name}.png){{width=99%}}'
def table(head,rows):return writer.table(head,rows)
def main(directory):
 ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed' and a['source_sha256']==base.sha(HERE/'analyze.py')
 for p,h in a['tables_sha256'].items():assert base.sha(ad/p)==h
 for p,h in a['figures_sha256'].items():assert base.sha(ROOT/p)==h
 m=json.loads((HERE/'frozen/manifest.json').read_text());metrics=pd.read_csv(ad/'case_metrics.csv');pairs=pd.read_csv(ad/'paired_cases.csv');summary=pd.read_csv(ad/'summary.csv');maps=pd.read_csv(ad/'map_pairs.csv');families=pd.read_csv(ad/'family_pairs.csv');work=pd.read_csv(ad/'work.csv');completion=pd.read_csv(ad/'completion.csv');caps=pd.read_csv(ad/'caps.csv');quality=pd.read_csv(ad/'navigation_quality.csv');changes=pd.read_csv(ad/'actual_changes.csv')
 o=[];add=o.append
 add('# Результат второй итерации')
 add(f"Реализован **SMD-A*** — симметричное откладывание правок с mesh-сертификатом освобождений и проверкой разрыва между рабочим оптимумом и допустимым incumbent. Выполнены {a['timed_runs']:,} временных эпизодов и {a['memory_runs']:,} отдельных эпизодов памяти на {a['scenarios']} конфигурациях; {a['timed_calls']:,} вызовов. Расхождений завершённых ответов с точным эталоном: {a['exact_cost_disagreements']}; capped-вызовов: {a['capped_calls']}. Все прежние логические поля обычного и allocation-прохода совпали в {a['allocation_matched_rows']:,} строках.")
 add('Это вторая исследовательская итерация после отрицательного первого результата: Envelope-Mesh почти не отличался от lattice-варианта на обычных картах, Circuit-Mesh не дал общего преимущества. Новый протокол зафиксирован до замеров SMD, но повторные replay-входы относятся к разработке, а не к независимому подтверждению. Навигация на альтернативном корне не участвовала в первой серии. Карты и спецификации уже были в репозитории; скрытым бенчмарком они не являются. Секунды разных серий не смешиваются.')
 rows=[]
 for (cohort,control,panel),d in summary[summary.baseline.eq('best_control')].groupby(['cohort','control','panel']):
  r=d.iloc[0];rows.append([cohort,control,panel,f'{int(r.pairs)}/{int(r.configurations)}',num(r.full_speedup),num(r.repair_speedup),f'{int(r.wins10)}/{int(r.pairs)}'])
 add(table(['Набор','Модель','Панель','Пары','Полное ×','Ремонт ×','Выигрыш от 10%'],rows))
 add('Отношение больше 1 выгодно SMD. Полное время включает конструктор и запрос 0; ремонт исключает их. Replay считает точный NoPath завершением; в навигации нужно достичь цели. Самый быстрый контроль выбирается после измерения по медиане полного эпизода среди завершившихся. В replay эта огибающая включает и сильный eager-open lazy-block контроль. Разные строки могут иметь разные общие завершённые конфигурации; caps и все завершения приведены ниже.')
 add(figure('profile','Парные отношения SMD к сильным контролям; каждый comparator перемерен в той же новой серии.'))
 add('# Алгоритм и доказательство')
 add((DEST/'design.md').read_text().split('\n\n',1)[1])
 add(r'Конкретный backend — неизменённый Batch-Mesh-MPGAA* с размером плитки 8. Нижняя оценка клетки взята из существующего MD-A*: $L(s,q,t)=D_\alpha(s,q)+D_\alpha(q,t)+\kappa$, где $D_\alpha$ — масштабированная octile-метрика, а поправка $\kappa$ компилируется из исходного primitive mesh. В частности, клетка q может лежать внутри swept-трассы и не быть граничной вершиной решётки. Это не новая нижняя оценка. Полные формулы и C++ остаются в `cpp/include/ima/deferred.hpp`. Отложенные освобождения обслуживаются прежней нижнеоценивающей очередью с поправкой на перемещение старта.')
 add(table(['Вариант','Роль'],[['SMD-A*','Оба вида правок отложены, mesh bound и gap-сертификат'],['SMD без gap','Изолирует короткую проверку оптимальности incumbent'],['MD + Batch','Односторонний MD на том же backend; блокировки применяются заранее'],['Lazy blocks / eager opens','Все освобождения применяются сразу, без ненужной очереди; только блокировки отложены'],['Batch / MD-A* / LBA reuse / Boundary-Mesh / Conditional D* / Octile','Сильные самостоятельные контроли']]))
 add('Generic lazy search, incumbent/primal-dual bounds, suffix reuse и mesh-bound MD-A* — известные компоненты. Заявляемая гипотеза вклада — их совместный сертификат при отсутствии глобального порядка между рабочим и наблюдаемым графом. Приоритет этого сочетания не установлен; нужен более широкий обзор полных текстов Lifelong-GLS/GD* и других lazy incremental методов. Официальные внешние реализации здесь не портированы. Код содержит дополнительный аудит: сохранённый путь допустим в observed-карте и оптимален в working-графе; случайные проверки сравнивают ответы с прямым primitive Dijkstra. ASan/UBSan проходят.')
 add('# Протокол')
 add(m['protocol'])
 add('Контролей и новых вариантов много, но единицы эксперимента не следует суммировать как независимые карты. Основная replay-панель car — 48 конфигураций шести карт и двух корней; четыре history-инстанса показаны отдельно. Grid replay — 96 прежних случаев четырёх плотностей random50; сильный Octile reuse сохраняется. Holdout-навигация: второй корень на всех шести car-картах, раскрытие с радиусами 8/16/32/64 и динамика при (k,cr)=(2,5%),(32,20%), n=k. Радиус — квадратная клеточная окрестность, move — исходный примитив. Динамическая видимость задана по глубине свободной primitive-решётки без окклюзии. При n=k одновременно меняются обзор и частота, поэтому их эффекты не разделяются.')
 add(f"Медиана относительного MAD времени эпизода: {100*a['relative_mad_median']:.2f}%, p95: {100*a['relative_mad_p95']:.2f}%. Три временных повтора — не три независимые карты. Память — отдельно запрошенные байты C++ new, не RSS. Общие шаблоны моделей готовятся заранее и отражены в JSON. Бюджет 1 000 000 раскрытий на запрос общий для всех внутренних раундов SMD. Нельзя засчитывать остановку по бюджету как NoPath. Проверяется стоимость каждого завершённого ответа с точностью $10^{{-6}}$.")
 add('# Результаты по картам')
 add(figure('by_map','Полное время по картам относительно самой быстрой завершившейся контрольной реализации. Семейства и настройки отдельно доступны в CSV.'))
 for (cohort,control),d in maps.groupby(['cohort','control']):
  add(f'## {cohort}, {control}');rows=[]
  for name,g in d.groupby('map'):
   row=[name]
   for b in ['best_control','md_batch','batch_mpgaa','conditional_dstar','smd_plain','lazy_blocks_batch']:
    v=g[g.baseline.eq(b)];row.append('—' if v.empty else f'{num(v.iloc[0].full_speedup)} / {num(v.iloc[0].repair_speedup)} ({int(v.iloc[0].pairs)}/{int(v.iloc[0].configurations)})')
   rows.append(row)
  add(table(['Карта','Fastest','MD+Batch','Batch','Cond D*','No gap','Eager opens'],rows))
  add('Формат: полное / ремонт × (завершённые пары / конфигурации). Eager-open и gap-off абляции навигации не добавлялись автоматически: недостающие клетки показаны прочерком.')
 add('# Механизм ремонта')
 add(figure('activation','Какая доля наблюдаемых правок реально доставлена в backend. Только одинаковые replay-входы; начальные препятствия исходной карты не являются новыми правками.'))
 rows=[]
 for (cohort,control),d in work[work.method.eq('smd_batch')].groupby(['cohort','control']):
  rows.append([cohort,control,int(d.blocks.sum()),int(d.activated_blocks.sum()),int(d.opens.sum()),int(d.activated_cells.sum()),int(d.optimistic_rounds.sum()),int(d.gap_hits.sum()),int(d.path_probes.sum())])
 add(table(['Набор','Модель','Blocks','Act B','Opens','Act O','Backend','Gap hits','Path probes'],rows))
 add('Backend — число вызовов API, включая нулевые раскрытия; оно не равно числу запусков полного нового A*. Gap hit означает принятие уже известного допустимого пути после сравнения с рабочим оптимумом. Path probes считает только дополнительную проверку optimistic-кандидата в observed-карте. Это не полный collision-API счётчик backend: историческое checked_cells также не охватывает все предварительные проверки. Время, число раскрытий, ремонт h, stamp-writes, очереди и доставленные изменения интерпретируются отдельно. Сумма deferred_block_cells в work.csv — сумма снимков; для максимума использовать max_deferred_blocks.csv.')
 add('# Радиусы, качество движения и память')
 add(figure('holdout_radius','Альтернативный корень: время планирования по радиусу на каждой карте. Крестики — незавершённые миссии, они не являются ускорениями.'))
 rows=[]
 for (name,radius),d in quality[quality.cohort.eq('navigation_unknown')].groupby(['map','radius']):
  row=[name,int(radius)]
  for method in ['smd_batch','md_batch','batch_mpgaa','lba_reuse','conditional_dstar']:
   v=d[d.method.eq(method)].iloc[0];row.append(num(v.static_stretch) if v.complete else 'нет goal')
  rows.append(row)
 add(table(['Карта','Радиус','SMD','MD+Batch','Batch','LBA reuse','Cond D*'],rows))
 add('Здесь значения — длина исполненного пути / начальный оптимум полной статической truth-карты, а не отношение времён. В динамике этот знаменатель не является нижней оценкой исполненного пути; там сохранены абсолютная длина, число moves и планирований. Каждый replanning-запрос точен относительно текущего belief, но контроллер не реализует активное исследование при NoPath. Он прекращает миссию; диагностические truth-снимки сохранены отдельно. Разные оптимальные пути могут приводить к разным наблюдениям и числу фаз.')
 add(figure('memory','Запрошенная heap-память, отдельный проход. Выбросы скрыты только на графике; максимумы не скрываются в таблице.'))
 rows=[]
 for (control,method),d in metrics.groupby(['control','method']):rows.append([control,LABEL[method],num(d.peak_heap_bytes.median()/2**20),num(d.peak_heap_bytes.max()/2**20),f'{int(d.complete.sum())}/{len(d)}'])
 add(table(['Модель','Метод','Медиана MiB','Максимум MiB','Завершено'],rows))
 add('# Caps, завершение и фактический cr')
 rows=[]
 for method,g in caps.groupby('method'):rows.append([LABEL[method],len(g),', '.join(sorted(x.replace('__',' / ') for x in g['case'].unique()))])
 add(table(['Метод','Capped calls','Конфигурации'],rows) if rows else 'Остановок по бюджету в этой серии нет.')
 rows=[]
 for _,r in completion.iterrows():rows.append([r.cohort,r.control,LABEL[r.method],f'{int(r.complete)}/{int(r.configurations)}'])
 add(table(['Набор','Модель','Метод','Завершено'],rows))
 rows=[]
 for (name,k,cr),d in changes.groupby(['map','k','requested_cr']):
  x=d[d.phases.gt(0)];rows.append([name,int(k),int(cr),num(x.actual_cr.min()),num(x.actual_cr.max()),int(d.clamped.sum()),f'{len(x)}/{len(d)}'])
 add(table(['Карта','k=n','Запрос cr%','Мин факт%','Макс факт%','Clamp phases','С фазами'],rows))
 add('cr считает сумму блокировок и освобождений / все клетки за фазу. Половины выбираются из исходных до фазы раздельных пулов, с защитой клеток агента и цели; число пар ограничивается доступной мощностью. Фактический cr=100·actual_changes/(число клеток·phases). Без фаз скорость изменения не оценивается. Ограниченные/нулевые фазы и метод-зависимые длины маршрутов не исключаются из исходных данных.')
 add('# Оценка пригодности для статьи')
 main_panel=summary[summary.cohort.eq('replay')&summary.control.eq('car16')&summary.panel.eq('main')]
 for b in ['best_control','md_batch','lazy_blocks_batch','smd_plain']:
  r=main_panel[main_panel.baseline.eq(b)].iloc[0]
  add(f"Основная balanced-панель car16, контроль {LABEL.get(b,b)}: полное время {num(r.full_speedup)}×, ремонт {num(r.repair_speedup)}×, выигрыш от 10% в {int(r.wins10)}/{int(r.pairs)} завершённых пар, всего {int(r.configurations)} конфигураций.")
 verdict=main_panel[main_panel.baseline.eq('best_control')].iloc[0]
 mesh=main_panel[main_panel.baseline.eq('lazy_blocks_batch')].iloc[0]
 if verdict.full_speedup>1.1 and mesh.full_speedup>1.1:
  add('На основной панели есть измеренный общий выигрыш и положительный эффект совместного откладывания относительно eager-open контроля. Это поддерживает дальнейшую разработку статьи, но ещё не устанавливает литературный приоритет или превосходство над внешними реализациями.')
 else:
  add('Требование убедительного общего преимущества на обычных картах пока не выполнено: основная панель не даёт одновременно более 10% по полному времени к самой быстрой контрольной реализации и к eager-open абляции. Отдельные успешные карты и экономия доставленных правок сохраняются как локальные результаты; объявлять алгоритм готовым победителем для ведущей конференции по этим данным нельзя.')
 rows=[]
 for _,r in summary[summary.baseline.isin(['best_control','md_batch','lazy_blocks_batch','smd_plain'])].iterrows():rows.append([r.cohort,r.control,r.panel,LABEL.get(r.baseline,r.baseline),num(r.full_speedup),num(r.repair_speedup),f'{int(r.pairs)}/{int(r.configurations)}'])
 add(table(['Набор','Модель','Панель','Контроль','Полное ×','Ремонт ×','Пары'],rows))
 add('Критерии убедительного результата: выигрыш не только над исходным MD, но и над тем же Batch-backend с односторонней обработкой; положительная роль mesh-bound против eager-open lazy-block варианта; повторяемость на нескольких обычных картах; отсутствие выигрыша за счёт недостижения цели или большего бюджета. Эти критерии проверяются приведёнными прямыми парами. Улучшение одной history-карты не заменяет результаты balanced main-панели. Заявка на ведущую конференцию потребует внешних L-GLS/GD* сравнений, большего числа корней и проверки литературного приоритета. Работа с дешёвыми 2D occupancy-проверками не доказывает выигрыш при высокоразмерной геометрии.')
 add('# Воспроизведение')
 add('```sh\nmake -C cpp/mesh_symmetric all test\npython cpp/mesh_symmetric/run_all.py --output cpp/mesh_symmetric/results/reproduction\npython cpp/mesh_symmetric/analyze.py\npython cpp/mesh_symmetric/report.py\n```')
 add('Файл frozen/manifest.json фиксирует код, входы и план; results/full/experiment.json фиксирует бинарники, команды, исходные CSV и метаданные. Тесты и preflight вынесены из измеряемой серии. Анализ также принимает --directory; PDF требует Pandoc, XeLaTeX и Noto. Общий обзор связанных работ и результаты отрицательного первого этапа находятся в docs/mesh_envelope/report.pdf и related_work.md.')
 report=writer.render(DEST/'report.md','\n\n'.join(o),'SMD-A*: симметричное откладывание правок mesh-графа','ru-RU')
 p=[];put=p.append
 put('# Abstract')
 put(f"We study exact incremental planning with fixed-cost motion primitives under occupancy updates. A single working graph can contain deferred obstacles and omit deferred openings, making it neither an optimistic nor a pessimistic model of the observed graph. We propose SMD-A*, which couples actual-path feasibility with mesh-derived swept-cell detour bounds. A known feasible incumbent can be accepted when the exact working optimum meets its cost, even if other tied working paths are invalid. The implementation wraps an unchanged mesh adaptive-search backend. A separate frozen study measures {a['timed_runs']:,} timing episodes and {a['memory_runs']:,} allocation episodes on {a['scenarios']} configurations, using shared-backend, gap-off, eager-open lazy-block and strong standalone controls. All completed answers match exact references; capped or unsuccessful missions are reported rather than counted as speedups. Priority of the particular combination remains a hypothesis, not an established first-in-literature claim.")
 put(f"The balanced 48-case car replay panel yields {num(verdict.full_speedup)} episode speedup against the fastest completed control and {num(mesh.full_speedup)} against eager-opening lazy blocking. Thus the implementation does not establish a useful general runtime advantage from symmetric mesh deferral on these inexpensive occupancy benchmarks, despite reducing backend update activation.")
 put('# Problem and algorithm')
 put((DEST/'design.md').read_text().split('\n\n',1)[1])
 put('The existing mesh compiler provides an admissible swept-cell lower bound L(s,q,t). We reuse its fast scaled-octile/projection-correction form and its moving-start lower-bound heap. Neither that bound nor generic lazy evaluation is claimed as new. The proposed contribution is the coupled acceptance/repair certificate when opposite update types are deferred and a global graph ordering is unavailable. Cell updates are given, not a precomputed changed-edge list; withholding irrelevant cells can avoid enumerating many translated primitive effects.')
 put('# Evaluation')
 put(m['protocol'])
 put('The 52 car replay inputs include 48 balanced map/root/family configurations and 4 separately reported history cases. The 96 grid inputs retain the strong Octile reuse control. Navigation uses the alternate root on each of six car maps, four discovery radii, and two n=k dynamic anchors. The replay inputs informed development; alternate-root navigation was not measured in the first stage, although all specifications were already public within this repository. Three serial randomized repeats and separate allocation measurement are used. No earlier seconds are pooled. A million-expansion cap is shared over all internal SMD repair rounds.')
 rows=[]
 for _,r in summary[summary.baseline.isin(['best_control','md_batch','lazy_blocks_batch','smd_plain'])].iterrows():rows.append([r.cohort,r.control,r.panel,LABEL.get(r.baseline,r.baseline),num(r.full_speedup),num(r.repair_speedup),f'{int(r.pairs)}/{int(r.configurations)}'])
 put(table(['Cohort','Model','Panel','Comparator','Episode ×','Repair ×','Pairs'],rows))
 put('Ratios above one favor SMD-A*. The descriptive fastest-control envelope selects a completed control by whole-episode median after measurement. Replay completion includes correct failure proofs; navigation completion requires reaching the goal. Missing pairs and caps are retained in the accompanying report. Different optimal paths may generate different subsequent observations, so replay gives the stricter identical-input comparison.')
 put(f"On the balanced 48-case car replay panel, the geometric-mean episode speedup is {num(verdict.full_speedup)} against the fastest completed control and {num(mesh.full_speedup)} against eager-opening lazy blocking. These values include construction and the first query; repair-only values are shown separately. The results support only the regimes where the measured ratios exceed one, not a claim of universal superiority.")
 put(figure('activation','Fraction of observed update cells activated in the backend on identical replay inputs.'))
 put(figure('holdout_radius','Alternate-root discovery navigation; crosses denote unsuccessful missions and are not speedup evidence.'))
 put(figure('memory','Separate requested-heap measurements.'))
 put('# Limitations and related work')
 put('The first stage found no useful standard-map advantage for a mesh negative envelope over independent lattice witnesses; this motivated targeting positive replanning. SMD combines established lazy search, incumbent bounds, adaptive A*, suffix reuse and the repository\'s prior mesh detour bound. Its novelty hypothesis is the particular two-sided swept-cell certificate. Lifelong-GLS and Generalized D* are closely related incremental lazy planners; external implementations were not integrated. IPC/IDPC already combine path and cut reasoning for feasibility. A full priority review is required before submission. The grid and car controls use identical frozen Hermite primitives and binary2D maps, not official optimized primitive libraries or expensive high-dimensional collision models. One alternate navigation root per point limits statistical strength; n=k changes sensing and frequency together.')
 put('Additional candidate validation can be wasted when many optimistic paths collide, and the expansion budget may be reached even where eager repair succeeds. The initial working model can also be a poor guide after dense changes. Deferred cell sets and repeated paths consume memory and validation work. Conversely, activation and gap-hit counts explain the proposed repair mechanism without treating the historical partial checked_cells counter as a full geometry count. The complete report preserves per-map ratios, all completion failures, actual clamped rates and latency percentiles.')
 put('# References')
 put((ROOT/'docs/mesh_envelope/related_work.md').read_text().split('\n\n',2)[2])
 paper=writer.render(DEST/'paper.md','\n\n'.join(p),'SMD-A*: Exact Mesh Replanning with Two-Sided Update Deferral','en-US')
 provenance=dict(status='passed',analysis_sha256=base.sha(ad/'analysis.json'),source_sha256=base.sha(Path(__file__)),design_sha256=base.sha(DEST/'design.md'),related_work_sha256=base.sha(ROOT/'docs/mesh_envelope/related_work.md'),report=report,paper=paper)
 (ad/'report_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(DEST/'paper.pdf')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
