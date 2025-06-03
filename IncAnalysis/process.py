import subprocess
import time
from subprocess import CalledProcessError, TimeoutExpired


class Process:

    class Stat:
        timeout = ("TIMEOUT",)
        unknown = ("UNKNOWN",)
        error = ("ERROR",)
        terminated = ("TERMINATED",)
        ok = "OK"
        skipped = "Skipped"

    def __init__(self, cmd, directory, timeout=600):
        self.cmd = cmd
        self.timeout = timeout
        self.timecost = 0.0
        start_time = time.time()
        try:
            proc = subprocess.run(
                self.cmd,
                text=True,
                timeout=self.timeout,
                capture_output=True,
                check=True,
                cwd=directory,
            )
            self.timecost = (
                time.time() - start_time
            )  # Only record time cost when process normally exited.
            self.stat = Process.Stat.ok
            self.stdout = proc.stdout
            self.stderr = proc.stderr
        except TimeoutExpired as e:
            self.timecost = "timeout"
            self.stat = Process.Stat.timeout
            self.stderr = e.stderr
            self.stdout = e.stdout
        except CalledProcessError as e:
            self.timecost = "error"
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
