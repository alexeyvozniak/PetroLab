# PetroLab v0.15.7 — план реализации (UX-консолидация)

Статус: **Preflight завершён**. Документ — рабочий план ветки `hotfix/v0157-ux-workflow`.
Авторитетный бэклог: `docs/UX_AUDIT_V0157_30_PROBLEMS.md`.
Глубокий разбор причин: `docs/UX_AUDIT_2026-08-15.md`.
Правила ветки: `.clinerules/*.md` и `.clinerules/workflows/v0157-ux-consolidation.md`.

## 0. Результаты Preflight

### 0.1 Render-цепочка и стек обёрток

`app.py` → `render_sidebar()` → `ROUTES[route]()`. Реестр `petrolab/ui/pages/__init__.py`
переопределяет один и тот же render многократно в порядке наслоения:

| Порядок | Слой | Что переопределяет | Механизм |
|---|---|---|---|
| 1 | базовые `pages/*.py` | все страницы | прямое объявление |
| 2 | `v0151_wrappers.py` | plots, multi_panel, global_search, thin_section, composite_points | wrapper-функции |
| 3 | `v0151_intake_wrappers.py` | add_data, quick_import | wrapper-функции |
| 4 | `v0152_publication_wrappers.py` | multi_panel (A/B/C метки, composer) | wrapper-функции |
| 5 | `v0153_grain_profile_wrappers.py` | global_search (профиль по зерну) | wrapper-функции |
| 6 | `v0154_rock_workspace_wrappers.py` + `rocks_staging_bridge_v0154.py` | rocks | wrapper-функции |
| 7 | `whole_rock_compare_linked_v0154.py` | whole_rock_compare | wrapper-функции |
| 8 | `workflow_cluster_bridge_v0154.py` | add_data, multi_panel, plots | monkey-patch во время рендера |
| 9 | `v0156_audit_wrappers.py` | analyses, article_tables, batch_edit, formulae, global_search, guided_workflow, home, images, mixed_minerals, multi_panel, object_workspace, slides, thin_section | wrapper-функции + monkey-patch удалений |

Monkey-patch в рантайме:
- `workflow_continuity_v0154.py`: `_plots.load_unified_with_derived`, `_advanced.load_unified_with_derived`, `_advanced.render_advanced_interactive`, `_multi._raw_dataframe`;
- `workflow_cluster_bridge_v0154.py`: `_flow.navigate`, `_flow._batch_token`, `_extensions._batch_token`;
- `v0156_audit_wrappers.py`: `_thin_base.delete_slide_marker`, `_thin_base._delete_field`, `_slides.delete_slide_marker`, `_slides.delete_slide_image`, `_formulae.delete_field`.

**Вывод**: цепочка непредсказуема локально; один и тот же user-концепт рендерится разными реализациями в зависимости от версии-имени ключа. Миграция должна переносить полезное поведение обёрток внутрь одной канонической страницы/компонента, а затем удалять версионные обёртки (правило 20-architecture-safety).

### 0.2 Раздробленные механизмы selection/session-state

