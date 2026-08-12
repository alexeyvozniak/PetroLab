from pathlib import Path

path = Path("petrolab/services/image_service.py")
text = path.read_text(encoding="utf-8")
old_import = '''from __future__ import annotations\n\nimport os\nimport sqlite3\n'''
new_import = '''from __future__ import annotations\n\nimport io\nimport os\nimport sqlite3\n'''
if old_import not in text:
    raise SystemExit("image import target not found")
text = text.replace(old_import, new_import, 1)

old_pandas = '''import pandas as pd\n\nfrom petrolab.db import'''
new_pandas = '''import pandas as pd\nfrom PIL import Image, UnidentifiedImageError\n\nfrom petrolab.db import'''
if old_pandas not in text:
    raise SystemExit("Pillow import target not found")
text = text.replace(old_pandas, new_pandas, 1)

old_validate = '''def _validate_payload(image: ImagePayload) -> None:\n    filename = Path(image.filename).name\n    if not filename:\n        raise ValueError("У изображения отсутствует имя файла")\n    suffix = Path(filename).suffix.lower()\n    if suffix not in SUPPORTED_IMAGE_SUFFIXES:\n        raise ValueError(f"Неподдерживаемый формат изображения: {suffix}")\n    if not image.data:\n        raise ValueError(f"Файл {filename} пустой")\n'''
new_validate = '''def _validate_payload(image: ImagePayload) -> None:\n    filename = Path(image.filename).name\n    if not filename:\n        raise ValueError("У изображения отсутствует имя файла")\n    suffix = Path(filename).suffix.lower()\n    if suffix not in SUPPORTED_IMAGE_SUFFIXES:\n        raise ValueError(f"Неподдерживаемый формат изображения: {suffix}")\n    if not image.data:\n        raise ValueError(f"Файл {filename} пустой")\n\n    # Do not trust the extension alone. A truncated or renamed non-image file should fail\n    # before any part of the batch is written to disk/database. Pillow.verify() checks the\n    # container structure without decoding the full raster into memory.\n    try:\n        with Image.open(io.BytesIO(image.data)) as opened:\n            opened.verify()\n    except (UnidentifiedImageError, OSError, SyntaxError) as exc:\n        raise ValueError(f"Файл {filename} не является читаемым изображением или повреждён") from exc\n'''
if old_validate not in text:
    raise SystemExit("image validation target not found")
text = text.replace(old_validate, new_validate, 1)

path.write_text(text, encoding="utf-8")
print("image content validation patch applied")
