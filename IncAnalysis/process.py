import subprocess
from subprocess import TimeoutExpired, CalledProcessError

class Process:

    class Stat:
        timeout = 'TIMEOUT',
        unknown = 'UNKNOWN',
        error = 'ERROR',
        terminated = 'TERMINATED',
        ok = 'OK'
        skipped = 'Skipped'

    def __init__(self, cmd, directory, timeout=600):
        self.cmd = cmd
        self.timeout = timeout
        try:
            proc = subprocess.run(
                self.cmd, text=True, timeout=self.timeout, capture_output=True, check=True, cwd=directory)
            self.stat = Process.Stat.ok
            self.stdout = proc.stdout
            self.stderr = proc.stderr
        except TimeoutExpired as e:
            self.stat = Process.Stat.timeout
            self.stderr = e.stderr
            self.stdout = e.stdout
        except CalledProcessError as e:
            if e.returncode < 0:
                self.stat = Process.Stat.terminated
                self.signal = -e.returncode
            elif e.returncode > 0:
                self.stat = Process.Stat.error
                self.code = e.returncode
            self.stdout = e.stdout
            self.stderr = e.stderr
        except Exception as e:
            self.stat = Process.Stat.unknown
            self.exception = e
            self.stderr = e.stdout
            self.stdout = e.stderr