- Навигация: `navigate()` пишет только `nav_route` — истории нет (P0 #2).
- Exact ids: `workflow_plot_analysis_ids/context`, `_v0151_plot_exact_analysis_ids`, `_v0151_multi_exact_analysis_ids`, `v0154_chemical_selection_ids`, linked-panel `*_linked_selection_ids`, `grain_profile_analysis_ids`, `_audit_edit_exact_analysis_ids(_datasets/_context)`, `_audit_table_exact_*`, `_audit_batch_exact_*`.
- Dataset/work context: `_petrolab_work_context` (work_context.py) + `sidebar_project`, `workflow_plot_dataset_ids`, `loaded_recipe`, `statistics_scope/datasets`.
- Duplicate key среди фиксированных: `v0154_clear_chemical_selection` в `_advanced_interactive_with_memory` — фиксированный key у reusable-компонента (P0 #1).

### 0.3 Тесты: какие реально исполняют UI

**Реально исполняют** (AppTest/Streamlit): `tests_streamlit.py` — постраничный smoke через `AppTest.from_file("app.py")`, включая double-click подтверждение удаления рецепта.
**Проверяют только текст исходников** (не E2E): `tests_ui_layout.py`, часть `tests_v0156_full_audit.py` (SourceContractTests), `tests_architecture.py`.

**Гэп**: нет ни одного E2E, исполняющего definition of done сценарии (клик в таблице, box/lasso, создание группы, кластер→XY, profile ordered, undo import, Back).

## 1. Цели и не-цели

Цель: закрыть P0/P1 из 30-ауда, убрать стек версионных обёрток из пользовательских сценариев и свести навигацию к 7–9 главным пунктам. **НЕ добавлять** новые user-facing модули и НЕ добавлять новые wrapper/bridge/monkey-patch-слои. Одна сущность — один основной workflow.

## 2. План по фазам (dependency-ordered)

### Phase A — фундамент и P0 (блокирует всё остальное; аудит **1–8, 19, 21, 23, 30**)

**A1. Stop crashes (аудит #1)**
- `_advanced_interactive_with_memory` принимает scoped `key_prefix`; ключи вида `{prefix}_clear_selection`, `{prefix}_select_mode`, ...
- Центральный компонент selection/action-bar принимает `key_prefix` обязательным параметром.
- Запрет fixed-key внутри компонентов, рендерящихся >1 раза; поисковое правило для ключей вида `key="v0154_`.
- Regression: AppTest «выделение → сменить оси → сброс selection» без StreamlitDuplicateElementKey.

**A2. Навигация с Back (аудит #2, #3)**
- Домен `NavigationState`: bounded history ≤20, `push`/`back`/`reset`, элементы (route, context, exact ids). Auto-переходы после импорта не ломают стек.
- `navigate()` остаётся единственным API перехода; кнопка «← Назад» в главном chrome, восстанавливающая route + контекст.
- Home: «Недавние данные» — клик/кнопка открывает соответствующий dataset, Back возвращает на Home.

**A3. Human identity (аудит #5)**
- Централизованный `human_point_label(row)` → `Sample · Grain · Point · Generation`; fallback — короткая строка источника/набора, никогда UUID.
- `_analysis_id` — только в «Технических сведениях»/advanced.

**A4. Единый SelectionContext (аудит #4, #8, #30)**
- Один immutable канал `selection_context`: `analysis_ids` + origin + optional grouping/cluster meta.
- `select(ids)`, `clear()`, `read()` — единственный способ чтения/записи.
- Миграция страниц (plots → multi → stats → profile) без удаления старых механизмов, пока адаптеры/тесты не докажут эквивалентность.

**A5. Общий Selection Panel/action bar (аудит #6, #8, #29)**
- Любой selection → панель: count + identity, compact chemistry (SiO2, TiO2, Al2O3, FeOt, MgO, CaO, Na2O, K2O + trace), полный список по запросу.
- Действия: Создать рабочую группу, Добавить в группу, Убрать из группы, Утвердить как Generation, Открыть в таблице, Открыть на графиках, Профиль (когда применимо), Очистить выбор.
**A6. Table Workspace (аудит #19, часть #30)**
- Одна каноническая таблица: checkbox-выбор строк, identity-колонки закреплены слева, column modes `Основное | Химия | Расчёты | Все`, поиск/фильтр/группа/сортировка.
- Действия: `Показать на графике`, `Профиль`, `Формула`, `Экспорт`, массовое назначение Sample/Grain/Generation/Work Group/QC.
- Химия видна без открытия отдельной технической страницы (аудит #6).

**A7. Навигация 7–9 пунктов (аудит #21, #22, #23)**
- Primary sidebar: Главная, Данные, Графики, Статистика, Шлифы/изображения, Расчёты, Публикация, Поиск, Настройки.
- Убрать «Минералогические модули» и прочие каталоги реализации из primary navigation; специализированные входы — контекстно/advanced.
- Консолидация import: один вход «Добавить данные», остальные (Быстрый импорт, Новые анализы, universal intake) внутри него или удалены.

**A8. Импорт — один wizard (аудит #23, #25, #26)**
- Drop-zone Excel/CSV + изображения -> предпросмотр -> `Разнести по образцам` (`Выбранные -> Sample`, сводка Sample->N) -> commit.
- `Отменить этот импорт` сразу после импорта; в меню набора `Убрать из проекта` / `Удалить из PetroLab` с подтверждением и списком связанных анализов.
### Phase B — научная связность (аудит **9–18, 20, 28, 29**)

**B1. Режимы выделения на графиках (аудит #7)** — segmented `Точка | Прямоугольник | Лассо | Панорама` над интерактивным XY; активный режим виден; подсказка «выделение заменяет/добавляет отбор»; Plotly toolbar -> второстепенные функции.

**B2. Курируемая группировка (аудит #11)** — основной список: PetroLab Generation, исходная Generation, рабочая группа, Sample, Grain, Textural zone, источник/статья, набор, минерал; всё прочее — за `Другой столбец…`; служебные колонки исключены.

**B3. PlotSpec + multi-panel (аудит #14, #15)** — канонический `PlotSpec` (dataset selection, exact ids, X, Y, grouping, source visibility, стили, оси); на обычном XY `+ Добавить ещё диаграмму`; `Добавить этот график в набор панелей` переносит текущий PlotSpec без пересборки первой панели; 2–6 панелей без переезда на другую страницу.

**B4. Научные поля групп (аудит #16)** — дефолтный редактор `Confidence ellipse | Convex hull | KDE` + уровень/покрытие + прозрачность + толщина/тип линии; ручная коррекция add/remove analysis и пересчёт; координаты polygon — только «Дополнительно».

**B5. Статистика -> графики (аудит #12, #13)** — PCA/cluster selection пишет в SelectionContext; `Показать кластеры на графиках` / `Проверить на XY` переносят exact ids + кластер-метки без обязательной записи; сохранение кластера как Work Group — явное действие.

**B6. Профиль по зерну (аудит #17, #18)** — таблица точек с checkbox `В профиль`, identity + химия, фильтры Sample/Point/Generation, редактируемая колонка `Порядок` (ручной или autofill Point/distance/coordinates), preview строго по отмеченным.

**B7. Формула/APFU (аудит #20)** — `Формула / APFU` в action bar и на карточке точки; формула-статус и `Пересчитать`; страница Formulae остаётся расширенным режимом.

### Phase C — импорт и housekeeping (аудит **24, 27, 28**, B3-followup)

**C1. BMP (аудит #24)** — uploader принимает `.bmp`, валидация Pillow, PNG preview без изменения оригинала, оригинал сохраняется как source asset.

**C2. Скрытие pipeline детей (аудит #27)** — внутренние mixed/phase датасеты группируются под import record и скрыты из поиска/recent по умолчанию; техническая структура раскрывается отдельно.

**C3. Work Group scope (аудит #28)** — группы по умолчанию текущего проекта; cross-project reuse только явным действием; одинаковые имена в разных проектах не связываются скрыто.

### Phase D — сведение навигации и удаление обёрток (аудит #21, #22, #23 + 20-architecture-safety)

**D1.** Сократить sidebar до ~7–9 пунктов; убрать «Минералогические модули» и каталоги реализации; один вход «Добавить данные»; удалить конкурирующие import/data routes.

**D2.** Освободиться от версионного слоя обёрток только после переноса поведения: канонический render на route, shared components вместо monkey-patch; затем удалить `v015x_wrappers`, `workflow_*_bridge_v0154` и прочие патч-слои из runtime.

**D3.** Финальная ревизия: поиск новых wrappers/monkey-patch, duplicate keys, видимых ID, state-broadening/loss, мёртвых routes.

## 3. E2E-матрица (требование `.clinerules/30-testing-definition-of-done.md`)

| # | Сценарий | Фаза | Аудиты |
|---|---|---|---|
| 1 | Home → recent dataset → open → Back → Home/context | A | 2, 3 |
| 2 | Table → filter → select rows → chemistry → Work Group → selection stays | A6/B | 4, 8, 19 |
| 3 | XY → switch Точка/Прямоугольник/Лассо → no duplicate key | B | 1, 7 |
| 4 | XY selection → Work Group → X/Y change → same ids | B | 4, 9 |
| 5 | XY → `Добавить этот график в набор панелей` → 2nd panel → 1st intact | B | 14, 15 |
| 6 | Statistics/cluster → `Проверить на XY` → exact ids | B | 12, 13 |
| 7 | multi-panel selection highlighted on another → approve Generation | B | 4, 10 |
| 8 | Профиль → table checkbox order → preview only checked | B | 17, 18 |
| 9 | Excel 2 Sample блока → разнести → commit → counts | A | 23, 25 |
| 10 | BMP upload → preview/link → original BMP retained | A/C | 24 |
| 11 | bad import → undo/remove safely | A | 26 |
| 12 | APFU из selection → открыть без лишних шагов | B | 20 |

## 4. Порядок коммитов и проверок

Каждая фаза: focused unit tests → integration → реальный browser/AppTest сценарий → малый локальный commit на ветке `hotfix/v0157-ux-workflow`. Никаких push/merge без явного разрешения; никаких изменений вне репозитория и удаления пользовательских данных.

## 5. На что не сломать (риски и миграция)

- Существующие SQLite-базы и импортированные наборы остаются читаемыми; миграции — аддитивные.
- `_analysis_id` остаётся immutable идентификатором; меняется только видимая подпись, не идентификация.
- Обёртки удаляются последними, только когда каноническое поведение покрыто тестами.
- Правило научной целостности: ничего не выбрасывается, не скрывается, не мержится без явного действия пользователя; QC/outliers не удаляют источники.