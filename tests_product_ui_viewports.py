from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests_guided_ui_viewports import _assert_viewport, _seed, _select_page, _visible_sidebar_buttons, _wait


PORT = 8522
PAGES = (
    ("add_data", "Добавить данные", ("Универсальный +", "Файлы", "Excel / CSV")),
    ("attention", "Требует внимания", ("Сначала проверить", "Неразобранные фазы / mixed")),
    ("batch", "Массовые действия", ("Наборы", "Фильтр")),
    ("history", "История правок данных", ("История действий", "Интерпретации", "Значения и Excel")),
)
PRIMARY_NAV = (
    "Главная", "Данные", "Графики", "Статистика", "Шлифы и изображения",
    "Расчёты", "Публикация", "Поиск", "Настройки",
)
PLOT_TOOLS = ("Точка", "Прямоугольник", "Лассо", "Панорама")
VIEWPORTS = ((1440, 900), (390, 844))
_SELECTION_RE = re.compile(r"Выбрано:\s*(\d+)")


def _wait_for_page_content(driver: webdriver.Chrome, expected: tuple[str, ...], slug: str, output: Path) -> None:
    wait = WebDriverWait(driver, 30)
    try:
        def ready(browser):
            main = browser.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]')
            text = main.text
            return all(marker in text for marker in expected)
        wait.until(ready)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        output.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(output / f"{slug}_content_failure.png"))
        main_text = ""
        try:
            main_text = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
        except Exception:
            pass
        raise AssertionError(f"Product page {slug} did not render expected content {expected}. Main text: {main_text!r}")


def _wait_for_primary_navigation(driver: webdriver.Chrome, output: Path) -> list[str]:
    wait = WebDriverWait(driver, 35)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stSidebar"]')))

        def ready(browser):
            sidebar = browser.find_element(By.CSS_SELECTOR, '[data-testid="stSidebar"]')
            visible = [
                button.text.strip()
                for button in sidebar.find_elements(By.TAG_NAME, "button")
                if button.is_displayed()
            ]
            return visible if all(label in visible for label in PRIMARY_NAV) else False

        return list(wait.until(ready))
    except Exception:
        output.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(output / "primary_navigation_failure.png"))
        raise


def _assert_primary_navigation(driver: webdriver.Chrome, output: Path) -> None:
    visible = _wait_for_primary_navigation(driver, output)
    for implementation_label in ["Минералогические модули", "Быстрый импорт", "Новые анализы", "Редактор пород"]:
        assert implementation_label not in visible, f"Implementation route leaked into primary navigation: {implementation_label}"


def _click_primary_without_refresh(driver: webdriver.Chrome, label: str, output: Path, slug: str) -> None:
    """Navigate inside one Streamlit websocket session so Back history is meaningful."""
    wait = WebDriverWait(driver, 25)
    try:
        wait.until(lambda d: bool(_visible_sidebar_buttons(d, label)))
        button = _visible_sidebar_buttons(driver, label)[0]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
        button.click()
        time.sleep(0.8)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stMain"]')))
    except Exception:
        output.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(output / f"{slug}_navigation_failure.png"))
        raise


def _assert_back_flow(driver: webdriver.Chrome, output: Path) -> None:
    # Do not use _select_page here: that viewport helper intentionally hard-refreshes
    # before each independent screenshot page. A hard refresh starts a new Streamlit
    # frontend session and therefore cannot test navigation history by definition.
    _click_primary_without_refresh(driver, "Данные", output, "back_data")
    _wait_for_page_content(driver, ("Рабочий стол",), "back_data", output)
    _click_primary_without_refresh(driver, "Графики", output, "back_plots")
    _wait_for_page_content(driver, ("XY-диаграммы",), "back_plots", output)

    wait = WebDriverWait(driver, 20)
    try:
        wait.until(lambda d: bool(_visible_sidebar_buttons(d, "← Назад")))
    except Exception:
        output.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(output / "back_button_missing.png"))
        raise
    back = _visible_sidebar_buttons(driver, "← Назад")[0]
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", back)
    back.click()
    deadline = time.time() + 20.0
    while time.time() < deadline:
        try:
            if "Рабочий стол" in driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text:
                return
        except Exception:
            pass
        time.sleep(0.25)
    output.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(output / "back_navigation_failure.png"))
    raise AssertionError("Browser Back action did not restore the previous Data workspace route")


