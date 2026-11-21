# Связанные работы и границы приоритета

* **MeshA\*** — Agranovskiy and Yakovlev, *MeshA\*: Efficient Path Planning With
  Motion Primitives*, AAAI 2026, [DOI](https://doi.org/10.1609/aaai.v40i43.41004).
  Отсюда происходит конфигурационное представление. Здесь применяется точный
  замороженный автомат репозитория; новые OPEN/g/h/policy относятся ко всем его
  состояниям, а не только к primitive-границам.
* **MPGAA\*** — Hernández, Asín and Baier, *Reusing Previously Found A\* Paths
  for Fast Goal-Directed Navigation in Dynamic Terrain*, AAAI 2015,
  [DOI](https://doi.org/10.1609/aaai.v29i1.9355). Обучение эвристики, ремонт при
  понижениях стоимости и присоединение к сохранённой политике являются базовыми
  известными компонентами. Обычный перенос на mesh включён отдельным контролем.
* **D\* Lite** — Koenig and Likhachev, AAAI 2002;
  **Lifelong Planning A\*** — Koenig, Likhachev and Furcy, Artificial Intelligence
  2004, [DOI](https://doi.org/10.1016/j.artint.2003.12.001).
  Локальная релаксация, условия поддержки и инкрементальное восстановление
  графовых меток давно известны; положительное перевзвешивание C-Mesh также
  уже присутствует в предыдущей ветке репозитория.
* **Fringe Search** — Yngvi Björnsson, Markus Enzenberger, Robert C. Holte and
  Jonathan Schaeffer, *Fringe Search: Beating A\* at Pathfinding on Game Maps*,
  CIG 2005, [public paper](http://papersdb.cs.ualberta.ca/~papersdb/uploaded_files/424/paper_cig2005.pdf),
  [metadata](https://openalex.org/W4260767). Обход дорогостоящих операций OPEN
  имеет предшественников. Наше прямое продолжение — узкий механизм, сохраняющий
  точный порядок `(f,-g,seq)`, а не новая общая идея fringe-поиска.
* **Partial Expansion A\*** — Takayuki Yoshizumi, Teruhisa Miura and Toru Ishida,
  *A\* with Partial Expansion for Large Branching Factor Problems*, AAAI 2000,
  [paper](https://www.aaai.org/Papers/AAAI/2000/AAAI00-142.pdf),
  [metadata](https://openalex.org/W1603934459). В Cascade не удаляются внутренние
  состояния и не подменяется поиск на primitive-границах. Но сокращение
  генерации/очередей нельзя заявлять без учёта этого направления.
* **Lifelong-GLS / Generalized D\*** — Lim, Srinivasa and Tsiotras, IROS 2022,
  [DOI](https://doi.org/10.1109/IROS47612.2022.9981389); IJRR 2024,
  [DOI](https://doi.org/10.1177/02783649241227869). Это близкие направления
  инкрементального ленивого планирования. В этой работе карта применяется
  немедленно, а подписки фильтруют ремонт learned h. Официальные внешние
  реализации не интегрированы.

Новая проверяемая гипотеза — активная клеточная граница нарушений согласованности
learned h и каскады по исходным нулевым рёбрам полного mesh-MPGAA*. Watch-индексы,
адаптивный поиск, кеширование путей и потенциалы сами по себе не новые. Метаданные
основных работ проверены в предыдущем исследовании; для Fringe/Partial Expansion
сохранён отдельный OpenAlex-поиск в literature_search.json. Это ограниченный обзор,
не доказательство первого в литературе сочетания и не замена чтению всех близких
полных текстов перед подачей.
