from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


PORT = 8525
PROJECT_NAME = "Viewport project"
VIEWPORTS = [(1440, 900), (1024, 768), (968, 516), (768, 900), (390, 844)]
PAGES = {
    "home": "Главная",
    "data": "Данные",
    "graphs": "Графики",
    "add_data": "Добавить данные",
    "thin": "Шлифы и изображения",
}
PAGE_DESTINATIONS = {
    "home": PROJECT_NAME,
    "data": "Рабочий стол",
    "graphs": "XY-диаграммы",
    "add_data": "Добавить данные",
    "thin": "Работать со шлифом",
}


def _seed_test_data(root: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(root / "data")
    from petrolab.db import add_dataset, create_project, replace_dataset_rows
    from petrolab.storage import ensure_storage

    ensure_storage()
    project_id = create_project(PROJECT_NAME, "Stable UI acceptance fixture")
    dataframe = pd.DataFrame(
        {
            "Sample": ["Sample 1", "Sample 1", "Sample 2"],
            "Point": ["P-1", "P-2", "P-3"],
            "SiO2": [40.0, 41.0, 42.0],
            "Al2O3": [15.0, 14.0, 13.0],
            "TiO2": [2.0, 2.2, 1.8],
            "Generation": ["Core", "Rim", "Core"],
        }
    )
    csv_path = root / "fixture.csv"
    dataframe.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id=project_id,
        name="Viewport data",
        mineral_key="mica",
        source_filename="viewport.xlsx",
        source_sheet="Data",
        source_sha256="viewport-fixture",
        csv_path=str(csv_path),
        row_count=len(dataframe),
    )
    replace_dataset_rows(dataset_id, dataframe, source_rows=[2, 3, 4])


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
    return bool(driver.execute_script(
        """
        return Array.from(document.querySelectorAll('button')).some(el =>
          el.offsetParent !== null && (el.innerText || '').trim() === 'Stop');
        """
    ))


def _signature(driver: webdriver.Chrome) -> tuple[int, int]:
    raw = driver.execute_script(
        """
        const main = document.querySelector('[data-testid="stMain"]');
        if (!main) return [0, 0];
        return [(main.innerText || '').length, Math.round(main.scrollHeight || 0)];
        """
    )
    return int(raw[0]), int(raw[1])


def _wait_for_idle(driver: webdriver.Chrome, timeout: float = 35.0) -> None:
    deadline = time.time() + timeout
    previous = None
    stable = 0
    while time.time() < deadline:
        if _running(driver):
            previous = None
            stable = 0
            time.sleep(0.15)
            continue
        signature = _signature(driver)
        if signature[0] > 0 and signature == previous:
            stable += 1
            if stable >= 3:
                return
        else:
            previous = signature
            stable = 0
        time.sleep(0.2)
    raise AssertionError(f"Streamlit did not become idle: {_signature(driver)}")


def _main_text(driver: webdriver.Chrome) -> str:
    return driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text


def _wait_for_destination(driver: webdriver.Chrome, needle: str, timeout: float = 35.0) -> None:
    """Wait for the requested page itself, not for the previous DOM to look idle."""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            last = _main_text(driver)
        except Exception:
            last = ""
        if needle in last:
            _wait_for_idle(driver)
            if needle in _main_text(driver):
                return
        time.sleep(0.2)
    raise AssertionError(f"Destination {needle!r} did not render. Current main text: {last[:2500]}")


def _visible_sidebar_button(driver: webdriver.Chrome, label: str):
    buttons = [
        button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
        if button.is_displayed() and button.text.strip() == label
    ]
    if buttons:
        return buttons[0]
    for summary in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] [data-testid="stExpander"] summary'):
        if summary.is_displayed() and "Дополнительно" in summary.text:
            driver.execute_script("arguments[0].click();", summary)
            time.sleep(0.2)
            buttons = [
                button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
                if button.is_displayed() and button.text.strip() == label
            ]
            if buttons:
                return buttons[0]
    return None


def _navigate(driver: webdriver.Chrome, label: str, destination: str) -> None:
    button = WebDriverWait(driver, 20).until(lambda d: _visible_sidebar_button(d, label))
    driver.execute_script("arguments[0].click();", button)
    _wait_for_destination(driver, destination)


