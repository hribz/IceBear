import os
import sys
import logging
from datetime import datetime


def remake_file(file):
    if os.path.isfile(file) and os.path.exists(file):
        os.remove(file)


def ensure_dir(d, verbose=True):
    if not os.path.exists(d):
        if verbose:
            print("Directory {} do not exist; creating...".format(d))
        os.makedirs(d)


class Logger(object):
    def __init__(self, TAG):
        self.TAG = TAG
        self.verbose = False
        self.handler = {
            logging.DEBUG: sys.stderr,
            logging.INFO: sys.stdout,
        }
        self.__loggers = {}
        logLevels = self.handler.keys()
        fmt = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
        for level in logLevels:
            logger = logging.getLogger(str(level))
            logger.setLevel(level)

            sh = logging.StreamHandler(self.handler[level])
            sh.setFormatter(fmt)
            sh.setLevel(level)
            logger.addHandler(sh)
            self.__loggers.update({level: logger})

    def start_log(self, timestamp, workspace):
        ensure_dir(workspace)
        debug_file = "{}/debug_{}.log".format(workspace, timestamp)
        info_file = "{}/info_{}.log".format(workspace, timestamp)
        self.handler = {
            logging.DEBUG: debug_file,
            logging.INFO: info_file,
            # logging.ERROR: "{}/{}_error.log".format(timestamp)
        }
        self.__loggers = {}
        if not self.verbose:
            self.handler.pop(logging.DEBUG)
        logLevels = self.handler.keys()
        fmt = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
        for level in logLevels:
            logger = logging.getLogger(str(level))
            logger.setLevel(level)

            if len(logger.handlers) > 1:
                logger.handlers.pop()

            log_path = os.path.abspath(self.handler[level])
            remake_file(log_path)
            fh = logging.FileHandler(log_path)
            fh.setFormatter(fmt)
            fh.setLevel(level)

            logger.addHandler(fh)
            self.__loggers.update({level: logger})

    def info(self, message):
        self.__loggers[logging.INFO].info(f"[{self.TAG}]" + message)

    def debug(self, message):
        if not self.verbose:
            return
        self.__loggers[logging.DEBUG].debug(f"[{self.TAG}]" + message)

    def error(self, message):
        self.__loggers[logging.INFO].error(f"[{self.TAG}]" + message)


logger = Logger("Prepare Env")