def _main_buttons(driver: webdriver.Chrome, label: str):
    main = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]')
    return [
        button for button in main.find_elements(By.TAG_NAME, "button")
        if button.is_displayed() and button.text.strip() == label
    ]


def _selection_count(driver: webdriver.Chrome) -> int:
    text = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
    match = _SELECTION_RE.search(text)
    return int(match.group(1)) if match else 0


def _plotly_drag_box(driver: webdriver.Chrome) -> bool:
    """Use Chrome's native input dispatcher on the actual Plotly drag surface."""
    geometry = driver.execute_script(
        """
        const graph = document.querySelector('[data-testid="stPlotlyChart"] .js-plotly-plot');
        const surface = document.querySelector('[data-testid="stPlotlyChart"] .nsewdrag');
        if (!graph || !surface || !window.Plotly) return null;
        window.Plotly.relayout(graph, {dragmode: 'select'});
        const rect = surface.getBoundingClientRect();
        return {
            mode: (graph._fullLayout && graph._fullLayout.dragmode) || '',
            left: rect.left, top: rect.top, width: rect.width, height: rect.height,
        };
        """
    )
    if not isinstance(geometry, dict) or geometry.get("mode") != "select":
        return False
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
    if width < 80 or height < 80:
        return False
    x1 = float(geometry["left"]) + width * 0.06
    y1 = float(geometry["top"]) + height * 0.06
    x2 = float(geometry["left"]) + width * 0.94
    y2 = float(geometry["top"]) + height * 0.94
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": x1, "y": y1,
    })
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x1, "y": y1,
        "button": "left", "buttons": 1, "clickCount": 1,
    })
    steps = 18
    for index in range(1, steps + 1):
        fraction = index / steps
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x1 + (x2 - x1) * fraction,
            "y": y1 + (y2 - y1) * fraction,
            "button": "left", "buttons": 1,
        })
        time.sleep(0.025)
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x2, "y": y2,
        "button": "left", "buttons": 0, "clickCount": 1,
    })
    return True


def _assert_plotly_selection_handoff(driver: webdriver.Chrome, output: Path) -> None:
    """Physically brush Plotly in Chrome and verify SelectionContext -> multi-panel."""
    _click_primary_without_refresh(driver, "Графики", output, "linked_selection_xy")
    _wait_for_page_content(driver, ("XY-диаграммы", *PLOT_TOOLS), "linked_selection_xy", output)
    wait = WebDriverWait(driver, 30)
    try:
        for label in PLOT_TOOLS:
            wait.until(lambda d, value=label: bool(_main_buttons(d, value)))
        assert _plotly_drag_box(driver), "Plotly chart did not expose a native box-select surface"
        selected = int(wait.until(lambda d: _selection_count(d) or False))
        assert selected > 0, "Native Chrome box drag did not reach PetroLab SelectionContext"

        wait.until(lambda d: bool(_main_buttons(d, "Несколько")))
        multi_button = _main_buttons(driver, "Несколько")[0]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", multi_button)
        multi_button.click()
        wait.until(
            lambda d: "Сравнить на нескольких диаграммах"
            in d.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
        )
        wait.until(lambda d: _selection_count(d) == selected)
    except Exception as exc:
        output.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(output / "plotly_selection_handoff_failure.png"))
        main_text = ""
        try:
            main_text = driver.find_element(By.CSS_SELECTOR, '[data-testid="stMain"]').text
        except Exception:
            pass
        raise AssertionError(
            "Real-browser Plotly brushing did not survive the XY -> multi-panel handoff. "
            f"Cause: {exc!r}. Main text: {main_text!r}"
        ) from exc


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_product_ui_", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _seed(root)
        output = Path(os.environ.get("PETROLAB_PRODUCT_VIEWPORT_ARTIFACTS", "product_viewport_artifacts"))
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
            _assert_primary_navigation(driver, output)
            _assert_back_flow(driver, output)
            _assert_plotly_selection_handoff(driver, output)
            for slug, label, expected in PAGES:
                _select_page(driver, label, output, slug)
                _wait_for_page_content(driver, expected, slug, output)
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
    print("product guidance real-browser navigation/linked-selection/viewport tests: OK")


if __name__ == "__main__":
    main()
