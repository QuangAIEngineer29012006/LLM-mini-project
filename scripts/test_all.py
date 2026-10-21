import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "database"):
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=directory)
    if result.returncode:
        raise SystemExit(result.returncode)
