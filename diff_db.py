# database used by incremental task

class DiffRegion:
    start_line: int
    line_count: int

class FileDiffResult:
    file: str
    

class DiffDB:
    def __init__(self):
        self.db = {}

