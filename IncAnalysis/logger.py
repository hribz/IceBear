import os
import sys
import logging
from datetime import datetime

def ensure_dir(d, verbose=True):
    if not os.path.exists(d):
        if verbose:
            print("Directory {} do not exist; creating...".format(d))
        os.makedirs(d)

class Logger(object):
    def __init__(self, TAG):
        self.TAG = TAG
        self.verbose = False
        handler = {
            logging.DEBUG: sys.stderr,
            logging.INFO: sys.stdout,
        }
        self.__loggers = {}
        logLevels = handler.keys()
        fmt = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')
        for level in logLevels:
            logger = logging.getLogger(str(level))
            logger.setLevel(level)
            
            sh = logging.StreamHandler(handler[level])
            sh.setFormatter(fmt)
            sh.setLevel(level)
            logger.addHandler(sh)
            self.__loggers.update({level: logger})
        
    def start_log(self, timestamp, workspace):
        ensure_dir(workspace)
        handler = {
            logging.DEBUG: "{}/debug.log".format(workspace),
            logging.INFO: "{}/info.log".format(workspace),
            # logging.ERROR: "{}/{}_error.log".format(timestamp)
        }
        self.__loggers = {}
        logLevels = handler.keys()
        fmt = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')
        for level in logLevels:
            logger = logging.getLogger(str(level))
            logger.setLevel(level)
            
            log_path = os.path.abspath(handler[level])
            fh = logging.FileHandler(log_path)
            fh.setFormatter(fmt)
            fh.setLevel(level)

            logger.addHandler(fh)
            self.__loggers.update({level: logger})

    def info(self, message):
        self.__loggers[logging.INFO].info(f"[{self.TAG}]" + message)
    def debug(self, message):
        self.__loggers[logging.DEBUG].debug(f"[{self.TAG}]" + message)
    def error(self, message):
        self.__loggers[logging.DEBUG].error(f"[{self.TAG}]" + message)

logger = Logger('Prepare Env')