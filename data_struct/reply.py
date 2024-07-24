from data_struct.codemodel import *
from data_struct.target import *
from data_struct.directory import *
from data_struct.cache import *
from data_struct.cmakeFiles import *
from data_struct.index import *

from pathlib import Path
import json

class Reply:
    code_model: CodeModel
    target_list: List[Target]
    directory_list: List[Directory]
    cache: Cache
    cmake_files: CMakeFiles

    def __init__(self, reply_path: Path, logger) -> None:
        self.logger = logger
        if not reply_path.exists():
            logger.error("[Reply Init] CMake configure reply floder doesn't exists!")
            return
        self.target_list = []
        self.directory_list = []
        for path in reply_path.rglob('*'):
            if path.is_file():
                logger.debug(f"[Reply Init] parse json file {path}")
                with open(path.absolute(), 'rb') as f:
                    data = json.loads(f.read())
                if path.name.startswith("codemodel"):
                    self.code_model = code_model_from_dict(data)
                elif path.name.startswith("cache"):
                    self.cache = cache_from_dict(data)
                elif path.name.startswith("cmakeFiles"):
                    self.cmake_files = c_make_files_from_dict(data)
                elif path.name.startswith("target"):
                    self.target_list.append(target_from_dict(data))
                elif path.name.startswith("directory"):
                    self.directory_list.append(directory_from_dict(data))