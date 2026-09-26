"""Central logging: rotating file + (optional) console."""
import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import LOG_DIR


def setup_logging(debug: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    log = logging.getLogger("jarvis")
    log.setLevel(logging.DEBUG if debug else logging.INFO)
    if log.handlers:
        return log
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    fh = RotatingFileHandler(LOG_DIR / "jarvis.log", maxBytes=1_000_000, backupCount=3,
                             encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    if sys.stderr is not None and debug:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        log.addHandler(sh)
    return log
