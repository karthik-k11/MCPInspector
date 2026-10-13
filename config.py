import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

DATABASE_PATH = os.environ.get(
    "MCPINSPECTOR_DATABASE",
    str(INSTANCE_DIR / "mcpinspector.db"),
)