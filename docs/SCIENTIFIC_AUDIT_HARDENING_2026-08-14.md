# Scientific audit hardening — 2026-08-14

Этот пакет закрывает научные замечания повторного аудита текущего PetroLab, **кроме Rhodes/Kd и whole-rock Mg# workflow**: эти два блока сознательно не менялись по решению пользователя.

## 1. Compositional statistics

Для PCA и кластеризации добавлен CoDA/CLR режим по log-ratio геометрии Aitchison. В UI он является предпочтительным режимом для compositional geochemical data; старый StandardScaler/RobustScaler сохранён как явно exploratory Euclidean mode.

PetroLab не подставляет произвольный pseudocount. В CLR строки с пропуском, нулём или отрицательным выбранным компонентом исключаются и это количество показывается пользователю. Detection-limit-aware replacement должен выполняться только отдельной процедурой, где известна семантика цензурирования.

CLR/ILR дополнительно защищён от смешивания несопоставимых шкал. Один log-ratio анализ может использовать только одну распознанную compositional domain: oxides в wt.%, trace-element concentrations в µg/g либо apfu. PetroLab блокирует смеси вроде `SiO2 wt.% + La µg/g`, а также Mg#, Cr#, scores и колонки с неизвестной единицей. В UI тип композиции выбирается явно, поэтому пользователь не получает ошибочный mixed-unit default.

Для анализа связей добавлена Aitchison log-ratio variation matrix `var[ln(x_i/x_j)]`. Обычные Pearson/Spearman/Kendall остаются доступны в Euclidean exploratory mode.

Основной источник: J. Aitchison (1986), *The Statistical Analysis of Compositional Data*, DOI `10.1007/978-94-009-4109-0`.

## 2. TAS

TAS по умолчанию строится по безводным major oxides, перенормированным к 100 wt.%. LOI/H2O/CO2 и другие volatile fields не входят в сумму. Iron semantics учитываются без двойного счёта: явный FeOt или Fe2O3t имеет приоритет над одновременно присутствующими split FeO+Fe2O3 при вычислении analytical major total.

Неполная таблица больше не может быть искусственно растянута до 100%. Для volatile-free TAS normalization требуются SiO2, Al2O3, MgO, CaO, Na2O, K2O и одна валидная форма железа; исходный major total должен находиться в QC-интервале 70–105 wt.%. Если gate не пройден, нормированные TAS coordinates остаются пустыми и сохраняется человекочитаемый `TAS_normalization_QC`. Это QC-ограничение, а не граница классификации пород.

Исходная whole-rock chemistry не переписывается: нормировка существует только в plotting/classification dataframe и сохраняет `TAS_original_major_total`, `TAS_normalization_factor`, `TAS_major_suite_complete` и `TAS_normalization_QC`.

Границы диаграммы не изменены: Le Bas et al. (1986) / IUGS TAS.

## 3. Independent formula benchmarks

Добавлен `tests_scientific_hardening.py` с идеальными независимыми стехиометрическими составами:

- forsterite Mg2SiO4;
- diopside CaMgSi2O6;
- pyrope Mg3Al2Si3O12;
- albite NaAlSi3O8;
- phlogopite KMg3AlSi3O10(OH)2 на 11 O-equivalent EPMA basis.

Весовые составы теста строятся из собственного набора molar masses, не импортированного из production formula engine. Проверяются apfu и ключевые end-member proportions.

## 4. REE / spider reference constants

CI chondrite McDonough & Sun (1995) и primitive mantle Sun & McDonough (1989), уже используемые PetroLab, теперь зафиксированы exact regression test. Случайное изменение одного reference value будет ломать CI.

McDonough & Sun (1995): DOI `10.1016/0009-2541(94)00140-4`.

## 5. Phase suggestion rules

Эвристический mixed-mineral classifier остаётся только suggestion layer и не превращается в IMA classifier. Добавлена обязательная версия ruleset `2026.08.1`, которая попадает в dataframe вместе с каждым предложением. Изменение threshold/scoring semantics требует новой версии.

Regression benchmark проверяет высокоспецифичные canonical cases для apatite, zircon, perovskite, olivine и mica. Ambiguous/unresolved behaviour остаётся допустимым и предпочтительным для перекрывающихся фаз.

## 6. Future thermobarometry contract

До появления новых thermometer/barometer equations введён минимальный научный контракт `ThermobarometerMethod`. Калибровку нельзя считать готовой к регистрации без:

- versioned equation;
- citation и DOI первичной calibration paper;
- required components;
- calibration range;
- reported uncertainty;
- explicit equilibrium test;
- assumptions.

Это предотвращает появление в PetroLab «температуры одной кнопкой» без области применимости и provenance.

## 7. Regression gate

`tests_scientific_hardening.py` включён отдельным шагом Windows GitHub Actions и в compile gate. Дополнительно тестируются запрет mixed-unit CLR и отказ TAS нормировать неполную major suite.

## Осознанно не изменено

По решению пользователя в этих научных правках не меняются:

- pairing logic Rhodes / olivine-liquid screening;
- handling/assumptions whole-rock Mg# и Fe3+/ΣFe в Rhodes workflow.
