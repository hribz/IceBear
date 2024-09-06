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
    def __init__(self, timestamp, TAG):
        self.TAG = TAG
        self.verbose = False
        ensure_dir('logs')
        handler = {
            logging.DEBUG: "logs/debug_{}.log".format(timestamp),
            logging.INFO: "logs/info_{}.log".format(timestamp),
            logging.ERROR: "logs/error_{}.log".format(timestamp)
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

            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            sh.setLevel(level)
            logger.addHandler(fh)
            logger.addHandler(sh)
            self.__loggers.update({level: logger})
    def info(self, message):
        self.__loggers[logging.INFO].info(f"[{self.TAG}]" + message)
    def debug(self, message):
        self.__loggers[logging.DEBUG].debug(f"[{self.TAG}]" + message)
    def error(self, message):
        self.__loggers[logging.ERROR].error(f"[{self.TAG}]" + message)

logger = Logger(datetime.now().strftime('%Y%m%d_%H%M%S'), '')