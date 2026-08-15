from __future__ import annotations

import os
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


PORT = 8521
VIEWPORTS = ((1440, 900), (390, 844))
PAGES = (("workflow", "Рабочий процесс"), ("mixed", "Фазы и выбросы"))


def _wait(url: str, timeout: float = 35.0) -> None:
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
    raise RuntimeError(f"Streamlit did not start: {last_error}")


def _seed(root: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(root / "data")
    from petrolab.db import add_dataset, create_project, replace_dataset_rows
    from petrolab.storage import ensure_storage

    ensure_storage()
    project_id = create_project("Guided UI", "CI-only guided workflow project")
    rows = []
    for index in range(8):
        rows.append({
            "Sample": "PG-1", "Grain": "Cpx-1", "Point": f"p{index + 1}",
            "SiO2": 50.8 + 0.1 * (index % 3), "Al2O3": 2.5 + 0.1 * (index % 2),
            "FeO": 6.0 + 0.1 * (index % 2), "MgO": 15.0 + 0.1 * (index % 3),
            "CaO": 21.0 - 0.1 * (index % 3), "Na2O": 0.8,
        })
    rows.append({
        "Sample": "PG-1", "Grain": "Cpx-1", "Point": "p9",
        "SiO2": 48.5, "Al2O3": 2.0, "FeO": 8.0, "MgO": 8.0, "CaO": 28.0, "Na2O": 1.0,
    })
    frame = pd.DataFrame(rows)
    csv_path = root / "guided_mixed.csv"
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id, "Probe mixed", "generic", "probe.xlsx", "Sheet1", "guided-sha",
        str(csv_path), len(frame), source_kind="managed_copy",
    )
    replace_dataset_rows(dataset_id, frame, source_rows=list(range(2, 2 + len(frame))))


def _sidebar_buttons(driver: webdriver.Chrome, label: str):
    return [
        button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
        if button.text.strip() == label
    ]


def _visible_sidebar_buttons(driver: webdriver.Chrome, label: str):
    return [button for button in _sidebar_buttons(driver, label) if button.is_displayed()]


def _expand_tools_if_needed(driver: webdriver.Chrome, label: str) -> None:
    """Open and scroll the secondary-tools group so off-screen entries become clickable."""
    if _visible_sidebar_buttons(driver, label):
        return
    sidebar = driver.find_element(By.CSS_SELECTOR, '[data-testid="stSidebar"]')
    expanders = sidebar.find_elements(By.CSS_SELECTOR, '[data-testid="stExpander"]')
    for expander in expanders:
        try:
            summary = expander.find_element(By.CSS_SELECTOR, "summary")
        except Exception:
            continue
        if "Все инструменты" not in summary.text:
            continue
        try:
            details = expander.find_element(By.CSS_SELECTOR, "details")
            opened = details.get_attribute("open") is not None
        except Exception:
            opened = False
        if not opened:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", summary)
            time.sleep(0.5)
        matches = _sidebar_buttons(driver, label)
        if matches:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", matches[0])
            time.sleep(0.25)
        return


def _select_page(driver: webdriver.Chrome, label: str, output: Path, slug: str) -> None:
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    driver.set_window_size(1280, 900)
    driver.refresh()
    wait = WebDriverWait(driver, 25)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stSidebar"]')))
    try:
        _expand_tools_if_needed(driver, label)
        wait.until(lambda d: bool(_visible_sidebar_buttons(d, label)))
        buttons = _visible_sidebar_buttons(driver, label)
        assert buttons, f"Sidebar button not found after expanding tools: {label}"
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", buttons[0])
        buttons[0].click()
        time.sleep(1.5)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stMain"]')))
    except Exception:
        output.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(output / f"{slug}_navigation_failure.png"))
        raise


def _assert_viewport(driver: webdriver.Chrome, width: int, height: int, slug: str, output: Path) -> None:
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
    })
    time.sleep(1.0)
    metrics = driver.execute_script("""
        return {
          innerWidth: window.innerWidth,
          scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
          mainWidth: document.querySelector('[data-testid="stMain"]')?.getBoundingClientRect().width || 0,
          mainRight: document.querySelector('[data-testid="stMain"]')?.getBoundingClientRect().right || 0
        };
    """)
    allowed = width + 3
    assert abs(int(metrics["innerWidth"]) - width) <= 1, metrics
    assert metrics["scrollWidth"] <= allowed, f"Global horizontal overflow on {slug} at {width}x{height}: {metrics}"
    assert metrics["mainWidth"] > 0, metrics
    assert metrics["mainRight"] <= allowed + 2, metrics
    output.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(output / f"{slug}_{width}x{height}.png"))


def main() -> None:
    # Windows may retain the SQLite handle briefly after the Streamlit process exits.
    # Ignore only cleanup races; all browser assertions and process shutdown still run normally.
    with tempfile.TemporaryDirectory(prefix="petrolab_guided_ui_", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _seed(root)
        output = Path(os.environ.get("PETROLAB_GUIDED_VIEWPORT_ARTIFACTS", "guided_viewport_artifacts"))
        env = os.environ.copy()
        env["PETROLAB_DATA_DIR"] = str(root / "data")
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
            f"--server.port={PORT}", "--server.address=127.0.0.1", "--browser.gatherUsageStats=false",
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        driver: webdriver.Chrome | None = None
        try:
            url = f"http://127.0.0.1:{PORT}"
            _wait(url)
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1280,900")
            try:
                driver = webdriver.Chrome(options=options)
            except WebDriverException as exc:
                raise RuntimeError(f"Could not start headless Chrome: {exc}") from exc
            driver.get(url)
            WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stAppViewContainer"]')))
            for slug, label in PAGES:
                _select_page(driver, label, output, slug)
                for width, height in VIEWPORTS:
                    _assert_viewport(driver, width, height, slug, output)
        finally:
            if driver is not None:
                try:
                    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
                except WebDriverException:
                    pass
                driver.quit()
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print("guided workflow real-browser viewport tests: OK")


if __name__ == "__main__":
    main()
