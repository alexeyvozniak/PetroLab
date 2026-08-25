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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


PORT = 8525
PROJECT_NAME = "Viewport project"
VIEWPORTS = [(1440, 900), (1024, 768), (968, 516), (768, 900), (390, 844)]
PAGES = {
    "home": ("Обзор", PROJECT_NAME),
    "data": ("Образцы", "Образцы"),
    "linked": ("Построение", "Предварительный отбор"),
    "search": ("Поиск", "Поиск"),
    "add_data": ("Добавить", "Проверка импорта"),
    "thin": ("Шлифы", "Шлифы"),
    "statistics": ("Статистика", "Пошаговый анализ"),
    "publication": ("Экспорт", "Экспорт и публикация"),
}


def _seed_test_data(root: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(root / "data")
    from petrolab.db import add_dataset, create_project, replace_dataset_rows
    from petrolab.storage import ensure_storage

    ensure_storage()
    project_id = create_project(PROJECT_NAME, "Product Design acceptance fixture")
    dataframe = pd.DataFrame(
        {
            "Sample": ["Sample 1", "Sample 1", "Sample 2", "Sample 2", "Sample 3", "Sample 3"],
            "Point": ["P-1", "P-2", "P-3", "P-4", "P-5", "P-6"],
            "Mineral": ["Phlogopite"] * 6,
            "Method": ["EPMA", "LA-ICP-MS", "EPMA", "SIMS", "EPMA", "LA-ICP-MS"],
            "Generation": ["Core", "Rim", "Core", "Rim", "Inclusion", "Core"],
            "SiO2": [40.0, 43.5, 48.0, 55.0, 62.5, 69.0],
            "Al2O3": [15.0, 14.0, 13.0, 12.0, 11.0, 10.5],
            "TiO2": [2.8, 2.4, 2.0, 1.6, 1.2, 0.8],
            "MgO": [8.0, 10.0, 12.5, 15.0, 18.0, 20.0],
            "K2O": [1.0, 1.5, 2.0, 2.8, 3.6, 4.4],
            "F": [0.70, 0.65, 0.60, 0.55, 0.48, 0.40],
            "Cl": [0.10, 0.12, 0.14, 0.16, 0.18, 0.20],
            "OH": [0.20, 0.23, 0.26, 0.29, 0.34, 0.40],
            "Nb": [5, 8, 12, 20, 35, 60],
            "Ta": [0.4, 0.7, 1.1, 1.8, 3.1, 5.4],
            "Rb": [20, 35, 55, 90, 150, 240],
            "Sr": [900, 650, 420, 260, 150, 90],
            "La": [100, 90, 80, 72, 65, 58],
            "Ce": [90, 82, 74, 66, 60, 54],
            "Pr": [75, 70, 64, 58, 53, 48],
            "Nd": [62, 58, 53, 49, 45, 41],
            "Sm": [35, 32, 29, 27, 24, 22],
            "Eu": [12, 11, 10, 9, 8, 7],
            "Gd": [28, 26, 24, 22, 20, 18],
            "Tb": [22, 20, 18, 17, 15, 14],
            "Dy": [18, 17, 15, 14, 13, 12],
            "Ho": [14, 13, 12, 11, 10, 9],
            "Er": [11, 10, 9, 8, 7.5, 7],
            "Tm": [8, 7.5, 7, 6.5, 6, 5.5],
            "Yb": [6.5, 6, 5.5, 5, 4.5, 4],
            "Lu": [5.0, 4.6, 4.2, 3.8, 3.4, 3.0],
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
    replace_dataset_rows(dataset_id, dataframe, source_rows=list(range(2, 2 + len(dataframe))))


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
        if summary.is_displayed() and "Ещё" in summary.text:
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
    exceptions = [item.text for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stException"]') if item.is_displayed()]
    assert not exceptions, f"Streamlit exception at {width}x{height}: {exceptions}"


def _prepare_search(driver: webdriver.Chrome) -> None:
    fields = [
        item for item in driver.find_elements(By.CSS_SELECTOR, 'input')
        if item.is_displayed() and "апатит" in (item.get_attribute("placeholder") or "").lower()
    ]
    if not fields:
        return
    fields[0].clear()
    fields[0].send_keys("Sample 1", Keys.ENTER)
    _wait_for_destination(driver, "Результаты")


def _assert_page(driver: webdriver.Chrome, page_name: str, width: int, height: int) -> None:
    text = _main_text(driver)
    _assert_no_exception(driver, width, height)

    if page_name == "home":
        assert PROJECT_NAME in text
    elif page_name == "data":
        assert "Образцы" in text
    elif page_name == "linked":
        assert "Предварительный отбор" in text and "Кодировка" in text
        charts = [item for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stPlotlyChart"], .js-plotly-plot') if item.is_displayed()]
        assert charts, f"No linked Plotly panel at {width}x{height}"
    elif page_name == "search":
        assert "Результаты" in text or "Введите хотя бы две" in text
    elif page_name == "add_data":
        assert "Проверка импорта" in text and "Что добавить?" in text
        assert any(item.is_displayed() for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stFileUploader"]'))
    elif page_name == "thin":
        assert "Шлифы" in text
        assert "Добавьте первый общий снимок" in text or "Фотографии" in text
    elif page_name == "statistics":
        assert "Статистика" in text and "1. Найти группы" in text and "2. PCA" in text
    elif page_name == "publication":
        assert "Экспорт и публикация" in text and "Рисунок" in text and "Таблицы" in text and "Данные" in text


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="petrolab_product_design_acceptance_"))
    process: subprocess.Popen | None = None
    driver: webdriver.Chrome | None = None
    try:
        _seed_test_data(root)
        output = Path(os.environ.get("PETROLAB_V0159_ACCEPTANCE_ARTIFACTS", "v0159_acceptance_artifacts"))
        output.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PETROLAB_DATA_DIR"] = str(root / "data")
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true", f"--server.port={PORT}", "--server.address=127.0.0.1", "--browser.gatherUsageStats=false"],
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

        for page_name, (nav_label, destination) in PAGES.items():
            driver.set_window_size(1440, 900)
            _navigate(driver, nav_label, destination)
            if page_name == "search":
                _prepare_search(driver)
            for width, height in VIEWPORTS:
                driver.set_window_size(width, height)
                _wait_for_idle(driver)
                _assert_page(driver, page_name, width, height)
                driver.save_screenshot(str(output / f"{page_name}_{width}x{height}.png"))

        print("PetroLab Product Design real-browser acceptance: OK")
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
