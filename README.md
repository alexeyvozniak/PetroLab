# ПетроЛаб v0.10.0

Локальная русскоязычная рабочая среда для петрологии, минералогии и геохимии. Исходные Excel, производные минералогические расчёты, локальная интерпретация, изображения и валовые составы пород хранятся как связанные, но разные слои данных.

## Что умеет

- Единая SQLite-база минералогических анализов из разных Excel/листов с сохранением происхождения каждой точки.
- Безопасная двусторонняя синхронизация XLSX/XLSM с backup и журналом изменений.
- Нормализация названий оксидов, trace elements и единиц; неоднозначные FeO/FeOt/Fe2O3/Fe2O3t не смешиваются молча.
- Минералогические формулы/APFU/end-members как отдельный derived-слой с provenance и stale detection.
- Интерактивные XY и ternary диаграммы: click/box/lasso, рабочие группы, изображения, ручные/MAD/IQR фильтры.
- Source-aware классификационные схемы: Morimoto pyroxene, Ab–An–Or, garnet projections, Grütter G10 diagnostics, Wyatt ilmenite reference и другие kimberlite/lamprophyre presets.
- REE и multi-element spider diagrams с CI-chondrite / primitive-mantle нормировкой только для концентраций с известной единицей.
- Гистограммы, boxplot, описательная статистика, корреляции, PCA, K-means и иерархическая кластеризация.
- Журнальные presets рисунков и таблиц (Lithos, Geodynamics & Tectonophysics, ДАН, Elsevier/Supplementary), гармоничные presets маркеров и редактируемые подписи/сетка/поля.
- Отдельная база пород: паспорт, массив/местоположение, описание, возраст и метод, валовая химия, изотопия, лаборатория/методика, фотографии и связи минерал–порода.
- Whole-rock TAS, Harker/binary, REE/spider, isotope XY и Rhodes-style olivine–rock equilibrium screening/Kd.
- Встроенные «Что нового», инструкция, настройки и responsive UI.

## Запуск Windows

1. Скачайте или клонируйте репозиторий в постоянную папку.
2. Запустите `START_PETROLAB.bat`.
3. При первом запуске автоматически создаётся `.venv` и устанавливаются зависимости.
4. Если запуск не удался, используйте `DIAGNOSE_PETROLAB.bat`.

## Основной рабочий путь

```text
Источники/породы
      ↓
Единая база
      ↓
Расчёты и derived-поля
      ↓
XY / ternary / scientific plots / statistics
      ↓
Изображения + mineral–rock links
      ↓
Publication presets → PNG/SVG/XLSX
```

## Принципы безопасности

- Реальные XLSX/CSV, SQLite и изображения исключены из Git.
- Фильтр, кластер или рабочая группа не удаляют исходный анализ.
- Derived-параметры не записываются в исходный Excel как будто они измерены.
- Нормированный REE/spider не принимает bare trace-element колонку без подтверждённой единицы за ppm.
- Литературные поля добавляются только вместе с источником и тестируемой геометрией; приблизительные поля «по картинке» не считаются научной классификацией.
- Whole-rock состав в mineral–rock модуле явно обозначается как proxy расплава там, где это методически важно.

GitHub Actions на Windows проверяет BAT/CRLF, архитектурные границы, минералогические формулы, импорт/синхронизацию, classification overlays, whole-rock/statistics/publication modules, responsive UI и открытие всех страниц Streamlit через AppTest.
