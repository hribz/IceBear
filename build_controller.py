from pathlib import Path
import subprocess
import shutil
import threading
from typing import List, Dict
from subprocess import CompletedProcess, run
from IncAnalysis.logger import logger
import json
import argparse
import os
import sys
import re
import time
import multiprocessing as mp
from functools import partial

from data_struct.reply import Reply
from IncAnalysis.utils import *
from IncAnalysis.environment import *
from IncAnalysis.repository import MultiConfigRepository
from IncAnalysis.configuration import Option

def main(args):
    parser = ArgumentParser()
    opts = parser.parse_args(args)
    logger.verbose = opts.verbose

    repo_info = [
        # {
        #     'name': 'json', 
        #     'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/json', 
        #     'options_list': [
        #     ]
        # },
        # {
        #     'name': 'xgboost', 
        #     'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/xgboost', 
        #     'options_list': [
        #         [('GOOGLE_TEST=ON')]
        #     ]
        # },
        # {
        #     'name': 'opencv', 
        #     'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/opencv', 
        #     'options_list': [
        #         [('WITH_CLP=ON')]
        #     ]
        # },
        {
            'name': 'ica-demo',
            'src_path': '/home/xiaoyu/cmake-analyzer/cmake-projects/ica-demo',
            'options_list': [
                [('CHANGE_ALL=ON')],
                # [('GLOBAL_CONSTANT=ON')],
                # [('VIRTUAL_FUNCTION=ON')],
                # [('RECORD_FIELD=ON')],
                # [('FEATURE_UPGRADE=ON')],
                # [('COMMON_CHANGE=ON')],
            ]
        }
    ]

    repo_list: List[MultiConfigRepository] = []
    env = Environment(opts)

    for repo in repo_info:
        repo_db = MultiConfigRepository(repo['name'], repo['src_path'], env, options_list=repo['options_list'])
        repo_list.append(repo_db)
        logger.info('-------------BEGIN SUMMARY-------------\n')
        # repo_db.build_every_config()
        repo_db.prepare_file_list_every_config()
        repo_db.preprocess_every_config()
        repo_db.diff_every_config()
        repo_db.extract_ii_every_config()
        repo_db.generate_efm_for_every_config()
        repo_db.analyze_for_every_config()
        repo_db.file_status_to_csv()

        # Copy compile_commands.json to build dir for clangd.
        shutil.copy(str(repo_db.default_config.compile_database), str(repo_db.src_path / 'build'))

    for repo_db in repo_list:
        logger.TAG = repo_db.name
        logger.info('---------------END SUMMARY-------------\n'+repo_db.session_summary())

if __name__ == '__main__':
    main(sys.argv[1:])