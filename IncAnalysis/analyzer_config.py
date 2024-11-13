from enum import Enum, auto
import json

class IncrementalMode(Enum):
    NoInc = auto()
    FileLevel = auto()
    FuncitonLevel = auto()
    InlineLevel = auto()

class AnalyzerConfig:
    def __init__(self):
        self.options = []

class CSAConfig(AnalyzerConfig):
    def __init__(self):
        super.__init__()
        self.AnalyzeAll = False
        
    def init_from_file(self, config_file):
        with open(config_file, 'r') as f:
            json_config = json.load(f)
