from pathlib import Path
import os
import shutil
from logger import logger
from enum import Enum, auto

def remake_dir(path: Path, debug_TAG=None):
    if path.exists():
        if debug_TAG:
            logger.debug(f"{debug_TAG} remove: {path}")
        shutil.rmtree(path)
    os.makedirs(path)

class SessionStatus(Enum):
    Skipped = auto()
    Success = auto()
    Failed = auto()
