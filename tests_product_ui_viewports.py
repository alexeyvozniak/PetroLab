from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests_guided_ui_viewports import _assert_viewport, _seed, _select_page, _wait


PORT = 8522
PAGES = (
    ("add_data", "Добавить данные", ("Мои анализы", "Статья / коллега", "Полевые Sample")),
    ("attention", "Требует внимания", ("PetroLab собирает оставшиеся хвосты",)),
    ("batch", "Массовые действия", ("Изменить фазу, Generation или морфологию",)),
    ("history", "История действий · История правок данных", ("Интерпретации", "Значения и Excel")),
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_product_ui_") as tmp:
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
    print("product guidance real-browser viewport tests: OK")


if __name__ == "__main__":
    main()
