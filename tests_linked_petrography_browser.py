from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


PORT = 8525
ROOT = Path(tempfile.mkdtemp(prefix="petrolab_linked_browser_"))
os.environ["PETROLAB_DATA_DIR"] = str(ROOT / "data")

from petrolab.db import add_dataset, create_project, load_dataset_dataframe, replace_dataset_rows
from petrolab.measurement_registry import create_entity
from petrolab.slides import create_slide_marker, register_managed_slide_image
from petrolab.storage import ensure_storage


def _dataset(project_id: int, *, name: str, source: str, frame: pd.DataFrame) -> tuple[int, list[str]]:
    csv_path = ROOT / f"{source}.csv"
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id,
        name,
        "mica",
        f"{source}.xlsx",
        "Sheet1",
        f"{source}-sha",
        str(csv_path),
        len(frame),
    )
    replace_dataset_rows(dataset_id, frame, source_rows=list(range(2, len(frame) + 2)))
    loaded = load_dataset_dataframe(dataset_id, include_meta=True)
    return dataset_id, loaded["_analysis_id"].astype(str).tolist()


def _seed() -> tuple[int, tuple[str, str]]:
    ensure_storage()
    project_id = create_project("Linked browser project", "Golden graph-thin-section CI path")
    _, epma_ids = _dataset(
        project_id,
        name="KIV EPMA",
        source="browser_epma",
        frame=pd.DataFrame(
            {
                "Sample": ["KIV-2", "KIV-2"],
                "Point": ["P-1-EPMA", "P-2-EPMA"],
                "SiO2": [40.1, 39.8],
                "Al2O3": [13.5, 14.1],
                "TiO2": [2.1, 1.7],
            }
        ),
    )
    _, la_ids = _dataset(
        project_id,
        name="KIV LA-ICP-MS",
        source="browser_la",
        frame=pd.DataFrame(
            {
                "Sample": ["KIV-2"],
                "Point": ["P-1-LA"],
                "SiO2": [40.2],
                "Al2O3": [13.7],
                "TiO2": [2.2],
                "Rb [µg/g]": [520.0],
            }
        ),
    )
    p1_ids = (epma_ids[0], la_ids[0])

    section_id = create_entity(project_id, kind="thin_section", name="KIV-2-1")
    buffer = BytesIO()
    Image.new("RGB", (900, 600), "white").save(buffer, format="PNG")
    image = register_managed_slide_image(
        project_id,
        filename="KIV-2-1_BSE.png",
        data=buffer.getvalue(),
        title="KIV-2-1 BSE",
        image_type="BSE",
        thin_section_id=section_id,
    )
    create_slide_marker(
        project_id,
        slide_image_id=image.id,
        x_norm=0.42,
        y_norm=0.57,
        label="P-1",
        analysis_ids=p1_ids,
    )
    create_slide_marker(
        project_id,
        slide_image_id=image.id,
        x_norm=0.75,
        y_norm=0.30,
        label="P-2",
        analysis_ids=(epma_ids[1],),
    )
    return project_id, p1_ids


def _wait_for_server(url: str, timeout: float = 35.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.35)
    raise RuntimeError(f"Streamlit did not start at {url}: {last_error}")


def _running(driver: webdriver.Chrome) -> bool:
    return bool(
        driver.execute_script(
            """
            return Array.from(document.querySelectorAll('button')).some(el =>
              el.offsetParent !== null && (el.innerText || '').trim() === 'Stop');
            """
        )
    )


def _main_signature(driver: webdriver.Chrome) -> tuple[int, int]:
    value = driver.execute_script(
        """
        const main = document.querySelector('[data-testid="stMain"]');
        if (!main) return [0, 0];
        return [(main.innerText || '').length, Math.round(main.scrollHeight || 0)];
        """
    )
    return int(value[0]), int(value[1])


def _wait_for_idle(driver: webdriver.Chrome, timeout: float = 35.0) -> None:
    deadline = time.time() + timeout
    previous: tuple[int, int] | None = None
    stable = 0
    while time.time() < deadline:
        if _running(driver):
            previous = None
            stable = 0
            time.sleep(0.15)
            continue
        signature = _main_signature(driver)
        if signature[0] <= 0:
            stable = 0
        elif signature == previous:
            stable += 1
            if stable >= 3:
                return
        else:
            previous = signature
            stable = 0
        time.sleep(0.2)
    raise AssertionError(f"Streamlit did not become idle: {_main_signature(driver)}")


