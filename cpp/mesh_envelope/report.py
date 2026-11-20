#!/usr/bin/env python3
"""Generate a Russian experiment report and an English paper from validated data."""
import argparse,json,math,re,subprocess,sys
from pathlib import Path
import pandas as pd
from analyze import HERE,ROOT,DEST,NEW,ABLATION,LABEL,gm,sha

def num(x,d=2):return f'{x:.{d}f}' if pd.notna(x) and math.isfinite(float(x)) else '—'
def table(head,rows):
 def c(x):return str(x).replace('|','/').replace('\n',' ')
 return '| '+' | '.join(map(c,head))+' |\n| '+' | '.join(['---']*len(head))+' |\n'+'\n'.join('| '+' | '.join(map(c,row))+' |' for row in rows)
def fig(name,caption):return f'![{caption}](figures/{name}.png){{width=99%}}'
def render(path,body,title,language):
 header=f'''---
title: "{title}"
author: "C++17 research artifact"
lang: {language}
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
 parts=re.split(r'(```[\s\S]*?```|`[^`\n]*`)',body)
 body=''.join(p if i%2 else re.sub(r'(?<=\w)\*(?!\*)',r'\\*',p) for i,p in enumerate(parts)).replace('A***','A\\***')
 path.write_text(header+body+'\n')
 command=['pandoc',str(path),'-o',str(path.with_suffix('.pdf')),'--pdf-engine=xelatex','--resource-path='+str(DEST),
          '--include-in-header='+str(ROOT/'docs/experiments/layout.tex'),'--lua-filter='+str(ROOT/'cpp/mpgaa_mesh/vector_images.lua')]
 result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,check=True)
 if 'Missing character' in result.stderr:raise RuntimeError(result.stderr)
 if result.stderr:print(result.stderr)
 return dict(markdown_sha256=sha(path),pdf_sha256=sha(path.with_suffix('.pdf')),command=command)

def main(directory,frontier_directory,conditional_directory):
 subprocess.run([sys.executable,str(ROOT/'cpp/mesh_probe_count/analyze.py')],cwd=ROOT,check=True)
 probe_path=ROOT/'cpp/mesh_probe_count/results/analysis/analysis.json';pmeta=json.loads(probe_path.read_text());assert pmeta['status']=='passed'
 ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed' and a['analysis_source_sha256']==sha(HERE/'analyze.py')
 for p,h in a['tables_sha256'].items():assert sha(ad/p)==h
 for p,h in json.loads((ad/'figures.json').read_text()).items():assert sha(ROOT/p)==h
 manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text())
 metrics=pd.read_csv(ad/'case_metrics.csv');pairs=pd.read_csv(ad/'paired_cases.csv');summary=pd.read_csv(ad/'summary.csv');maps=pd.read_csv(ad/'map_pairs.csv');family=pd.read_csv(ad/'family_pairs.csv');work=pd.read_csv(ad/'work.csv');answers=pd.read_csv(ad/'answer_types.csv');queries=pd.read_csv(ad/'queries.csv');qp=pd.read_csv(ad/'query_pairs.csv');changes=pd.read_csv(ad/'actual_changes.csv');completion=pd.read_csv(ad/'completion.csv');statuses=pd.read_csv(ad/'statuses.csv')
 out=[];add=out.append
 add('# Проверяемый результат')
 add(f"Добавлены три алгоритма C++17: **Envelope-Mesh**, **Dual-Certificate Mesh** и **Bellman-Circuit Mesh D* Lite**, а также четыре контрольных варианта. Выполнены {a['timed_runs']:,} временных эпизодов, {a['memory_runs']:,} отдельных эпизодов памяти на {a['scenarios']} конфигурациях; получено {a['timed_calls']:,} временных вызовов. Расхождений достижимости или стоимости у завершённых ответов: {a['exact_cost_disagreements']}; остановок по лимиту: {a['capped_calls']}. Независимые тесты проверили 10 852 ответа через прямой Dijkstra. ASan/UBSan прошли. Логические результаты обычного и allocation-прогонов совпали в {a['allocation_matched_rows']:,} строках.")
 cap=statuses[statuses.status.eq('capped')].groupby('method')['size'].sum()
 add('Остановки по бюджету: '+('; '.join(f'{LABEL.get(m,m)}: {int(n)}' for m,n in cap.items()) or 'нет')+'. Ни один ограниченный ответ не засчитывается как доказательство отсутствия пути.')
 rows=[]
 for m in NEW:
  d=pairs[pairs.method.eq(m)&pairs.baseline.eq('best_control')];mtr=metrics[metrics.method.eq(m)]
  rows.append([LABEL[m],f'{int(mtr.complete.sum())}/{len(mtr)}',num(gm(d.full_speedup)),num(gm(d.repair_speedup)),num(gm(d.memory_multiplier)),f'{int(d.full_speedup.ge(1.1).sum())}/{int(d.full_speedup.notna().sum())}'])
 add(table(['Алгоритм','Завершено','Эпизод ×','Ремонт ×','Память / baseline','Выигрыш ≥10%'],rows))
 add('Эта общая строка описывает именно смесь выбранных конфигураций: 96 небольших grid replay представлены чаще, чем отдельные большие карты. Основные выводы следует читать по отдельным картам и семействам ниже. Геометрические средние рассчитаны по общим завершённым конфигурациям. В replay точный ответ «пути нет» считается завершением; в навигации требуется достичь цели. Память / baseline меньше 1 выгодна кандидату. Время включает конструктор планировщика и первый поиск; ремонт исключает только конструктор и запрос 0.')
 add('`best_control` — описательная огибающая: для каждой конфигурации после измерений выбран прежний завершившийся контроль с минимальной медианой полного времени эпизода. Его время ремонта может не быть минимальным. В огибающую входят '+', '.join(LABEL[x] for x in manifest['controls'])+'. Прямые парные сравнения с каждым методом сохранены в CSV. Новые абляции в эту огибающую не входят.')
 add(fig('performance_profile','Распределение выигрышей и проигрышей полного эпизода относительно самой быстрой реализации контроля.'))
 add('# Идея и корректность')
 add(fig('certificate_idea','Общий свидетель mesh-префикса и замкнутое надмножество, которое сохраняется после блокировок.'))
 add(r'''Состояния исходного направленного графа — $(i,j,\theta)$. Каждый примитив имеет исходную положительную стоимость и упорядоченную трассу клеток. Для каждого направления строится префиксное дерево этих трасс. Общие префиксы проверяются один раз. Это развёрнутая форма mesh без всех слияний эквивалентных конфигураций оригинального MeshA*. В новых алгоритмах глобальный поиск и очередь D* хранят граничные состояния, а mesh отвечает за общее представление и ремонт локальных семейств переходов. Исходный MeshA* и C-Mesh-D* Lite участвуют в замерах отдельно.''')
 add('Входная правка — клетка занятости, а не готовый список изменившихся рёбер примитивного графа. Одна клетка принадлежит множеству переведённых swept-трасс. Обычному динамическому графовому методу ещё нужно породить эти изменения дуг; mesh-граница подписывается только на заблокированные свидетельства, поддерживающие текущий отрицательный ответ. Именно преобразование cell-to-family на ремонтируемой границе, а не общий факт о замкнутом множестве, является узкой гипотезой вклада.')
 add(r'''**Отрицательный сертификат.** После полного неуспешного A* сохраняется множество $R$ всех закрытых граничных состояний. Инвариант: $s\in R$, $t\notin R$ и каждый допустимый переход из $R$ заканчивается в $R$. Следовательно, любой путь из старта остаётся внутри $R$ и не достигает цели. Блокировки только удаляют переходы и сохраняют этот инвариант. Поэтому $R$ можно не уменьшать; оно становится безопасным надмножеством реально достижимых состояний. Это избавляет от сложного удаления поддеревьев связности, но может привести к лишнему вызову точного поиска.''')
 add(r'''Для выхода из $R$ хранятся первые заблокированные узлы mesh-префиксов. Узел покрывает сразу все продолжающие его примитивы. Поддерево пропускается, если все его конечные состояния уже в $R$, за картой или заблокированы. Заблокированные конечные клетки представлены неявно: при освобождении такой клетки перечисляются входящие примитивы и проверяются только хвосты в $R$. Это предотвращает создание отдельной подписки для каждого примитива к каждому заблокированному конечному состоянию.''')
 add(r'''Пакет правок сначала целиком применяется к карте убеждений. Освобождённый явный свидетель вызывает проверку полного префикса: после нового препятствия свидетель может переместиться ближе к началу. Если переход стал допустим, его конец добавляется в $R$, затем выполняется обычное раскрытие достижимости с mesh-обходом. При попадании цели в $R$ сертификат отбрасывается и запускается точный взвешенный A*. Заливка достижимости никогда не возвращает стоимость или положительный путь. При старте вне $R$ также нужен точный поиск.''')
 add(r'''**Полнота событий.** Вновь допустимый выход из $R$ либо оканчивается в только что освобождённой клетке, либо прежде был покрыт заблокированным mesh-свидетелем. В первом случае он обнаруживается входящим соединением, во втором — освобождением свидетеля. Все новые состояния раскрываются до принятия сертификата. Блокировки не создают выходов. Значит, принятый сертификат остаётся замкнутым. Для физически заблокированных исходных состояний $R$ используется безопасный суперграф с проверкой клеток после начала примитива; это может только вызвать лишний откат к A*, но не ложный ответ «пути нет». Текущий старт и цель проверяются отдельно.''')
 add(r'''**Dual-Certificate Mesh.** Добавляет к Envelope-Mesh известное правило оптимального суффикса: после одних блокировок сохранившийся суффикс прежнего оптимального пути остаётся оптимальным от текущего граничного состояния. Любое освобождение удаляет положительный сертификат, потому что путь мог стать короче. Это правило не заявляется как новая научная идея; его роль — устранить лишние поиски на положительных запросах и проверить совместимость двух сертификатов.''')
 add(r'''**Bellman-Circuit Mesh D* Lite.** Лист примитива $p$ имеет значение $c_p+g(v_p)$. Заблокированный mesh-узел равен $\infty$, свободный — минимуму детей и терминалов. Корень точно равен $rhs(u)$, кроме стандартного условия цели. Изменение $g$ затрагивает входящие листья, изменение карты — переведённые mesh-узлы. Минимумы распространяются к корню до первого неизменившегося результата. В очередь D* попадает только несогласованный граничный корень. Это сохраняет Bellman-уравнения исходного графа. В реализации нет сжатия однодетных цепочек; хранится double на каждый узел локального префиксного дерева, поэтому память и локальная работа могут стать слабым местом.''')
 add(table(['Вариант','Назначение'],[['Mesh cold','Идентичный точный backend; ничего не сохраняет'],['Mesh reuse','Тот же backend и только положительный суффикс'],['Cut reset','Отрицательное R сохраняется после блокировок; любое освобождение сбрасывает его'],['Lattice-Envelope','Тот же R и неявные конечные свидетели, но отдельные проверки каждого примитива вместо mesh-префикса']]))
 add(r'''**Стоимость и границы.** Хранение $R$ занимает $O(|V|)$ бит плюс список состояний $O(|R|)$; явные подписки — $O(|W|)$ для множества свидетелей. Пакет с $o$ освобождениями содержит входящее соединение $O(oP)$ по шаблонным примитивам, проверку затронутых префиксов и обход новых состояний. Между точными перестроениями каждое состояние добавляется в $R$ один раз. Противник может вызывать перестроение после каждого пакета, поэтому общего асимптотического превосходства над D* Lite нет. Старые избыточные свидетели не очищаются после каждой блокировки; они проверяются при освобождении и удаляются при перестроении. Обратное соединение конечных клеток пока не использует общий suffix-mesh.''')
 add('# Экспериментальный протокол')
 add(manifest['protocol'])
 add('Модель car16: 16 направлений, 284 примитива, суммарно 1 492 проверяемые клетки в исходных трассах, максимум 8 клеток после начала; префиксный forest содержит 572 узла вместе с 16 корнями, исходный configuration mesh — 412 конфигураций. Grid8: одно направление состояния, восемь одноклеточных переходов, forest из 9 узлов. У grid8 нет длинных общих префиксов; это необходимый отрицательный контроль структурной выгоды mesh.')
 add('Шесть car-карт: Berlin, AR0700, arena, MA_maze96, MA_room96, MA_random96. Первые три берутся в исходном размере, последние три — прежние фиксированные кропы Moving AI. В replay есть два корня и четыре семейства: препятствия на пути, вне пути, смешанные блокировки/освобождения, раскрытие неизвестной карты; добавлены четыре прежних history-эпизода. Grid replay — все 96 прежних сценариев random50 с четырьмя плотностями. Новые синтетические эпизоды: разделяющая полоса шириной 7 клеток, размеры 32 и 64, два варианта карты с разными seed и одинаковыми координатами концов, правки вдали, на границе и с периодическим открытием/закрытием прохода; 17 запросов. По этим данным оценивается окупаемость для 0, 1, 2, 4, 8, 16 ремонтов. Префиксы одного эпизода зависимы и не считаются отдельными независимыми запусками.')
 add('Для автономной навигации раскрытие карты проверено на всех шести car-картах с радиусами 8, 16, 32, 64 и одним прежним корнем. Динамика проверена на всех 16 картах в двух заранее выбранных точках (k,cr)=(2,5%), (32,20%); n=k. Это сокращённый новый срез прежней полной сетки k/cr, а не её повторное измерение. В навигации только один корень на точку, поэтому выводы по отдельной точке разведочные. Один move означает один исходный примитив, а не одну клетку. Статический радиус — квадратная $L_\\infty$-окрестность. Динамическая глубина n задаётся по свободной решётке примитивов с учётом направления; наблюдаются все клетки трасс дуг этой глубины без окклюзии препятствиями. Пути могут различаться при равной оптимальной стоимости, следовательно последующие наблюдения и динамические миры при различном ходе агента тоже могут различаться. Результаты replay дают более строгую проверку на одинаковых входах.')
 add(f"CPU: {state['cpu']}; {state['platform']}; один измерительный процесс, affinity {state['affinity']}. Компилятор и точные флаги сохранены в JSON каждого задания; все контроли собраны и измерены заново в том же запуске. Бюджет — {manifest['cap']:,} раскрытий на запрос, точность проверки стоимости $10^{{-6}}$. Три повтора выполняются последовательно со случайным порядком алгоритмов; память измеряется четвёртым отдельным проходом. Время проверки эталона не входит во время планировщика. Общая подготовка mesh-шаблонов вынесена из конструктора и отражена в JSON, включая собственную память. Peak heap — число запрошенных байтов C++ new, не RSS и не полный расход процесса.")
 add(f"Медиана относительного MAD полного времени эпизода: {100*a['repeat_relative_mad_median']:.2f}%; p95: {100*a['repeat_relative_mad_p95']:.2f}%. Три повтора недостаточны для сильных статистических утверждений; большие отношения на микросекундных запросах проверяются также полным временем и счётчиками.")
 add(fig('map_atlas','Измеренные карты из замороженных входов: зелёный старт и красная цель первого инстанса. Дополнительно показаны синтетические разделители.'))
 add('# Результаты по картам')
 add(fig('map_replay','Полное время replay по картам относительно самого быстрого контроля; в ячейке отношение времён.'))
 for (cohort,control),d in maps[maps.baseline.eq('best_control')&maps.method.isin(NEW)].groupby(['cohort','control'],sort=False):
  add(f'## {cohort}, {control}')
  rr=[]
  for name,g in d.groupby('map',sort=False):
   row=[name]
   for m in NEW:
    x=g[g.method.eq(m)].iloc[0];row.append(f"{num(x.full_speedup)} / {num(x.repair_speedup)} ({int(x.pairs)}/{int(x.configurations)})")
   rr.append(row)
  add(table(['Карта',*[LABEL[m] for m in NEW]],rr));add('Формат: полное / ремонт × (общие завершённые / конфигурации). Значения выше 1 выгодны новому методу. Для всех пар по каждому отдельному контролю см. `analysis/map_pairs.csv`.')
 add('## Динамика: отдельные точки k/cr')
 points=pd.read_csv(ad/'navigation_points.csv');rr=[]
 for (control,name,k,cr),d in points.groupby(['control','map','k','cr']):
  row=[control,name,f'{int(k)}/{int(cr)}']
  for m in NEW:
   v=d[d.method.eq(m)].iloc[0];row.append(f'{num(v.full_speedup)} / {num(v.repair_speedup)}' if v.complete else 'нет общей goal-пары')
  rr.append(row)
 add(table(['Модель','Карта','k/cr% (n=k)',*[LABEL[m] for m in NEW]],rr))
 add('Полное / ремонт × к быстрейшему завершившемуся контролю в данной точке; одна seed-миссия на точку, три повтора времени. Отсутствие общей goal-пары не считается ни ускорением, ни успешным решением. Все завершения показаны отдельно ниже.')
 add('# Повторные отрицательные ответы и эффект mesh')
 add('Миссии обычной навигации прекращаются при первом NoPath; сертификат, построенный в этот момент, не может окупиться. Кроме того, в динамической модели k moves без следующих движений не будет следующих фаз. Новый механизм предназначен для продолжения запросов после временного разрыва связности: агент ждёт открытия двери либо сервис получает внешние изменения. Синтетический replay с фиксированным стартом моделирует такие ожидающие запросы, но не исполненную поездку; reconnect проверяет возвращение к положительному точному поиску. Эти выигрыши нельзя переносить на все терминальные навигационные миссии.')
 rows=[]
 for (control,fam),d in family[family.cohort.eq('separator')&family.method.isin(NEW)&family.baseline.isin(['lba_reuse','dstar_lattice','lattice_envelope','mesh_reuse'])].groupby(['control','family']):
  for m in NEW:
   row=[control,fam,LABEL[m]]
   for b in ['lba_reuse','dstar_lattice','mesh_reuse','lattice_envelope']:
    x=d[d.method.eq(m)&d.baseline.eq(b)];row.append(num(x.iloc[0].full_speedup) if len(x) else '—')
   rows.append(row)
 add(table(['Модель','Сценарий','Метод','LBA reuse ×','D* Lite ×','Mesh reuse ×','Lattice-Envelope ×'],rows))
 add(fig('amortization','Окупаемость с учётом первого поиска и построения сертификата; геометрическое среднее полного времени по двум размерам и двум seed.'))
 add('В манифесте синтетические seed-инстансы названы roots; координаты старта и цели в них фиксированы, меняются случайные препятствия. В стандартных replay два корня различаются также стартом и целью.')
 add('Начальная стоимость включает повторный mesh-обход границы после исчерпания OPEN; он не подменяется бесплатным построением сертификата. Выигрыш относительно Lattice-Envelope отражает именно совместную обработку префиксов. На grid8 один шаг примитива занимает одну конечную клетку: структурного преимущества общего префикса здесь ожидать нельзя. Быстрый ответ на удалённые правки сам по себе ещё не доказывает пользу mesh; важен этот контроль.')
 rows=[]
 for (control,m,b),d in qp[qp.cohort.eq('replay')&qp['query'].gt(0)&qp.baseline.isin(['lba_reuse','mesh_reuse','dstar_lattice'])].groupby(['control','method','baseline']):
  rr=[control,LABEL[m],LABEL[b]]
  for answer in ['path','no_path']:
   v=d[d.answer.eq(answer)];rr.append(f'{num(gm(v.speedup))} ({len(v)})')
  rows.append(rr)
 add(table(['Модель','Кандидат','Baseline','Положительные × (N)','Нет пути × (N)'],rows))
 add('Эта таблица использует медианы запросов только replay. В одном эпизоде запросы зависимы; N показывает число пар запросов, а не независимых карт. Поскольку огибающая выбирается по эпизоду, она не подменяет приведённые прямые сравнения типов ответа.')
 add(fig('all_collision_probes','Отдельный счётный проход: все вызовы Grid.free внутри replan, включая предварительные проверки концов. Добавлена единица для логарифмической шкалы. Время этого бинарника не используется.'))
 add('## Полный счётчик обращений к проверке занятости')
 add(f"Старое поле checked_cells считает явные проверки трасс/узлов, но пропускает предварительные проверки конечных клеток в candidate и часть проверок условий входа. Его нельзя трактовать как полное число collision queries. Поэтому выполнен отдельный count-only проход на всех 184 replay-входах: {pmeta['counted_runs']} эпизодов с пятью методами, все вызовы Grid.free перехвачены в сгенерированной копии заголовков, измеряемые исходники не изменялись. {pmeta['logical_matched_rows']} строк совпали по всем прежним логическим полям с обычными траекториями. Инструментированный бинарник не используется для сравнения времени. Считаются логические вызовы API, включая проверки вне карты; прямые Grid.blocked в общей нормализации входа и эталонные/проверочные поиски исключены. Это не число физических CPU-чтений памяти.")
 pw=pd.read_csv(probe_path.parent/'probe_work.csv');pp=pd.read_csv(probe_path.parent/'probe_pairs.csv');rr=[]
 for (control,m),d in pw.groupby(['control','method']):
  n=d.all_free_calls.sum();old=d.legacy_checks.sum();rr.append([control,'Conditional D* Lite' if m=='conditional_dstar' else LABEL[m],num(n/1e6),num(old/1e6),num(100*(n-old)/n)])
 add(table(['Модель','Метод','Все Grid.free, млн','Legacy, млн','Пропущено legacy, %'],rr))
 rr=[]
 for (control,cohort,m,b),d in pp.groupby(['control','cohort','method','baseline']):
  a=d[~d.online];o=d[d.online];rr.append([control,cohort,LABEL[m],'Conditional D* Lite' if b=='conditional_dstar' else LABEL[b],num(gm(a.ratio)),num(gm(o.ratio)),f'{int(a.complete.sum())}/{len(a)}'])
 add(table(['Модель','Набор','Метод','Контроль','Probes F ×','Probes R ×','Пары'],rr))
 add('Значения больше 1 означают меньше вызовов проверки занятости у кандидата. Если время улучшается без уменьшения этих вызовов, причина в других операциях; если число обращений меньше, но время хуже, сказывается обслуживание индексов, очередей и множеств. Полный legacy-счётчик сохранён для сопоставления с прежними отчётами, но вывод о суммарной геометрической работе опирается на этот отдельный проход.')
 add('# Число изменений, радиус, задержки и память')
 add(fig('edit_scaling','Ремонт по числу наблюдаемых правок в replay; контроль LBA* reuse. Корзины и число пар доступны в query_pairs.csv.'))
 add(fig('discovery_radius','Раскрытие полностью неизвестной карты: фиксированная цель, радиусы 8/16/32/64. Линии соединяют завершённые миссии; крестики показывают время незавершённых и не считаются выигрышами.'))
 add('Статическое раскрытие даёт только новые блокировки, поэтому отрицательный сертификат редко нужен до терминального отказа. Выигрыш Dual-Mesh в этом режиме может объясняться известным суффиксом и выбранным backend, а не новым механизмом отрицательной границы. Envelope-Mesh без положительного сертификата измерен отдельно именно для такого разделения.')
 add(fig('travel_quality','Длина исполненного пути в статической неизвестной карте / оптимум по полной исходной truth-карте. Незавершённые миссии не получают значение.'))
 add('Точность каждого replanning-запроса не означает оптимальность всего исполненного пути в неизвестной карте: агент мог сделать объезд до раскрытия препятствия. Для статического раскрытия нормированная длина обязана быть не меньше 1; это дополнительно проверяется анализом. Для динамических карт такое отношение к исходному статическому оптимуму не является мерой субоптимальности, поскольку препятствия меняются. Абсолютная длина, число moves и число планирований всех навигационных эпизодов сохранены в navigation_quality.csv.')
 add(fig('memory','Распределение пиков запрошенной C++ heap-памяти по конфигурациям. Выбросы скрыты только на рисунке; максимумы указаны в таблице.'))
 rows=[]
 for (control,m),d in metrics.groupby(['control','method']):
  rows.append([control,LABEL.get(m,m),num(d.peak_heap_bytes.median()/2**20),num(d.peak_heap_bytes.max()/2**20),f'{int(d.complete.sum())}/{len(d)}'])
 add(table(['Модель','Метод','Медиана MiB','Максимум MiB','Завершено'],rows))
 add('Картовые p50/p95/p99 задержки ремонтов приведены в `analysis/latency.csv`; их получают из медиан трёх временных повторов каждого запроса, не из пула всех повторов. Счётчики раскрытий, occupancy-проверок, уведомлений, построений/попаданий сертификата, добавлений R и событий свидетелей сохранены по картам и запросам. Они позволяют отличить экономию поиска от более дешёвого исполнения той же работы.')
 add('Число раскрытий у разных представлений относится к разным единицам: MeshA* раскрывает и внутренние конфигурации, новые методы — граничные состояния. Поэтому оно не является одинаковой операцией CPU. Старые D*-реализации не заполняют notify_probes для всех своих циклов; нули этого поля не означают отсутствие работы уведомлений. Время и occupancy-проверки интерпретируются отдельно.')
 add('# Фактический change rate и завершение навигации')
 rr=[]
 for (control,name,cr),d in changes.groupby(['control','map','requested_cr_pct']):
  active=d[d.phases.gt(0)];rr.append([control,name,int(cr),f'{len(active)}/{len(d)}',num(active.actual_cr_pct.min()),num(active.actual_cr_pct.max()),int(d.clamped_phases.sum())])
 add(table(['Модель','Карта','cr %','С фазами','Мин факт %','Макс факт %','Clamp фаз'],rr))
 add('cr здесь — доля всех клеток, изменённых за фазу, то есть сумма блокировок и освобождений. Каждая сторона выбирается из своего исходного до фазы пула; число пар ограничивается доступными клетками и защитой клеток текущего положения агента и цели. Фактический cr равен 100·actual_changes/(число клеток·phases). Эпизоды без фаз показываются отдельно. Разные маршруты могут дать разное число фаз; clamped_phases суммированы по алгоритмам, не по независимым мирам.')
 rr=[]
 for _,r in completion[completion.cohort.str.startswith('navigation')].iterrows():rr.append([r.cohort,r.control,LABEL.get(r.method,r.method),f'{int(r.complete)}/{int(r.configurations)}'])
 add(table(['Сценарий','Модель','Метод','Цель / конфигурации'],rr))
 frontier_path=frontier_directory/'analysis/analysis.json'
 fmeta=json.loads(frontier_path.read_text());assert fmeta['status']=='passed'
 for p,h in fmeta['tables_sha256'].items():assert sha(frontier_path.parent/p)==h
 for p,h in fmeta['figures_sha256'].items():assert sha(ROOT/p)==h
 fs=pd.read_csv(frontier_path.parent/'summary.csv');fm=pd.read_csv(frontier_path.parent/'case_metrics.csv')
 add('# Отдельная структурная проверка ширины границы')
 add(f"Дополнение содержит {fmeta['scenarios']} конфигураций, {fmeta['timed_runs']} временных и {fmeta['memory_runs']} allocation-эпизодов; {fmeta['allocation_matched_rows']} логических строк совпали. Оно объявлено до просмотра агрегированных основных времён и не включено в основные средние 228 конфигураций. Причина добавления — структурная: полоса шириной 7 превосходит размах car-примитивов, и конечные клетки всех выходящих переходов могут быть заблокированы; это скрывает явные префиксные свидетели за неявной обработкой концов. Поэтому отдельно проверены все ширины 1, 3, 7, два seed при фиксированных координатах концов, обе модели, размер 64 и чередующийся сдвиг полосы на одну клетку, 17 запросов. Сохранены все результаты, включая потенциально дорогие ложные откаты надмножества R при тонкой смещающейся стене.")
 add(fig('barrier_width','Отдельное дополнение: полное время и ремонт при разных ширинах движущейся разделяющей полосы.'))
 rr=[]
 for (control,width,m),d in fs[fs.method.isin(NEW)].groupby(['control','width','method']):
  row=[control,int(width),LABEL[m]]
  for b in ['lba_reuse','lattice_envelope','dstar_lattice']:
   v=d[d.baseline.eq(b)].iloc[0];row.append(f'{num(v.full_speedup)} / {num(v.repair_speedup)}')
  rr.append(row)
 add(table(['Модель','Ширина','Кандидат','LBA reuse F/R','Lattice F/R','D* Lite F/R'],rr))
 rr=[]
 for (control,width,m),d in fm[fm.method.isin(NEW+['lattice_envelope'])].groupby(['control','width','method']):
  rr.append([control,int(width),LABEL[m],int(d.online_envelope_builds.sum()),int(d.online_envelope_hits.sum()),int(d.online_guard_events.sum()),int(d.online_checked_cells.sum())])
 add(table(['Модель','Ширина','Метод','Перестроения','Cert hits','События cut','Occupancy'],rr))
 conditional_path=conditional_directory/'analysis/analysis.json'
 cmeta=json.loads(conditional_path.read_text());assert cmeta['status']=='passed'
 for p,h in cmeta['tables_sha256'].items():assert sha(conditional_path.parent/p)==h
 for p,h in cmeta['figures_sha256'].items():assert sha(ROOT/p)==h
 cs=pd.read_csv(conditional_path.parent/'summary.csv');cm=pd.read_csv(conditional_path.parent/'map_pairs.csv')
 add('# Усиленный контроль: условные изменения рёбер D* Lite')
 add('Код исходного D* Lite условно распространяет изменения g, но после уведомлений карты полностью пересчитывает rhs затронутых хвостов. Чтобы не выдать известную оптимизацию за новизну Circuit-Mesh, добавлен отдельный стандартный Conditional D* Lite: вновь допустимая дуга понижает rhs через c+g(head), а отключённая вызывает полный backup только при возможной поддержке текущего rhs. Все кеши пакета инвалидируются до backup; одинаковый активный ключ не добавляется повторно. Это контроль, а не новый заявляемый алгоритм.')
 add(f"В отдельном новом бинарнике совместно перемерены все три неизменённых кандидата и Conditional D* Lite: {cmeta['scenarios']} прежних replay-конфигураций, {cmeta['timed_runs']} временных и {cmeta['memory_runs']} allocation-эпизодов. Это повтор тех же входов, а не новые независимые карты; секунды не смешаны с основной серией. Выбор контроля сделан по анализу исходников до просмотра агрегированных основных сравнений. Навигация в этом дополнительном проходе не повторяется. Расхождений стоимости: {cmeta['exact_cost_disagreements']}; capped-вызовов: {cmeta['capped_calls']}; совпавших normal/allocation-строк: {cmeta['allocation_matched_rows']}.")
 rr=[]
 for _,v in cs.iterrows():rr.append([v.control,v.cohort,LABEL[v.method],f'{int(v.pairs)}/{int(v.configurations)}',num(v.full_speedup),num(v.repair_speedup),num(v.memory_multiplier)])
 add(table(['Модель','Набор','Кандидат','Пары','Полное ×','Ремонт ×','Heap / control'],rr))
 add(fig('conditional_control','Отдельная совместная серия: новые методы против условного D* Lite на одинаковых replay-входах.'))
 rr=[]
 for (control,cohort,name),d in cm.groupby(['control','cohort','map']):
  row=[control,cohort,name]
  for m in NEW:
   v=d[d.method.eq(m)].iloc[0];row.append(f'{num(v.full_speedup)} / {num(v.repair_speedup)} ({int(v.pairs)}/{int(v.configurations)})')
  rr.append(row)
 add(table(['Модель','Набор','Карта',*[LABEL[m] for m in NEW]],rr))
 add('В этом контроле, как и в исходном valid_edge, допустимость вспомогательной дуги проверяет клетки после начала. Исходящие дуги заблокированного состояния могут оставаться во вспомогательном графе, но свободный старт не может попасть в него через заблокированную конечную клетку. Текущие старт и цель проверяются отдельно. Таким образом физические пути и стоимости совпадают с постановкой; блокировки концов и перенос старта дополнительно проверены независимым Dijkstra. Подробности и код: cpp/mesh_conditional/README.md.')
 add('# Оценка научного результата')
 add('Для статьи наиболее содержательна гипотеза о ремонтируемом отрицательном mesh-сертификате. Она проста: хранить безопасное замкнутое надмножество, а не пытаться поддерживать точную компоненту после удалений. Новая часть в рамках этого репозитория — общая префиксная граница и неявные конечные свидетели. Доказательство отсутствия пути через замкнутое множество, инкрементальная достижимость, D* Lite и повторное использование суффикса давно известны. Проверенный набор источников ограничен; литературный приоритет сочетания не доказан.')
 # Give a concrete, falsifiable verdict using case-level evidence.
 for model in ['car16','grid8']:
  for m in NEW:
   d=pairs[pairs.control.eq(model)&pairs.cohort.eq('replay')&pairs.method.eq(m)&pairs.baseline.eq('best_control')]
   add(f"На {model} replay {LABEL[m]} имеет полное отношение {num(gm(d.full_speedup))}× и ремонт {num(gm(d.repair_speedup))}× к самому быстрому контролю на конфигурацию; выигрышей от 10% — {int(d.full_speedup.ge(1.1).sum())} из {int(d.complete.sum())} общих завершённых пар.")
 for model in ['car16','grid8']:
  for m in ['envelope_mesh','dual_mesh']:
   d=pairs[pairs.control.eq(model)&pairs.cohort.eq('separator')&pairs.method.eq(m)]
   l=d[d.baseline.eq('lattice_envelope')];same_backend='mesh_cold' if m=='envelope_mesh' else 'mesh_reuse';r=d[d.baseline.eq(same_backend)]
   if len(l) and len(r):add(f"На separator {model} {LABEL[m]} даёт {num(gm(r.full_speedup))}× по полному времени к контролю {LABEL[same_backend]} и {num(gm(l.full_speedup))}× к независимым lattice-свидетелям. Первая величина изолирует сохранение отрицательного ответа. Только сравнение Envelope-Mesh с Lattice-Envelope изолирует mesh-представление; для Dual-Mesh вторая величина включает также положительный суффикс.")
 for _,v in cs[cs.cohort.eq('replay')].iterrows():
  add(f"Дополнительная совместная проверка {v.control}: {LABEL[v.method]} / Conditional D* Lite — {num(v.full_speedup)}× по полному эпизоду, {num(v.repair_speedup)}× по ремонту, {int(v.pairs)}/{int(v.configurations)} общих завершённых конфигураций. Эти отношения следует использовать при оценке новизны Circuit-Mesh, а не только сравнение с полными backup после уведомлений.")
 add('Сильный результат для подачи должен одновременно показать: окупаемость построения, выигрыш относительно lattice-границы, повторяемость на нескольких стандартных картах и контролируемую потерю при восстановлении связи. Разница с одним медленным baseline или только специальные стены этого не устанавливает. Bellman-Circuit оценивается как отдельная простая альтернатива: если локальная арифметика и хранение значений дороже условных lattice-обновлений, этот отрицательный результат также следует сохранить.')
 add('Ограничения: единичные 2D occupancy-проверки дешёвы; высокоразмерные swept-volume коллизии не измерены. Префиксный forest не использует все слияния исходного mesh. Возможны лишние откаты из-за устаревшего надмножества R и лишние подписки после блокировок. Полные внешние реализации Lifelong-GLS/Generalized D* не интегрированы. Из прежних экспериментальных вариантов не повторялись отдельно Selective/Policy/Stamp/Witness и несколько старых параметризаций MD; их прежние секунды не смешиваются с этой серией. Автономная навигация использует один корень на точку. Это проверяемая исследовательская основа, а не установленное универсальное превосходство или готовое доказательство приоритета.')
 add('# Воспроизводимость и источники')
 add('```sh\nmake -C cpp/mesh_envelope all test\npython cpp/mesh_envelope/run_all.py --output cpp/mesh_envelope/results/reproduction\npython cpp/mesh_envelope/analyze.py\npython cpp/mesh_envelope/report.py\npython cpp/mesh_envelope/validate.py\n```')
 add('Первая команда собирает код и выполняет прямой Dijkstra. Вторая запускает новую серию без перезаписи существующих данных. Анализ и отчёт читают сохранённую серию `results/full`; другой каталог задаётся через `--directory`. Зависимости анализа: `cpp/mpgaa_mesh/requirements.txt`; PDF: Pandoc/XeLaTeX и Noto. `frozen/manifest.json` фиксирует исходники, входы и протокол; `experiment.json` — бинарники, команды и хеши результатов. Выполненный notebook воспроизводит итоговые таблицы. Старые измеренные каталоги сохранены без изменений.')
 add((DEST/'related_work.md').read_text().replace('# Related work and scope of the novelty claim','## Связанные работы'))
 report=render(DEST/'report.md','\n\n'.join(out),'Ремонт отрицательных ответов на mesh: алгоритмы и эксперименты','ru-RU')
 # The short English manuscript centers the proposed contribution; all claims
 # are computed from the exact same case-level table as the Russian report.
 article=[];put=article.append
 put('# Abstract')
 put(f"We study exact replanning on directed motion-primitive lattices represented by shared collision-cell prefix meshes. We propose a negative certificate: a closed superset of boundary states whose outgoing invalid transitions are covered by mesh-prefix witnesses. Edge deletions preserve the superset certificate; insertions repair only its exposed frontier. Blocked endpoints are represented implicitly, avoiding per-primitive terminal subscriptions. A dual variant combines this certificate with standard optimal-suffix reuse. We also evaluate a Bellman-circuit mesh variant of D* Lite. Our frozen C++17 study covers {a['scenarios']} configurations and {a['timed_runs']:,} serial timing episodes, with a separate allocation pass and exact cost validation. Results are reported per map and include failure episodes, reconnection, map discovery, construction overhead and strong controls. We claim a mesh-specific frontier representation and its correctness, not a new general reachability theorem or universal planner superiority.")
 put('# Problem and motivation')
 put('Updates are occupancy cells, not a precomputed list of changed primitive edges. One cell may occur in many translated swept traces. A generic dynamic graph method must first generate those arc changes. Our proposed contribution is a cell-to-family repair representation: subscriptions to blocked mesh-prefix witnesses, with implicit blocked endpoints, around a closed negative region. Unrelated cell updates need not materialize all affected arcs or repair weighted cost labels.')
 put('A failed shortest-path query is useful information. Standard suffix reuse accelerates surviving positive paths, but may repeat a full failure proof after an irrelevant edge insertion. Maintaining the exact reachable component under deletions is considerably harder than maintaining a closed superset. We exploit this asymmetry and compress its outgoing invalid boundary using the same primitive-prefix mesh that shares collision checks in MeshA*.')
 put('The intended consumer continues querying after temporary disconnection: e.g., a robot waiting for a door or a planning service receiving external map updates. Standard navigation in this study stops on its first NO_PATH. Under the k-move update model, stopping also prevents subsequent change phases. Negative-certificate construction cannot amortize in those terminal missions; they are retained as controls. Externally driven replay and reconnection isolate repeated-failure reuse. Fixed-start synthetic replay models waiting queries, not executed navigation.')
 put('# Method and correctness')
 put(fig('certificate_idea','A shared invalid prefix and a closed superset preserved under deletions.'))
 design=(DEST/'design.md').read_text();design=design[design.index('## Definitions and invariant'):design.index('## Variants and controls')];put(design)
 put('The **Envelope-Mesh** algorithm uses the negative certificate and an exact mesh boundary A*. **Dual-Mesh** additionally reuses a surviving optimal suffix after deletion-only updates; all insertions discard that positive certificate. Suffix reuse is established and is treated as a control, not a novelty claim. Cut reset discards R on any insertion. Lattice-Envelope retains the same R but replaces shared mesh witnesses by independent primitive witnesses. Mesh cold and Mesh reuse share exactly the same weighted backend as the proposed algorithms.')
 put('# Bellman-circuit alternative')
 design=(DEST/'design.md').read_text();put(design[design.index('## Bellman-Circuit Mesh D* Lite'):])
 put('# Experimental design')
 put(manifest['protocol'])
 put('The main car replay is balanced over six maps, two roots and four edit families. Grid replay contains the prior 96 small-grid dynamic cases. Synthetic separators isolate remote changes, changes along the closed boundary and periodic reconnection. They are mechanism tests rather than standard benchmarks. Closed-loop discovery uses four radii on all six car maps; dynamic runs cover all sixteen maps at two anchors, n=k. One root per navigation point limits statistical strength. All controls are freshly compiled and timed; published times are never pooled. Exact cost validation, Dijkstra tests, sanitizer checks and independent allocation runs are separate from measured kernel time.')
 put('# Results')
 rr=[]
 for (cohort,control,m),d in pairs[pairs.method.isin(NEW)&pairs.baseline.eq('best_control')].groupby(['cohort','control','method']):rr.append([cohort,control,LABEL[m],num(gm(d.full_speedup)),num(gm(d.repair_speedup)),f'{int(d.complete.sum())}/{len(d)}'])
 put(table(['Cohort','Model','Candidate','Episode speedup','Repair speedup','Pairs'],rr))
 put('The comparator is the fastest completed control per configuration by median whole-episode time, selected post hoc as a descriptive envelope. Ratios above one favor the candidate. Correct no-path replay answers count as completed; closed-loop missions require reaching the goal. Repair time excludes setup and the first query. No-path certificates are accepted only after full closure, never after an expansion cap.')
 put(fig('map_replay','Map-specific replay speedups against the fastest control.'))
 put(fig('amortization','Construction cost and amortization over consecutive repairs.'))
 rr=[]
 for (model,fam,m),d in pairs[pairs.cohort.eq('separator')&pairs.method.isin(NEW)&pairs.baseline.isin(['lba_reuse','lattice_envelope','dstar_lattice'])].groupby(['control','family','method']):
  rr.append([model,fam,LABEL[m],*[num(gm(d[d.baseline.eq(b)].full_speedup)) for b in ['lba_reuse','lattice_envelope','dstar_lattice']]])
 put(table(['Model','Changes','Candidate','LBA reuse','Lattice envelope','D* Lite'],rr))
 put(fig('discovery_radius','Unknown-map navigation by map and sensing radius; crosses are unsuccessful missions, not speedup evidence.'))
 put('# Structural complement: barrier width')
 put('Separately from the primary aggregate, we fixed a structural complement before inspecting aggregate primary times. A seven-cell separator can hide all outgoing free endpoints beyond the primitive span, so widths 1, 3 and 7 are all tested on 64x64 maps, two fixed-start map seeds, both control sets, with alternating one-column shifts. All widths, including conservative fallback failures, are retained. These twelve mechanism configurations are not pooled into the primary 228-case means.')
 put(fig('barrier_width','Separate structural complement: barrier-width sensitivity including cold construction.'))
 rr=[]
 for (model,width,m),d in fs[fs.method.isin(NEW)&fs.baseline.eq('lattice_envelope')].groupby(['control','width','method']):
  v=d.iloc[0];rr.append([model,int(width),LABEL[m],num(v.full_speedup),num(v.repair_speedup)])
 put(table(['Model','Width','Candidate','Full vs lattice','Repair vs lattice'],rr))
 put('# Stronger conditional-edge control')
 put('Source review showed that the inherited D* control conditionally propagates g but fully backs up map-notified tails. We therefore added a standard optimized Conditional D* Lite control: edge decreases seed c+g(head), disabled edges trigger backups only when they may support rhs, and identical active queue keys are suppressed. All three unchanged candidates were freshly remeasured alongside it in the same binary, on all184 replay inputs (including the width complement), with three randomized timing repeats and a separate allocation pass. These repeated inputs are not extra independent cases; no seconds are pooled with the primary cohort. Navigation is outside this additional validation.')
 rr=[]
 for _,v in cs.iterrows():rr.append([v.control,v.cohort,LABEL[v.method],num(v.full_speedup),num(v.repair_speedup),f'{int(v.pairs)}/{int(v.configurations)}'])
 put(table(['Model','Cohort','Candidate','Full speedup','Repair speedup','Pairs'],rr))
 put(fig('conditional_control','Fresh joint validation against conditional map-edge updates.'))
 put('The inherited checked_cells field omits endpoint eligibility reads. We therefore ran a separate count-only pass over all184 replay inputs, instrumenting every Grid.free invocation inside replan in generated header copies. All previous logical fields match the unchanged trajectories; count-binary times are discarded. Reported total collision-API probes include endpoint gates and outside-grid probes, excluding direct Grid.blocked input normalization and all reference/verification calls. These are logical API invocations, not hardware load counts. See the accompanying report for totals and ratios against Lattice-Envelope and Conditional D* Lite.')
 put(fig('all_collision_probes','Independent full collision-API probe counts; instrumented times are discarded.'))
 put('# Discussion and limitations')
 put('The primary falsifiable claim is that a shared mesh frontier can amortize repeated negative answers more cheaply than rebuilding or maintaining independent primitive witnesses. Remote edits alone do not establish mesh value: Lattice-Envelope is the decisive representation ablation. The first failure pays construction overhead; reconnection can trigger a conservative exact fallback because R is a superset. Positive-only navigation largely measures the backend and standard suffix rule, not the new negative certificate. The circuit variant must justify both its event work and larger local storage against conditional lattice D* Lite. Full per-map tables, latency percentiles, edit rates, memory maxima and completion failures are retained in the accompanying report.')
 put('This work uses cheap 2D occupancy tests and an unmerged prefix representation. It does not establish superiority over external Lifelong-GLS or Generalized D* implementations, which were not integrated. Incremental reachability, cut-based non-reachability arguments, D* Lite and suffix reuse are prior concepts. The novelty hypothesis is their specific mesh-compressed negative frontier with implicit endpoints; a broader full-text literature review and additional independent roots are required before a priority or top-conference readiness claim.')
 put('# References')
 put((DEST/'related_work.md').read_text().split('\n\n',2)[2])
 paper=render(DEST/'paper.md','\n\n'.join(article),'Repairing Negative Answers on Motion-Primitive Meshes','en-US')
 provenance=dict(status='passed',analysis_sha256=sha(ad/'analysis.json'),frontier_analysis_sha256=sha(frontier_path),conditional_analysis_sha256=sha(conditional_path),probe_analysis_sha256=sha(probe_path),narrative_sha256={p.name:sha(p) for p in [DEST/'design.md',DEST/'related_work.md']},report=report,paper=paper,source_sha256=sha(Path(__file__)))
 (ad/'report_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(json.dumps(provenance))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--frontier-directory',type=Path,default=HERE/'results/frontier');p.add_argument('--conditional-directory',type=Path,default=ROOT/'cpp/mesh_conditional/results/full');args=p.parse_args();main(args.directory,args.frontier_directory,args.conditional_directory)
