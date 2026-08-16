from __future__ import annotations

import os
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
VIEWPORTS = ((1440, 900), (390, 844))


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
    print("product guidance real-browser navigation/viewport tests: OK")


if __name__ == "__main__":
    main()
