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


PORT = 8527
ROOT = Path(tempfile.mkdtemp(prefix="petrolab_image_intake_browser_"))
os.environ["PETROLAB_DATA_DIR"] = str(ROOT / "data")
ARTIFACTS = Path("image_intake_browser_artifacts")

from petrolab.db import add_dataset, create_project, replace_dataset_rows
from petrolab.storage import ensure_storage


def _seed() -> Path:
    ensure_storage()
    project_id = create_project("Image intake browser", "Direct images-only workflow")
    dataframe = pd.DataFrame(
        {
            "Sample": ["19", "19", "19"],
            "Point": ["P-1", "P-2", "P-3"],
            "SiO2": [40.0, 41.0, 42.0],
            "TiO2": [2.0, 2.2, 1.8],
            "Al2O3": [13.0, 14.0, 15.0],
        }
    )
    csv_path = ROOT / "sheet.csv"
    dataframe.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id=project_id,
        name="Session · Sheet 7",
        mineral_key="mica",
        source_filename="session.xlsx",
        source_sheet="Sheet 7",
        source_sha256="image-intake-session",
        csv_path=str(csv_path),
        row_count=len(dataframe),
    )
    replace_dataset_rows(dataset_id, dataframe, source_rows=[2, 3, 4])

    image_path = ROOT / "sample19_bse.png"
    buffer = BytesIO()
    Image.new("RGB", (900, 600), "white").save(buffer, format="PNG")
    image_path.write_bytes(buffer.getvalue())
    return image_path


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


def _wait_for_main_text(driver: webdriver.Chrome, needle: str, timeout: float = 25.0) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            last = _main_text(driver)
        except Exception:
            last = ""
        if needle in last:
            _wait_for_idle(driver)
            last = _main_text(driver)
            if needle in last:
                return last
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {needle!r}. Current main text: {last[:3000]}")


def _visible_button(driver: webdriver.Chrome, label: str):
    items = [
        item for item in driver.find_elements(By.TAG_NAME, "button")
        if item.is_displayed() and item.text.strip() == label
    ]
    return items[0] if items else None


def _click_button(driver: webdriver.Chrome, label: str) -> None:
    button = WebDriverWait(driver, 20).until(lambda d: _visible_button(d, label))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", button)


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
    driver.execute_script("arguments[0].click();", candidates[0])
    _wait_for_main_text(driver, "Рабочий стол")


def _assert_no_exception(driver: webdriver.Chrome) -> None:
    exceptions = [
        item.text for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stException"]')
        if item.is_displayed()
    ]
    assert not exceptions, exceptions


def main() -> None:
    image_path = _seed()
    process: subprocess.Popen | None = None
    driver: webdriver.Chrome | None = None
    ARTIFACTS.mkdir(exist_ok=True)
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
        WebDriverWait(driver, 25).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[data-testid="stAppViewContainer"]')
        )
        _wait_for_idle(driver)

        _navigate_sidebar(driver, "Данные")
        driver.save_screenshot(str(ARTIFACTS / "00_workspace_before_image_intake.png"))
        _click_button(driver, "+ Добавить изображения")
        try:
            text = _wait_for_main_text(driver, "Добавить изображения")
        except AssertionError:
            driver.save_screenshot(str(ARTIFACTS / "01_after_image_button_diagnostic.png"))
            raise
        driver.save_screenshot(str(ARTIFACTS / "01_image_intake_entry.png"))
        assert "Фазовые наборы выбирать не нужно" in text
        assert "Перетащите изображения или выберите файлы" in text
        assert "Что добавить?" not in text
        assert "Добавить данные" not in text
        _assert_no_exception(driver)

        upload = WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.CSS_SELECTOR, 'input[type="file"]')
        )
        upload.send_keys(str(image_path.resolve()))
        try:
            text = _wait_for_main_text(driver, "К чему относится это изображение?")
        except AssertionError:
            driver.save_screenshot(str(ARTIFACTS / "02_after_upload_diagnostic.png"))
            raise
        assert "Исходный лист" in text
        assert "Какие точки видны на фотографии?" in text
        assert "Весь лист: 3 анализов" in text
        assert "Дальше → разметить изображения" not in text
        assert "Тип изображения" not in text
        assert "Что добавить?" not in text
        _assert_no_exception(driver)

        driver.save_screenshot(str(ARTIFACTS / "02_direct_image_intake_1440x900.png"))
        print("PetroLab compact direct image intake browser path: OK")
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
