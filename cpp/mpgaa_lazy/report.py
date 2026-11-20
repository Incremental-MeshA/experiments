#!/usr/bin/env python3
"""Write the map-specific research report from validated new measurements."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path
import pandas as pd
from analyze import HERE,ROOT,DEST,NEW,CONTROL,SHORT,LABELS,gm
from run_all import digest
def num(x,d=2):return f'{x:.{d}f}' if pd.notna(x) and math.isfinite(float(x)) else '—'
def cell(x):return str(x).replace('|','/').replace('\n',' ')
def table(headers,rows):return '| '+' | '.join(map(cell,headers))+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(cell(x) for x in r)+' |' for r in rows)
def figure(name,caption):return f'![{caption}](figures/{name}.png){{width=99%}}'
def main(directory):
    ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed'
    assert a['analysis_source_sha256']==digest(HERE/'analyze.py')
    for name,sha in a['tables_sha256'].items():assert digest(ad/name)==sha
    for name,sha in json.loads((ad/'figures.json').read_text()).items():assert digest(ROOT/name)==sha
    manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text())
    metrics=pd.read_csv(ad/'case_metrics.csv');summary=pd.read_csv(ad/'summary.csv');pairs=pd.read_csv(ad/'paired_cases.csv');maps=pd.read_csv(ad/'map_pairs.csv')
    family=pd.read_csv(ad/'family_pairs.csv');work=pd.read_csv(ad/'work.csv');repair=pd.read_csv(ad/'repair_work.csv');latency=pd.read_csv(ad/'latency_summary.csv')
    points=pd.read_csv(ad/'navigation_points.csv');changes=pd.read_csv(ad/'actual_changes.csv');completion=pd.read_csv(ad/'completion.csv')
    out=[];add=out.append
    add('# Результат')
    add(f"Реализованы три новых варианта C++17: **Stamp-Mesh-MPGAA***, **Batch-Mesh-MPGAA*** и **Witness-Mesh-MPGAA***. Выполнено **{a['timed_runs']:,} временных прогонов** и **{a['memory_runs']:,} отдельных прогонов памяти** на **{a['scenarios']} конфигурациях**. Измерено {a['timed_planner_calls']:,} вызовов планировщиков; завершенные ответы проверены с точностью $10^{{-6}}$. Расхождений стоимости — **{a['exact_cost_disagreements']}**, остановок по бюджету — **{a['capped_calls']}**.")
    add('Это исследование конкретных инженерных сочетаний версий карты, пакетного восстановления эвристики и префиксных свидетельств. Их новизна относительно прежнего кода репозитория определяется явно ниже. Литературный приоритет этих сочетаний и превосходство над всеми опубликованными реализациями не установлены. Прежние четыре mesh-MPGAA и исходные контроли сохранены без изменений.')
    rows=[]
    for c in NEW:
        d=metrics[metrics.method.eq(c)];p=pairs[pairs.method.eq(c)&pairs.baseline.eq('best_control')]
        rows.append([SHORT[c],f'{int(d.complete.sum())}/{len(d)}',num(gm(p.episode_speedup)),num(gm(p.online_speedup)),num(gm(p.memory_ratio)),f'{int(p.episode_speedup.ge(1.1).sum())}/{int(p.episode_speedup.notna().sum())}'])
    add(table(['Метод','Завершено','Полное ×','Online ×','Память ×','Выигрыш от 10%'],rows))
    add('Здесь baseline — самый быстрый **по полному эпизоду** завершившийся прежний метод в каждой конфигурации: MPGAA*, LBA* reuse, MD-A*, Boundary-MPGAA*, Selective-Mesh-MPGAA*, Delta-Mesh-MPGAA*, Policy-Mesh-MPGAA* и, на grid8, Octile A* reuse. Это выбранная после измерения описательная огибающая. Ее online-время не обязательно минимально среди online-времен контролей. Отношения — геометрические средние по общим завершенным конфигурациям, разные строки могут иметь разные множества пар. Значение больше 1 выгодно новому методу. В replay корректное доказательство отсутствия пути считается завершением; в навигации требуется достижение цели.')
    if (pairs[pairs.method.isin(NEW)&pairs.baseline.eq('best_control')].episode_speedup.dropna()<1).any():
        add('Универсального превосходства нет: в наборе новые методы проигрывают сильным прежним контролям на части конфигураций. Итоги ниже разделены по модели, нагрузке и карте; преимущество в доставке блокировок или объеме подписок не подменяет полное время.')
    rows=[]
    for control in ['car16','grid8']:
        for c in NEW:
            d=summary[summary.cohort.eq('replay')&summary.control.eq(control)&summary.method.eq(c)&summary.baseline.eq('boundary_mpgaa')].iloc[0]
            rows.append([control,SHORT[c],num(d.episode_speedup),num(d.online_speedup),num(d.memory_ratio),f'{int(d.paired)}/{int(d.configurations)}'])
    add(table(['Replay','Метод','Полное / Boundary','Online / Boundary','Heap / Boundary','Пар'],rows))
    add(figure('episode_speedup','Полное время: медиана трех повторов каждой конфигурации, затем геометрическое среднее отношений. Слева сравнение с Boundary, справа — с самым быстрым завершившимся прежним методом. Значения больше 1 выгодны кандидату.'))
    add('# Постановка и алгоритмы')
    add(r'''Состояние $u=(i,j,\theta)$ — исходное граничное состояние направленного графа примитивов. Цель фиксирована. Дуга $p$ имеет положительную стоимость $c_p$ и исходную упорядоченную трассу клеток. Она допустима, если все проверяемые клетки свободны. Общий mesh — префиксное дерево этих трасс для каждого начального направления, без изменения дуг, затрат или дискретизации. В OPEN остаются только исходные граничные состояния.

Общий поиск использует MPGAA*: допустимую согласованную эвристику $h\geq h_0$, сохраненное продолжение `next` и обучение $h(u)\leftarrow\max(h(u),C-g(u))$ после найденного оптимального пути стоимости $C$. Новые методы меняют обслуживание коллизий и начальных нарушений согласованности. Они не используют weighted A*, приближенный ответ или отсечение по времени ремонта.''')
    add('## Stamp-Mesh-MPGAA*: версии карты вместо обратной доставки блокировок')
    add(r'''Карта делится на плитки $8\times8$. У каждой плитки — номер последнего пакета изменений. У кеша граничного состояния хранятся упакованные флаги всех исходящих примитивов, версия полного вычисления `born` и версия последней успешной проверки `verified`. Ограничивающий прямоугольник всех исходных трасс данного направления вычисляется один раз.

Если состояние уже проверялось в текущем пакете, кеш читается сразу. Иначе читаются версии плиток, пересекающих его прямоугольник. Если все они не новее `born`, прежняя маска точна. Если хотя бы одна новее, все нужные флаги пересчитываются общим обходом префиксного дерева. Изменение внутри прямоугольника, но вне трасс, может вызвать лишнее обновление; пропустить влияющую правку оно не может. Размер плитки 8 зафиксирован до временных измерений, без настройки по результатам.

Блокировки больше не перечисляют обратные смещения примитивов и не разрушают все затронутые кеши заранее. Перед приемом сохраненного MPGAA-продолжения проверяются актуальная допустимость каждой дуги и tight-равенство $h(u)=c_p+h(v)$; результат внутри запроса мемоизируется. Поэтому ленивость не позволяет вернуть поврежденный путь. При освобождениях эвристика ремонтируется полностью до поиска.

**Инвариант версий.** Любая изменившаяся проверяемая клетка дуги лежит в одной из просмотренных плиток. Ее версия больше `born`, поэтому старая маска не читается без пересчета. За границей карты занятость постоянна. Если успешная tight-цепочка ведет в цель, суммирование ее стоимостей дает $h(s)$; допустимость $h$ доказывает оптимальность этой цепочки.

**Ожидаемое преимущество.** После общей нормализации правок доставка блокировок требует только записей версий, не зависит от числа обратных смещений car16 и количества сохраненных состояний. Цена переносится в будущие чтения масок и проверку продолжения. Это условие преимущества, а не гарантия ускорения каждого эпизода.''')
    add('## Batch-Mesh-MPGAA*: два полных способа начать ремонт')
    add(r'''Batch сохраняет Stamp и выбирает направление соединения при релевантных освобождениях. Пусть $O$ — число таких клеток, $G$ — число групп обратных смещений, $H$ — множество состояний с обученным $h$, $D_H=\sum_{u\in H}\deg^+(u)$. Значение $D_H$ поддерживается при обучении без полного обхода $H$ на каждом обновлении.

* **Edit join:** для освобожденных клеток перечисляются $G$ групп смещений; кандидаты «обученное состояние, примитив» объединяются. Проверяется только возможное нарушение $h(u)>c_p+h(v)$, затем актуальная допустимость дуги.
* **State scan:** состояния $H$ сортируются в стабильном порядке и просматриваются все их исходящие дуги. Проверяются все текущие нарушения того же неравенства независимо от того, какая клетка их вызвала.

Выбирается state scan при $D_H<O\,G$, иначе edit join. Это детерминированная модель числа операций без измерения времени и без обучаемого порога. Она не учитывает цену сортировки, выделения памяти и вероятность попадания в кеш, поэтому не гарантирует лучший wall time.

**Полнота ремонта.** При edit join любой вновь открывшийся переход из обученного состояния содержит хотя бы одну освобожденную клетку и попадает в обратную проекцию. State scan непосредственно проверяет все исходящие переходы таких состояний и тоже не теряет ни одного начального нарушения. В обоих случаях найденные снижения $h$ затем полностью распространяются стандартной очередью MPGAA* по допустимым предшественникам. Нельзя ограничиться первыми кандидатами и пропустить эту очередь. Блокировки согласованность не ухудшают; состояния без обученного значения используют согласованную геометрическую оценку $h_0$.''')
    add('## Witness-Mesh-MPGAA*: компактное сечение препятствий')
    add(r'''Witness добавляет к Batch префиксное сечение из первых блокирующих узлов mesh. Потомки такого узла не проверяются. При устаревании маски сначала читаются клетки прежнего сечения. Сохранившийся блокирующий узел повторно запрещает все примитивы своего поддерева; его потомки не обходятся. Если свидетель открылся, соответствующая ветвь вычисляется заново, пока не будет найдена следующая блокировка или разрешенный конец.

**Корректность.** Каждый примитив под сохраненным узлом содержит его клетку. Пока она занята, примитив запрещен при любых правках потомков. Открытие свидетеля обязательно проверяется перед его повторным использованием. Сечение остается префиксно свободным: ни один его узел не является предком другого. Разные узлы сечения закрывают непересекающиеся множества трасс; размер сечения не превышает числа исходящих примитивов.

В отличие от прежнего Delta, здесь нет обратного индекса «клетка → множество состояний и узлов», снятия подписок или плотного массива активности всего дерева для каждого состояния. Witness не доставляет только действительные изменения допустимости заранее: он откладывает работу до чтения маски и может проверить свидетели, которые фактически не затронуты правками. Это иной обмен времени и памяти, а не замена Delta с тождественной работой.''')
    add('## Стоимость и точность сравнения механизмов')
    add(r'''Пусть $R$ — число материализованных масок, $d$ — максимальная исходящая степень, $T$ — число узлов шаблонного дерева, $A$ — число плиток карты. Память новых кешей и версий — $O(Rd+A)$, плюс эвристика, указатели и структуры текущего поиска. У Witness сечение добавляет не более $O(Rd)$. Полное обновление маски требует до $O(T)$ чтений узлов; проверка версии — до числа плиток прямоугольника трасс. Неограниченный рост числа сохраненных состояний возможен; вытеснение кеша в этой работе не реализовано.

Три новых метода имеют общий поисковый код. Относительно старого Boundary изменена также организация раскрытия: ссылка на текущую маску берется один раз перед циклом примитивов. Поэтому общее ускорение Stamp против Boundary нельзя целиком приписывать версиям карты. Абляция `stamp_cell` отделяет размер плитки, Batch против Stamp — выбор начала ремонта, Witness против Batch — сохраненное сечение. `batch_scan` проверяет адаптивный выбор против постоянного state scan. Сравнение новых методов между собой сохраняет организацию поискового цикла.

Вычисления используют `double`, `EPS=1e-9` и ту же схему tie breaking, что прежний поиск. Tight-связи допускают запас `8*EPS`; внешняя проверка стоимости — абсолютный допуск $10^{-6}$. Персистентное хранение непроверенного `next` может сохранить пригодную цепочку после блокировки и последующего открытия, когда прежний Boundary уже удалил указатель. Поэтому равенство числа раскрытий с Boundary не требуется и проверяется отдельно как наблюдение.''')
    add('# Протокол')
    rows=[]
    for cohort,control in metrics[['cohort','control']].drop_duplicates().itertuples(index=False,name=None):
        d=metrics[metrics.cohort.eq(cohort)&metrics.control.eq(control)]
        rows.append([cohort.replace('navigation_','nav / '),control,d['case'].nunique(),d.method.nunique(),int(d.repeats.sum()),len(d)])
    add(table(['Нагрузка','Модель','Конфигураций','Методов','Временных','Память'],rows))
    add('Replay использует все 90 car16 и 96 grid8 сценариев прежнего замороженного набора. car16 включает препятствия на пути и вдали от него, смешанные изменения, раскрытие карты и историю правок; партии до 128 клеток и несколько интервалов изменения. grid8 replay включает случайные карты с плотностями 10/20/30/40%, частичную видимость и разные k/cr. Replay подает всем методам одинаковые старты и изменения, даже если их собственные оптимальные пути имеют разный tie breaking.')
    add('Новая закрытая навигация: динамика на всех 16 картах, два корня и две заранее зафиксированные опорные точки `(k,cr)=(2,5),(32,20)` с **n=k**. Раскрытие полностью неизвестной car16-карты: все шесть карт, два корня, радиусы **8/16/32/64**. Это 64 динамические и 48 неизвестных миссий, а не полный повтор 36 сочетаний k/cr. В неизвестной карте ненаблюденные клетки оптимистично свободны; наблюдения накапливаются по мере движения. Динамика начинается с известной исходной карты, затем агент получает только локальные наблюдения.')
    add('Каждые k исполненных примитивов динамика выбирает из исходных пулов одинаковое число свободных клеток для блокировки и занятых для освобождения. Половина запроса равна округленному `N*cr/200`; она ограничена размером обоих пулов. Текущая клетка агента и цель защищены. В одном пакете новая блокировка не может тут же стать освобождением. Плотность сохраняется. Реальный cr равен `100*actual_changes/(N*phases)` и может быть меньше запрошенного. Динамическая видимость — глубина по графу примитивов, а не квадратный радиус.')
    add('В навигации каждый метод исполняет свой маршрут, получает собственные наблюдения, а защита текущей клетки может изменить реализацию общей случайной фазы. Поэтому совпадают параметры и корни симулятора, но не гарантируются тождественные запросы или миры. Фиксированная цель и одинаковый генератор не превращают это в сравнение на одной траектории. Replay и closed-loop результаты представлены раздельно.')
    add('В каждом задании сначала три последовательных временных повтора с перемешиванием порядка методов, затем отдельный одинарный проход памяти. Одновременно запущен один измеряющий процесс. Предварительные данные в `results/preflight` исключены из основных отношений. Старые секунды не используются. Медиана берется внутри конфигурации; среднее парных ускорений геометрическое. Bootstrap в CSV выполняется по кластерам карт и носит описательный характер: корни, запросы и повторы не являются независимой выборкой новых карт.')
    add(f"Медианный относительный MAD полного времени трех повторов — **{num(100*a['median_relative_mad'])}%**, 95-й процентиль — **{num(100*a['p95_relative_mad'])}%**. Преимущества масштаба этого шума следует оценивать осторожно. Бюджет {manifest['cap']:,} ограничивает раскрытия A*, но не отдельным лимитом всю очередь ремонта эвристики. Остановленные эпизоды сохраняются в данных и не заменяются числом секунд как успешное решение.")
    add('Полное время включает конструктор, нормализацию пакета, изменение внутренней карты, уведомления, весь ремонт h, поиск, обучение, проверку продолжения и построение возвращаемого пути. Online исключает конструктор и первый вызов. Генерация среды, сенсор, точный контрольный поиск, ввод-вывод CSV и компиляция общей модели вынесены за часы планировщика. Общий MeshIndex строится для всех методов; его время сохранено в native JSON завершения. Для однократного запуска холодную подготовку нужно прибавить отдельно.')
    add('Память получена отдельной сборкой с перехватом C++ new/delete: пик запрошенных heap-байтов планировщика и его ответа. Включены копия карты, версии плиток и кеши; общая модель и мир симулятора исключены. Это не RSS, не стек и не общая память приложения. Все результаты, пути и счетчики профилирующей сборки совпали с обычной, а три временных повтора — друг с другом по решениям и работе.')
    add('# Карты и нагрузки')
    add(figure('map_speedup','Картовые ускорения полного эпизода против самого быстрого завершившегося прежнего метода. Числа — геометрические средние; цвет показывает log2 ускорения. На каждом сравнении используются общие завершенные конфигурации.'))
    for cohort,control in metrics[['cohort','control']].drop_duplicates().itertuples(index=False,name=None):
        add('## '+cohort.replace('navigation_','Навигация: ')+' / '+control)
        for baseline in ['boundary_mpgaa','best_control']:
            rows=[];d=maps[maps.cohort.eq(cohort)&maps.control.eq(control)&maps.baseline.eq(baseline)]
            for mp in sorted(d['map'].unique()):
                row=[mp]
                for c in NEW:
                    v=d[d['map'].eq(mp)&d.method.eq(c)].iloc[0]
                    row.append(f'{num(v.episode_speedup)} / {num(v.online_speedup)} ({int(v.paired)}/{int(v.configurations)})')
                rows.append(row)
            add('Baseline: '+('Boundary-MPGAA*' if baseline=='boundary_mpgaa' else 'самый быстрый завершившийся прежний метод')+'. В ячейке: **полное / online (число пар / конфигураций)**.')
            add(table(['Карта','Stamp','Batch','Witness'],rows))
    add('## Семейства replay')
    rows=[]
    for (control,f),d in family[family.baseline.eq('boundary_mpgaa')&family.method.isin(NEW)].groupby(['control','family']):
        row=[control,f]
        for c in NEW:
            v=d[d.method.eq(c)].iloc[0];row.append(f'{num(v.episode_speedup)} / {num(v.online_speedup)}')
        rows.append(row)
    add(table(['Модель','Семейство','Stamp','Batch','Witness'],rows))
    add('## Раскрытие карты: все радиусы')
    add(figure('unknown_radius','Раскрытие неизвестной карты: полное ускорение относительно Boundary, геометрическое среднее двух корней на общих завершенных миссиях. Радиусы 8/16/32/64. Отсутствие пары не считается выигрышем.'))
    radii=pd.read_csv(ad/'radius_pairs.csv');rows=[]
    for (control,mp,radius),d in radii[radii.baseline.eq('boundary_mpgaa')&radii.method.isin(NEW)].groupby(['control','map','radius']):
        row=[mp,int(radius)]
        for c in NEW:
            v=d[d.method.eq(c)].iloc[0];row.append(f'{num(v.episode_speedup)} / {num(v.online_speedup)} ({int(v.paired)})')
        rows.append(row)
    add(table(['Карта','Радиус','Stamp','Batch','Witness'],rows));add('Ячейки: полное / online (пар из двух). Разные радиусы меняют количество раскрытий, полученных препятствий и собственный маршрут; зависимость не обязана быть монотонной.')
    add('## Динамика: опорные точки и фактический cr')
    dynamic=pd.read_csv(ad/'dynamic_pairs.csv');rows=[]
    for (control,mp,k,cr),d in dynamic[dynamic.baseline.eq('best_control')&dynamic.method.isin(NEW)].groupby(['control','map','k','cr']):
        row=[control+'/'+mp,f'{int(k)}/{int(cr)}']
        for c in NEW:
            v=d[d.method.eq(c)].iloc[0];row.append(f'{num(v.episode_speedup)} / {num(v.online_speedup)} ({int(v.paired)})')
        rows.append(row)
    add(table(['Карта','k=n / cr%','Stamp','Batch','Witness'],rows));add('Ячейки: полное / online (пар из двух) против самого быстрого завершившегося прежнего метода.')
    dyn=changes[changes.kind.eq('dynamic')].copy();dyn['k']=dyn['case'].map(lambda x:int(re.search(r'__k(\d+)',x).group(1)))
    rows=[]
    for (control,mp,k,cr),d in dyn.groupby(['control','map','k','requested_cr']):
        active=d[d.phases.gt(0)]
        rows.append([control+'/'+mp,f'{int(k)}/{int(cr)}',f'{num(active.actual_cr.min(),3)}–{num(active.actual_cr.max(),3)}',
                     int(d.clamped_phases.sum()),int(d.phases.eq(0).sum())])
    add(table(['Карта','k=n / cr%','Фактический cr%','Ограниченных фаз','Эпизодов без фазы'],rows))
    add('Диапазон фактического cr охватывает методы и оба корня первого временного повтора. Суммы фаз не являются числом независимых сценариев: одна и та же настройка повторяется у методов. Без фазы cr не определен, а не равен нулю. Полная разметка находится в `actual_changes.csv`.')
    rows=[]
    for c in NEW:
        d=points[points.method.eq(c)]
        full=d.roots.eq(2)&d.paired.eq(2)&d.min_episode_speedup.ge(1.1)
        online=d.roots.eq(2)&d.paired.eq(2)&d.paired_online.eq(2)&d.min_online_speedup.ge(1.1)
        rows.append([SHORT[c],int(full.sum()),int(online.sum()),len(d)])
    add(table(['Метод','Полное от 10% на обоих корнях','Online от 10% на обоих корнях','Точек'],rows))
    add('Требование двух корней — описательный фильтр устойчивости внутри этих карт, а не статистическое доказательство обобщения. Для online требуется положительное измеренное время ремонта у обоих методов на обоих корнях.')
    add('# Механизмы и абляции')
    add(figure('ablations','Replay, одинаковая структура новых планировщиков: tile 8 против клеточных версий; адаптивный ремонт против edit join и forced scan; Witness против Batch без сечения. Ускорение больше 1 выгодно кандидату.'))
    rows=[]
    for control in ['car16','grid8']:
        for c,b,label in [('stamp_mpgaa','stamp_cell','Stamp / cell epochs'),('batch_mpgaa','stamp_mpgaa','Batch / Stamp'),
                          ('batch_mpgaa','batch_scan','Batch / forced scan'),('witness_mpgaa','batch_mpgaa','Witness / Batch')]:
            d=summary[summary.cohort.eq('replay')&summary.control.eq(control)&summary.method.eq(c)&summary.baseline.eq(b)].iloc[0]
            rows.append([control,label,num(d.episode_speedup,3),num(d.online_speedup,3),num(d.memory_ratio,3),int(d.paired)])
    add(table(['Модель','Сравнение','Полное ×','Online ×','Heap ×','Пар'],rows))
    add('Абляции не выбирались по выигравшим картам: все применены ко всем replay-конфигурациям. Различия меньше шума трех повторов не поддерживают сильное утверждение о преимуществе механизма. Forced scan может менять порядок начальных снижений h и последующее дерево поиска; число раскрытий не обязано совпадать с адаптивным вариантом.')
    add(figure('batch_choice','Доля релевантных пакетов освобождений, в которых выбран state scan; числа над столбцами — количество таких пакетов в первом повторе всех нагрузок. У Stamp выбор всегда edit join.'))
    rows=[]
    for control in ['car16','grid8']:
        for c in ['boundary_mpgaa',*NEW,'delta_mpgaa']:
            d=repair[repair.control.eq(control)&repair.method.eq(c)&repair.edit_kind.eq('blocks')]
            rows.append([control,SHORT.get(c,c),int(d.blocks.sum()),int(d.notify_probes.sum()),int(d.checked_cells.sum()),int(d.expansions.sum())])
    add(table(['Replay, только blocks','Метод','Правок','Notify probes','Чтений занятости','Раскрытий'],rows))
    add('Здесь суммируются строго односторонние блокировки первого повтора на одинаковых replay-запросах. Нулевые notify probes у новых вариантов показывают устранение обратной доставки блокировок, но не нулевую работу: остаются нормализация, записи версий, проверка продолжения, чтения плиток и возможный поиск. У Delta notify probes — попадания подписок; у Boundary — группы смещений. Одинаковое число таких событий не означает одинаковую стоимость.')
    rows=[]
    for control in ['car16','grid8']:
        for c in NEW:
            d=work[work.control.eq(control)&work.method.eq(c)]
            rows.append([control,SHORT[c],int(d.stamp_writes.sum()),int(d.tile_reads.sum()),int(d.mask_refreshes.sum()),int(d.cut_checks.sum()),int(d.cut_reuses.sum())])
    add(table(['Модель','Метод','Записей версий','Чтений версий','Обновлений масок','Проверок сечения','Сохраненных узлов'],rows))
    add('Счетчики включают начальный поиск и все выполненные вызовы первого повтора всех нагрузок, включая остановки. Чтения свидетелей уже входят в checked_cells; складывать эти два поля как разные затраты нельзя. Ускорение Witness против Batch, а не одна величина cut_reuses, определяет, окупилось ли сечение.')
    parity=pd.read_csv(ad/'replay_work_parity.csv');add(table(['Модель','Метод','Online replay-строк','Совпал ответ','Совпали раскрытия','Совпал путь'],
        [[r.control,SHORT[r.method],r.rows,r.same_cost,r.same_expansions,r.same_path_hash] for r in parity.itertuples()]))
    add('# Память и задержки')
    add(figure('memory_online','Память отдельного профилирующего прохода и online-время обычной сборки относительно Boundary на общих завершенных конфигурациях. Пик heap больше единицы означает меньшую память кандидата.'))
    rows=[]
    for (cohort,control),d in metrics.groupby(['cohort','control']):
        for c in ['boundary_mpgaa','delta_mpgaa',*NEW]:
            p=d[d.method.eq(c)];v=latency[latency.cohort.eq(cohort)&latency.control.eq(control)&latency.method.eq(c)]
            rows.append([cohort.replace('navigation_','nav / ')+'/'+control,SHORT.get(c,c),num(p.peak_heap_bytes.median()/2**20),num(p.peak_heap_bytes.max()/2**20),
                num(v.p95.iloc[0]*1000,3) if len(v) else '—',num(v.p99.iloc[0]*1000,3) if len(v) else '—'])
    add(table(['Нагрузка','Метод','Heap мед., MiB','Heap макс., MiB','p95, ms','p99, ms'],rows))
    add('p95/p99 описывают объединенные выполненные online-вызовы, кроме capped-вызовов; это не доверительные интервалы. Включены корректные ответы «пути нет», исключены пропущенные после лимита запросы. В навигации методы могут выполнять разное количество запросов на разных состояниях. По картам задержки даны в `latency.csv`.')
    add(figure('change_count_latency','Задержка online replay-вызова в зависимости от числа полученных правок. Первый повтор; медиана в корзине по всем картам модели. Медианы групп с разным составом запросов описательны, не причинный эффект числа правок.'))
    add(figure('paired_distribution','Распределение полных парных ускорений против самого быстрого завершившегося прежнего метода. Каждая конфигурация получает один вес после медианы трех временных повторов; наблюдения вложены в карты.'))
    add('# Полнота и положительные случаи')
    rows=[]
    for (cohort,control,method),d in completion.groupby(['cohort','control','method']):
        if method in NEW+['boundary_mpgaa','lba_reuse','md_astar','octile_reuse']:
            rows.append([cohort.replace('navigation_','nav / '),control,SHORT.get(method,method),f'{int(d.completed.sum())}/{int(d.cases.sum())}'])
    add(table(['Нагрузка','Модель','Метод','Завершено'],rows))
    wins=pd.read_csv(ad/'strong_control_wins.csv');rows=[]
    for (cohort,control,mp,c),d in wins.groupby(['cohort','control','map','method']):
        rows.append([cohort.replace('navigation_','nav / '),control+'/'+mp,SHORT[c],len(d),num(d.episode_speedup.min()),num(d.episode_speedup.max())])
    add(table(['Нагрузка','Карта','Метод','Конфигураций от 10%','Мин. ×','Макс. ×'],rows) if rows else 'Нет завершенных конфигураций с выигрышем полного времени от 10% против выбранной огибающей прежних методов.')
    add('Таблица положительных случаев перечисляет все такие группы, а не только лучший результат. Все отдельные конфигурации с параметрами сохранены в `strong_control_wins.csv`, включая выбранный контроль. Полный набор выигрышей и проигрышей находится в `paired_cases.csv`. Конфигурация с единственным удачным корнем не считается устойчивой победой динамической точки.')
    add('# Проверки, воспроизводимость и качество')
    add(f"Независимый Дейкстра выполнен на **1 296 динамических снимках**: {a['independent_dijkstra_comparisons']:,} сравнений трех вариантов, двух абляций и дополнительного размера плитки, включая восстановление после нулевого бюджета. Он перечисляет исходные примитивы и напрямую читает карту, не использует mesh, кеш или адаптивную эвристику. Аудит h и текущих сертифицированных масок не меняет планировщик. ASan/UBSan прошли те же тесты. Перед официальными измерениями проверены {a['preflight_matched_rows']:,} строк двух harness и их профилирующих сборок. Во всей серии совпало {a['memory_matched_rows']:,} строк решений и работы первого временного повтора с отдельным проходом памяти.")
    add('На каждой большой карте native harness проверяет допустимость возвращенного пути и стоимость: replay — с замороженным точным ответом, навигация — с отдельным исходным LBA*. Времена проверки исключены из часов. Это проверка данной модели; малые независимые тесты уменьшают риск общей ошибки mesh и контрольного поиска, но не доказывают отсутствие всех ошибок во всех возможных моделях.')
    add('Сильные стороны работы: полные исходники C++17; новые и прежние методы измерены в одном процессе с одинаковыми моделями; замороженный план до таймингов; отдельная память; проверки оптимальности, воспроизводимых решений и счетчиков; разделение карт, радиусов, нагрузок и неуспехов; явные абляции; сохранение сырых данных и команд.')
    add('Практические ограничения: один набор направленных примитивов car16 и один grid8, дешевые 2D-чтения занятости, фиксированная цель, два экспериментальных корня на карте и только две динамические опорные точки. В серии повторно измерена выбранная группа сильных прежних методов, а не все 15 исторических реализаций. Измерения на одной машине не устанавливают преимущество на иной архитектуре или в робототехнической проверке контура. Адаптивная оценка стоимости Batch не учитывает все накладные расходы. Память кешей не ограничена вытеснением.')
    add('Качество оценивается по фактическим результатам: гарантия оптимальности опирается на инварианты и независимые проверки; инженерная воспроизводимость проверяется отдельным валидатором; область ускорения определяется картовыми парными таблицами. Для заявления конференционной новизны нужны отдельный обзор литературы по lazy collision caches и incremental search, больше независимых карт и реализаций соперников. Здесь такого приоритета или готовности к принятию на ведущую конференцию не заявляется.')
    add('Ориентиры протокола: Hernández, Asín & Baier, MPGAA*, AAAI 2015, DOI 10.1609/aaai.v29i1.9355; Koenig & Likhachev, D* Lite, AAAI 2002; Sturtevant, Moving AI benchmarks. Источники официальных карт и хеши сохранены в [реестре карт](../../cpp/experiments/maps/SOURCES.json). Это адаптация опубликованных постановок, без воспроизведения чужих опубликованных секунд.')
    add('## Команды и файлы')
    add('''```bash
make -C cpp/mpgaa_lazy -j2 all
make -C cpp/mpgaa_lazy test
python cpp/mpgaa_lazy/run_all.py \\
  --output cpp/mpgaa_lazy/results/reproduction
python cpp/mpgaa_lazy/analyze.py
python cpp/mpgaa_lazy/report.py
python cpp/mpgaa_lazy/validate_artifact.py
```

Последние три команды проверяют сохраненные основные данные, не повторяя временные прогоны. Для анализа нового каталога указывайте `--directory`. Зависимости Python те же, что в `cpp/mpgaa_mesh/requirements.txt`; PDF использует Pandoc, XeLaTeX, Noto Serif и Noto Sans Mono.''')
    add(table(['Артефакт','Содержимое'],[
        ['algorithms.hpp / factory.hpp','Алгоритмы, абляции и выбор методов'],['frozen/manifest.json','План и хеши входов и исходников'],
        ['results/full/experiment.json','Команды, бинарники и завершения заданий'],['analysis/case_metrics.csv','Медианы времени, память, статусы'],
        ['analysis/paired_cases.csv','Все парные отношения и выбранный baseline'],['analysis/map_pairs.csv','Раздельные результаты карт'],
        ['analysis/actual_changes.csv','Фактические cr, ограниченные и нулевые фазы'],['analysis/repair_work.csv','Работа по типу правок'],
        ['analysis/navigation_points.csv','Два корня для каждой динамической точки'],['analysis/latency.csv','Картовые p50/p95/p99'],
        ['analysis.ipynb','Выполненный анализ сохраненных таблиц']]))
    header='''---
title: "Stamp, Batch и Witness: ленивый ремонт mesh MPGAA*"
author: "Исследовательский артефакт C++17"
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
    body='\n\n'.join(out)+'\n';parts=re.split(r'(```[\s\S]*?```|`[^`\n]*`)',body)
    body=''.join(p if i%2 else re.sub(r'(?<=\w)\*(?!\*)',r'\\*',p) for i,p in enumerate(parts))
    # Keep emphasis markers separate from escaped algorithm-name asterisks.
    body=body.replace('MPGAA***','MPGAA\\***')
    DEST.mkdir(parents=True,exist_ok=True);markdown=DEST/'report.md';markdown.write_text(header+body)
    command=['pandoc',str(markdown),'-o',str(DEST/'report.pdf'),'--pdf-engine=xelatex','--resource-path='+str(DEST),
        '--include-in-header='+str(ROOT/'docs/experiments/layout.tex'),'--lua-filter='+str(ROOT/'cpp/mpgaa_mesh/vector_images.lua')]
    subprocess.run(command,cwd=ROOT,check=True)
    provenance=dict(status='passed',analysis_sha256=digest(ad/'analysis.json'),markdown_sha256=digest(markdown),pdf_sha256=digest(DEST/'report.pdf'),
        command=command,source_sha256=digest(Path(__file__)),figures_manifest_sha256=digest(ad/'figures.json'),layout_sha256=digest(ROOT/'docs/experiments/layout.tex'),
        vector_filter_sha256=digest(ROOT/'cpp/mpgaa_mesh/vector_images.lua'))
    (ad/'report_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(DEST/'report.pdf')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
