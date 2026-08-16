from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_ui_viewports import _remove_temp_tree, _seed_test_data, _stop_process


PORT = 8523
VIEWPORTS = ((1440, 900), (1024, 768), (968, 516), (768, 900), (390, 844))
PAGES = (("home", "Главная"), ("data", "Данные"), ("graphs", "Графики"))


def _wait_for_server(url: str, timeout: float = 35.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - only useful in CI diagnostics
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError(f"Streamlit did not start at {url}: {last_error}")


def _running(driver: webdriver.Chrome) -> bool:
    return bool(driver.execute_script(
        """
        return Array.from(document.querySelectorAll('button')).some(el => {
          if (el.offsetParent === null) return false;
          return (el.innerText || '').trim() === 'Stop';
        });
        """
    ))


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
    """Wait for Streamlit to finish rerun and for the rendered main tree to stop moving."""
    deadline = time.time() + timeout
    stable = 0
    previous: tuple[int, int] | None = None
    while time.time() < deadline:
        if _running(driver):
            stable = 0
            previous = None
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
            stable = 0
            previous = signature
        time.sleep(0.2)
    raise AssertionError(f"Streamlit did not become visually idle; running={_running(driver)}, signature={_main_signature(driver)}")


def _visible_sidebar_button(driver: webdriver.Chrome, label: str):
    buttons = [
        button for button in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] button')
        if button.text.strip() == label and button.is_displayed()
    ]
    return buttons[0] if buttons else None


def _navigate(driver: webdriver.Chrome, label: str) -> None:
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    driver.set_window_size(1280, 900)
    driver.refresh()
    WebDriverWait(driver, 25).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"]')
    )
    _wait_for_idle(driver)
    button = _visible_sidebar_button(driver, label)
    if button is None:
        summaries = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stSidebar"] [data-testid="stExpander"] summary')
        for summary in summaries:
            if summary.is_displayed() and "Дополнительно" in summary.text:
                driver.execute_script("arguments[0].click();", summary)
                time.sleep(0.2)
                button = _visible_sidebar_button(driver, label)
                if button is not None:
                    break
    assert button is not None, f"Navigation button not found: {label}"
    driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", button)
    _wait_for_idle(driver)


def _assert_common(driver: webdriver.Chrome, page_name: str, width: int, height: int) -> None:
    result = driver.execute_script(
        """
        const main = document.querySelector('[data-testid="stMain"]');
        const exceptions = Array.from(document.querySelectorAll('[data-testid="stException"]'))
          .filter(el => el.offsetParent !== null)
          .map(el => (el.innerText || '').slice(0, 400));
        return {
          running: Array.from(document.querySelectorAll('button')).some(el => el.offsetParent !== null && (el.innerText || '').trim() === 'Stop'),
          scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
          mainWidth: main ? main.getBoundingClientRect().width : 0,
          exceptions,
          text: main ? (main.innerText || '') : ''
        };
        """
    )
    assert not result["running"], f"Screenshot attempted during Streamlit rerun: {page_name} {width}x{height}"
    assert not result["exceptions"], f"Visible Streamlit exception: {page_name} {width}x{height}: {result['exceptions']}"
    assert float(result["mainWidth"]) > 0, f"Main content missing: {page_name}"
    assert float(result["scrollWidth"]) <= width + 3, f"Horizontal overflow: {page_name} {width}x{height}: {result['scrollWidth']}"
    assert len(str(result["text"]).strip()) >= 20, f"Suspiciously empty main area: {page_name} {width}x{height}"


def _assert_page(driver: webdriver.Chrome, page_name: str, width: int, height: int) -> None:
    _assert_common(driver, page_name, width, height)
    if page_name == "home":
        text = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
        for label in ("Данные", "Добавить", "Графики", "Шлифы"):
            assert label in text, f"Home primary action missing at {width}x{height}: {label}"
        return

    if page_name == "data":
        text = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
        assert "Рабочий стол" in text, f"Data workspace title missing at {width}x{height}"
        assert "3 анализов" in text, f"Dataset result count missing at {width}x{height}"
        grids = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stDataFrame"], [data-testid="stDataEditor"]')
        assert grids, f"Analyses workspace rendered without a table/editor at {width}x{height}"
        return

    if page_name == "graphs":
        text = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
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
        minimum_width = 520 if width >= 1200 else 350 if width >= 700 else 300
        assert float(rect["width"]) >= minimum_width, f"Plot is too narrow at {width}x{height}: {rect}"
        minimum_visible = 140 if height <= 600 else 180
        assert float(rect["visibleHeight"]) >= minimum_visible, f"First plot is not sufficiently visible at {width}x{height}: {rect}"
        return


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="petrolab_v0159_acceptance_"))
    process: subprocess.Popen | None = None
    driver: webdriver.Chrome | None = None
    try:
        _seed_test_data(root)
        output = Path(os.environ.get("PETROLAB_V0159_ACCEPTANCE_ARTIFACTS", "v0159_acceptance_artifacts"))
        output.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PETROLAB_DATA_DIR"] = str(root / "data")
        process = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
                f"--server.port={PORT}", "--server.address=127.0.0.1", "--browser.gatherUsageStats=false",
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
        options.add_argument("--window-size=1280,900")
        try:
            driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise RuntimeError(f"Could not start headless Chrome: {exc}") from exc
        driver.get(url)
        WebDriverWait(driver, 25).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[data-testid="stAppViewContainer"]')
        )
        _wait_for_idle(driver)

        expected: list[Path] = []
        for page_name, label in PAGES:
            _navigate(driver, label)
            for width, height in VIEWPORTS:
                driver.execute_cdp_cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                _wait_for_idle(driver)
                _assert_page(driver, page_name, width, height)
                target = output / f"{page_name}_{width}x{height}.png"
                driver.save_screenshot(str(target))
                expected.append(target)

        missing = [str(path) for path in expected if not path.exists() or path.stat().st_size < 10_000]
        assert not missing, f"Incomplete stable viewport artifact set: {missing}"
    finally:
        if driver is not None:
            try:
                driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
            except WebDriverException:
                pass
            driver.quit()
        if process is not None:
            _stop_process(process)
        _remove_temp_tree(root)
    print("PetroLab 0.15.9 stable UI acceptance: OK")


if __name__ == "__main__":
    main()
