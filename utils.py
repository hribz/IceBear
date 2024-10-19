from pathlib import Path
import os
import shutil
from logger import logger
from enum import Enum, auto

def makedir(path: str, debug_TAG=None):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except FileExistsError:  # may happen when multi-thread
            pass

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

class FileKind(Enum):
    Preprocessed = auto()
    DIFF = auto()
    AST = auto()
    EFM = auto()
    CG = auto()
    CF = auto()
    RF = auto()
    FS = auto()