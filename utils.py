from pathlib import Path
import os
import shutil
from logger import logger

def remake_dir(path: Path, debug_TAG=None):
    if path.exists():
        if debug_TAG:
            logger.debug(f"{debug_TAG} remove: {path}")
        shutil.rmtree(path)
    os.makedirs(path)