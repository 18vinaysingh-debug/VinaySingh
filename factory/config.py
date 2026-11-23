"""Load config.yaml and .env; resolve project paths."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "jobs"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
SECRETS_DIR = ROOT / "secrets"

for d in (JOBS_DIR, DATA_DIR, REPORTS_DIR, SECRETS_DIR):
    d.mkdir(exist_ok=True)


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config():
    _load_env()
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def secret(name):
    return os.environ.get(name, "").strip()
