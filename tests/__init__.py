import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
for folder in ["frontend", "backend", "mocks"]:
    folder_path = str(ROOT_DIR / folder)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)
