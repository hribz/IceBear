import concurrent.futures
import csv
import os
import re
import shutil
from enum import Enum, auto
from pathlib import Path
from typing import List

from IncAnalysis.logger import logger


def makedir(path, debug_TAG=None):
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


def remove_file(file: str):
    if os.path.exists(file):
        os.remove(file)


class SessionStatus(Enum):
    Skipped = auto()
    Success = auto()
    Failed = auto()


def getExtDefMap(efmfile):
    return open(efmfile).read()


def virtualCall(file, method, has_arg, arg=None):
    if has_arg:
        getattr(file, method.__name__)(arg)
    else:
        getattr(file, method.__name__)()


def replace_loc_info(pair):
    src, dest = pair
    if not src:
        logger.debug(f"[Replace Loc Info] Skip file {dest}")
        return
    try:
        pattern = re.compile(r"^# \d+")
        with open(src, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = ["\n" if pattern.match(line) else line for line in lines]
        makedir(os.path.dirname(dest))
        with open(dest, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Error processing {src}: {e}")


def get_origin_file_name(file: str, prefix: str, extnames: List[str]):
    file = file[len(prefix) :]
    for ext in extnames:
        if file.endswith(ext):
            file = file[: -len(ext)]
            break
    return file


def parse_efm(efmline: str):
    efmline = efmline.strip()
    if not efmline:
        return None, None
    try:  # The new "<usr-length>:<usr> <path>" format (D102669).
        lenlen = efmline.find(":")
        usrlen = int(efmline[:lenlen])
        usr = efmline[: lenlen + usrlen + 1]
        path = efmline[lenlen + usrlen + 2 :]
        return usr, path
    except ValueError:  # When <usr-length> is not available.
        efmitem = efmline.split(" ")
        if len(efmitem) == 2:
            return efmitem[0], efmitem[1]
        logger.error(f"[Parse EFM] efmline {efmline} format error.")
        return None, None


def read_csv(csv_file):
    with open(csv_file, mode="r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, None)
        data = list(reader)
        return header, data


def add_to_csv(headers, data, csv_file, write_headers: bool = True):
    makedir(os.path.dirname(csv_file))
    with open(csv_file, "w" if write_headers else "a", newline="") as f:
        writer = csv.writer(f)
        if write_headers:
            writer.writerow(headers)
        if data is not None:
            writer.writerows(data)


def process_file_list(method, file_list: List, jobs):
    # Can't use mutilprocessing, because every process has its own memory space.
    # with mp.Pool(self.env.analyze_opts.jobs) as p:
    #     p.starmap(virtualCall, [(file, method, False) for file in file_list])

    # threads = []
    # for file in file_list:
    #     thread = threading.Thread(target=getattr(file, method.__name__))
    #     thread.start()
    #     threads.append(thread)
    #     # getattr(file, method.__name__)()

    # for thread in threads:
    #     thread.join()
    ret = True
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [
            executor.submit(getattr(file, method.__name__)) for file in file_list
        ]

        for idx, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()  # 获取任务结果，如果有的话
            logger.info(
                f"[{method.__name__} {idx+1}/{len(file_list)}] [{result}] {file_list[idx].identifier}"
            )
            ret = ret and result
    return ret


def commands_to_shell_script(commands):
    assert commands is not None
    from shlex import join

    return join(commands)