def _visible_button(driver: webdriver.Chrome, label: str):
    candidates = [
        button for button in driver.find_elements(By.TAG_NAME, "button")
        if button.is_displayed() and button.text.strip() == label
    ]
    return candidates[0] if candidates else None


def _visible_tab(driver: webdriver.Chrome, label: str):
    candidates = [
        tab for tab in driver.find_elements(By.CSS_SELECTOR, '[role="tab"], [data-baseweb="tab"]')
        if tab.is_displayed() and tab.text.strip() == label
    ]
    return candidates[0] if candidates else None


def _click_button(driver: webdriver.Chrome, label: str) -> None:
    button = WebDriverWait(driver, 20).until(lambda d: _visible_button(d, label))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", button)
    _wait_for_idle(driver)


def _click_tab(driver: webdriver.Chrome, label: str) -> None:
    tab = WebDriverWait(driver, 20).until(lambda d: _visible_tab(d, label))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", tab)
    _wait_for_idle(driver)


def _navigate_sidebar(driver: webdriver.Chrome, label: str) -> None:
    candidates = [
        button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
        if button.is_displayed() and button.text.strip() == label
    ]
    if not candidates:
        for summary in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] [data-testid="stExpander"] summary'):
            if summary.is_displayed() and "Дополнительно" in summary.text:
                driver.execute_script("arguments[0].click();", summary)
                time.sleep(0.2)
                candidates = [
                    button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
                    if button.is_displayed() and button.text.strip() == label
                ]
                if candidates:
                    break
    assert candidates, f"Sidebar route not found: {label}"
    driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", candidates[0])
    _wait_for_idle(driver)


def _main_text(driver: webdriver.Chrome) -> str:
    return driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text


def _save(driver: webdriver.Chrome, name: str) -> None:
    output = Path("linked_petrography_browser_artifacts")
    output.mkdir(exist_ok=True)
    driver.save_screenshot(str(output / name))


def _assert_no_exception(driver: webdriver.Chrome) -> None:
    exceptions = [
        element.text for element in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stException"]')
        if element.is_displayed()
    ]
    assert not exceptions, exceptions


def main() -> None:
    _seed()
    process: subprocess.Popen | None = None
    driver: webdriver.Chrome | None = None
    try:
        env = os.environ.copy()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.headless=true",
                f"--server.port={PORT}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        url = f"http://127.0.0.1:{PORT}"
        _wait_for_server(url)
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,900")
        try:
            driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise RuntimeError(f"Could not start Chrome: {exc}") from exc
        driver.get(url)
        WebDriverWait(driver, 25).until(lambda d: d.find_elements(By.CSS_SELECTOR, '[data-testid="stAppViewContainer"]'))
        _wait_for_idle(driver)

        _navigate_sidebar(driver, "Шлифы и изображения")
        _save(driver, "00_thin_initial.png")
        text = _main_text(driver)
        assert "Работать со шлифом" in text, text[:2000]
        # Selected values live inside Streamlit select inputs and are not guaranteed to
        # appear in main.innerText. These visible badges prove the seeded physical
        # section/image/markers are the active workspace instead of a blank project.
        for expected in ("снимков · 1", "точек · 2", "связанных анализов · 3"):
            assert expected in text, f"Missing {expected!r}: {text[:2500]}"
        _assert_no_exception(driver)

        _click_tab(driver, "Связи")
        text = _main_text(driver)
        assert "точек · 2" in text
        assert "связанных анализов · 3" in text
        _save(driver, "01_thin_links.png")

        _click_button(driver, "Открыть в графиках")
        text = _main_text(driver)
        assert "XY-диаграммы" in text
        assert "Выбрано: 2" in text, text[:2500]
        assert "На шлифе" in text
        charts = [
            chart for chart in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stPlotlyChart"], .js-plotly-plot')
            if chart.is_displayed()
        ]
        assert charts, "Smart Start did not render a real Plotly chart"
        _assert_no_exception(driver)
        _save(driver, "02_graph_selection_2.png")

        _click_button(driver, "На шлифе")
        text = _main_text(driver)
        assert "Работать со шлифом" in text
        assert "Selection · 2" in text, text[:2500]
        assert "на этом снимке · 1 точ." in text
        assert "Selection здесь · 1" in text
        _assert_no_exception(driver)
        _save(driver, "03_back_on_exact_bse.png")

        print("PetroLab browser golden path graph <-> BSE: OK")
    finally:
        if driver is not None:
            driver.quit()
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