def _assert_no_exception(driver: webdriver.Chrome, width: int, height: int) -> None:
    exceptions = [
        item.text for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stException"]')
        if item.is_displayed()
    ]
    assert not exceptions, f"Streamlit exception at {width}x{height}: {exceptions}"


def _minimum_plot_width(viewport_width: int) -> float:
    if viewport_width >= 1200:
        return 540.0
    if viewport_width >= 900:
        return 420.0
    if viewport_width >= 700:
        return 330.0
    return 280.0


def _assert_page(driver: webdriver.Chrome, page_name: str, width: int, height: int) -> None:
    text = _main_text(driver)
    _assert_no_exception(driver, width, height)

    if page_name == "home":
        assert "ПетроЛаб" in text or "PetroLab" in text, f"Home identity missing at {width}x{height}"
        assert PROJECT_NAME in text, f"Project context missing at {width}x{height}"
        return

    if page_name == "data":
        assert "Рабочий стол" in text, f"Workspace title missing at {width}x{height}"
        grids = driver.find_elements(
            By.CSS_SELECTOR, '[data-testid="stDataFrame"], [data-testid="stDataEditor"]'
        )
        assert grids, f"Analyses workspace rendered without a table/editor at {width}x{height}"
        return

    if page_name == "graphs":
        assert "XY-диаграммы" in text, f"Graph workspace title missing at {width}x{height}"
        charts = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stPlotlyChart"], .js-plotly-plot')
        charts = [chart for chart in charts if chart.is_displayed()]
        assert charts, f"No visible Plotly graph at {width}x{height}"
        rect = driver.execute_script(
            """
            const el = arguments[0];
            const r = el.getBoundingClientRect();
            return {left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width, height:r.height,
                    visibleHeight: Math.max(0, Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0))};
            """,
            charts[0],
        )
        minimum_width = _minimum_plot_width(width)
        assert float(rect["width"]) >= minimum_width, (
            f"Plot is too narrow for scientific work at {width}x{height}: "
            f"required {minimum_width}, got {rect}"
        )
        minimum_visible = 140 if height <= 600 else 180
        assert float(rect["visibleHeight"]) >= minimum_visible, (
            f"First plot is not sufficiently visible at {width}x{height}: {rect}"
        )
        return

    if page_name == "add_data":
        assert "Добавить данные" in text, f"Add Data title missing at {width}x{height}"
        assert "Что добавить?" in text, f"Add Data mode selector missing at {width}x{height}"
        assert "Excel / CSV" in text, f"Add Data analytical intake missing at {width}x{height}"
        assert "PPL / XPL / BSE / карты" in text, f"Add Data image intake missing at {width}x{height}"
        uploaders = [
            item for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stFileUploader"]')
            if item.is_displayed()
        ]
        assert uploaders, f"Add Data file uploader missing at {width}x{height}"
        return

    if page_name == "thin":
        assert "Работать со шлифом" in text, f"Thin-section workspace title missing at {width}x{height}"
        assert ("Шлиф" in text or "Создайте первый шлиф" in text), (
            f"Thin-section physical context missing at {width}x{height}"
        )
        return


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="petrolab_v0159_acceptance_"))
    process: subprocess.Popen | None = None
    driver: webdriver.Chrome | None = None
    try:
        _seed_test_data(root)
        output = Path(
            os.environ.get("PETROLAB_V0159_ACCEPTANCE_ARTIFACTS", "v0159_acceptance_artifacts")
        )
        output.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PETROLAB_DATA_DIR"] = str(root / "data")
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
        WebDriverWait(driver, 25).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[data-testid="stAppViewContainer"]')
        )
        _wait_for_idle(driver)

        for width, height in VIEWPORTS:
            driver.set_window_size(width, height)
            for page_name, nav_label in PAGES.items():
                _navigate(driver, nav_label, PAGE_DESTINATIONS[page_name])
                _assert_page(driver, page_name, width, height)
                driver.save_screenshot(str(output / f"{page_name}_{width}x{height}.png"))

        print("PetroLab 0.15.9 stable UI acceptance: OK")
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
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
