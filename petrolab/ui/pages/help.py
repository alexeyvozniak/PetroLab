from __future__ import annotations

import streamlit as st

from petrolab.ui.layout import render_page_header


SECTIONS = [
    ("Импорт и Fe", "FeO FeOt Fe2O3 Fe2O3t Excel CSV units source", "Свяжите XLSX/XLSM для безопасной обратной синхронизации или загрузите рабочую копию. Для каждого листа проверьте минерал, строку заголовков, Sample/Grain/Point/Generation и явно подтвердите смысл FeO/Fe2O3. Неизвестные единицы и duplicate chemistry PetroLab не угадывает."),
    ("Расчёты APFU", "APFU formula end-members derived missing Fe Droop", "В разделе «Расчёты» выберите минерал и метод. APFU/end-members сохраняются отдельным derived-слоем. Censored values, отрицательные концентрации и несовместимые режимы железа не подставляются молча."),
    ("XY и выбор точек", "XY plot graph lasso box recipe configuration outlier", "В XY используйте быстрый plot-first режим или расширенный редактор. Click/box/lasso служат для исследования и рабочих групп. Фильтры и исключения не удаляют анализы из базы."),
    ("REE / spider", "REE spider chondrite primitive mantle normalization trace", "Научные диаграммы находят canonical trace-element колонки и работают только с совместимыми единицами/reference values. Неположительные и non-finite значения не соединяются на логарифмических кривых."),
    ("Изображения", "BSE EDS image photo grain point Generation link", "Загрузите пачку изображений после импорта анализов. Для каждого файла задайте тип, подпись и связь с точками, Sample/Grain/Generation/Point или всем набором. Одна BSE может быть связана с несколькими аналитическими точками."),
    ("Породы", "rock whole-rock TAS Harker isotope Rhodes", "Породы имеют собственный паспорт, валовую химию, изотопию, фотографии и связи с минералогическими datasets. Whole-rock и mineral chemistry остаются разными слоями."),
    ("Синхронизация и безопасность", "sync backup refresh linked source Excel", "Перед обратной записью PetroLab проверяет внешний файл и создаёт резервную копию. Derived-поля, QC и локальные рабочие группы не записываются в Excel как измеренные данные."),
]


def render_help_page() -> None:
    render_page_header(
        "Справка",
        "Найдите термин или задачу — не нужно помнить устройство базы и названия внутренних модулей.",
        eyebrow="Система",
    )
    query = st.text_input("Поиск по справке", placeholder="Например: FeOt, APFU, BSE, синхронизация, REE")
    needle = query.strip().casefold()
    matches = [section for section in SECTIONS if not needle or needle in (" ".join(section)).casefold()]
    if not matches:
        st.info("Ничего не найдено. Попробуйте более короткий термин.")
        return
    for title, _, body in matches:
        with st.expander(title, expanded=bool(needle)):
            st.write(body)

    st.divider()
    st.markdown("### Основной путь")
    st.markdown("**Импорт → База анализов → Расчёты → XY / научные диаграммы → Таблицы / экспорт**")
    st.caption("Исходные данные, расчётные поля и локальная интерпретация остаются раздельными на всём пути.")
