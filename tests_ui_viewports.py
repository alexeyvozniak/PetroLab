from __future__ import annotations

import gc
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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PORT = 8517
VIEWPORTS = ((1440, 900), (1024, 768), (768, 900), (390, 844))
PAGES = (
    ("home", "Главная"),
    ("workspace", "Рабочий стол"),
    ("thin_section", "Работать со шлифом"),
    ("graphs", "XY-диаграммы"),
    ("thermodynamics", "Термодинамика"),
    ("rocks", "Породы"),
    ("publication", "Таблицы для статьи"),
)


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not start at {url}: {last_error}")


def _seed_test_data(root: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(root / "data")
    from petrolab.db import add_dataset, create_project, replace_dataset_rows
    from petrolab.repositories.rock_repository import create_rock, replace_composition, replace_isotopes
    from petrolab.storage import ensure_storage

    ensure_storage()
    project_id = create_project("Viewport project", "Synthetic CI-only UI data")
    frame = pd.DataFrame({
        "Sample": ["V1", "V2", "V3"], "Generation": ["core", "rim", "core"],
        "SiO2": [39.2, 40.1, 38.8], "Al2O3": [14.1, 13.7, 15.0],
        "FeOt": [7.2, 8.1, 6.8], "Rb [µg/g]": [410.0, 520.0, 390.0],
    })
    csv_path = root / "viewport_dataset.csv"
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(project_id, "Viewport mica", "mica", "viewport.xlsx", "Sheet1", "viewport-sha", str(csv_path), len(frame))
    replace_dataset_rows(dataset_id, frame, source_rows=[2, 3, 4])
    rock_id = create_rock(project_id, "ViewportRock", massif="Test massif", lithology="lamprophyre")
    replace_composition(rock_id, {"SiO2": 44.0, "Na2O": 2.5, "K2O": 3.0, "MgO": 12.0, "FeOt": 10.0})
    replace_isotopes(rock_id, pd.DataFrame([
        {"system": "Sr", "ratio_name": "87Sr/86Sr", "analysis_label": "A", "value": 0.70310, "uncertainty": 0.00002, "source": "viewport"},
        {"system": "Sr", "ratio_name": "87Sr/86Sr", "analysis_label": "B", "value": 0.70318, "uncertainty": 0.00003, "source": "viewport"},
    ]))


def _reset_desktop_metrics(driver: webdriver.Chrome) -> None:
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    driver.set_window_size(1280, 900)


def _sidebar_buttons(driver: webdriver.Chrome, label: str):
    return [
        button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
        if button.text.strip() == label
    ]


def _visible_sidebar_buttons(driver: webdriver.Chrome, label: str):
    return [button for button in _sidebar_buttons(driver, label) if button.is_displayed()]


def _expand_tool_navigation(driver: webdriver.Chrome, label: str) -> None:
    summaries = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] [data-testid="stExpander"] summary')
    for summary in summaries:
        if summary.is_displayed() and "Все инструменты" in summary.text:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", summary)
            time.sleep(0.5)
            matches = _sidebar_buttons(driver, label)
            if matches:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", matches[0])
                time.sleep(0.25)
            return


def _select_page(driver: webdriver.Chrome, label: str, output: Path, page_name: str) -> None:
    _reset_desktop_metrics(driver)
    driver.refresh()
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stSidebar"]')))
    output.mkdir(parents=True, exist_ok=True)
    try:
        if not _visible_sidebar_buttons(driver, label):
            _expand_tool_navigation(driver, label)
        wait.until(lambda d: bool(_visible_sidebar_buttons(d, label)))
        buttons = _visible_sidebar_buttons(driver, label)
        assert buttons, f"Sidebar button not found: {label}"
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", buttons[0])
        buttons[0].click()
        time.sleep(1.2)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stMain"]')))
    except Exception:
        driver.save_screenshot(str(output / f"{page_name}_navigation_failure.png"))
        raise


def _assert_viewport(driver: webdriver.Chrome, width: int, height: int, page_name: str, output: Path) -> None:
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
    time.sleep(0.8)
    metrics = driver.execute_script("""
        return {
          innerWidth: window.innerWidth,
          innerHeight: window.innerHeight,
          scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
          mainWidth: document.querySelector('[data-testid="stMain"]')?.getBoundingClientRect().width || 0,
          mainRight: document.querySelector('[data-testid="stMain"]')?.getBoundingClientRect().right || 0
        };
    """)
    assert abs(int(metrics["innerWidth"]) - width) <= 1, metrics
    assert abs(int(metrics["innerHeight"]) - height) <= 1, metrics
    allowed = width + 3
    assert metrics["scrollWidth"] <= allowed, f"Global horizontal overflow on {page_name} at {width}x{height}: {metrics}"
    assert metrics["mainWidth"] > 0, f"Main Streamlit container missing on {page_name}"
    assert metrics["mainRight"] <= allowed + 2, f"Main content escapes viewport on {page_name}: {metrics}"
    output.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(output / f"{page_name}_{width}x{height}.png"))


def _stop_process(process: subprocess.Popen) -> None:
    """Reap Streamlit fully before attempting to remove its SQLite data directory."""
    if process.poll() is None:
        process.terminate()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)
    if process.stdout is not None:
        process.stdout.close()


def _remove_temp_tree(root: Path) -> None:
    """Retry only transient Windows file-lock cleanup; never hide a persistent leak."""
    last_error: PermissionError | None = None
    for delay in (0.0, 0.10, 0.25, 0.50, 1.0, 2.0):
        if delay:
            time.sleep(delay)
        gc.collect()
        try:
            shutil.rmtree(root)
            return
        except PermissionError as exc:
            last_error = exc
    if root.exists():
        assert last_error is not None
        raise last_error


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="petrolab_viewport_"))
    process: subprocess.Popen | None = None
    driver: webdriver.Chrome | None = None
    try:
        _seed_test_data(root)
        output = Path(os.environ.get("PETROLAB_VIEWPORT_ARTIFACTS", "viewport_artifacts"))
        env = os.environ.copy(); env["PETROLAB_DATA_DIR"] = str(root / "data")
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
            f"--server.port={PORT}", "--server.address=127.0.0.1", "--browser.gatherUsageStats=false",
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        url = f"http://127.0.0.1:{PORT}"
        _wait_for_server(url)
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new"); options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,900")
        try:
            driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise RuntimeError(f"Could not start headless Chrome: {exc}") from exc
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stAppViewContainer"]')))
        for page_name, label in PAGES:
            _select_page(driver, label, output, page_name)
            for width, height in VIEWPORTS:
                _assert_viewport(driver, width, height, page_name, output)
    finally:
        if driver is not None:
            try:
                driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
            except WebDriverException:
                pass
            driver.quit()
        if process is not None:
            _stop_process(process)
        # Main-process repository helpers can also leave short-lived row/cursor
        # objects pending finalization; retry cleanup only after every child is gone.
        _remove_temp_tree(root)
    print("real-browser viewport tests: OK")


if __name__ == "__main__":
    main()
