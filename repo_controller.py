from shlex import join
import sys
import json
import time

from IncAnalysis.repository import UpdateConfigRepository, BuildType
from IncAnalysis.utils import *
from IncAnalysis.environment import *
from IncAnalysis.logger import logger
from IncAnalysis.utils import add_to_csv
from git_utils import *

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--repo', type=str, dest='repo', help='Only analyse specific repos.')
        self.parser.add_argument('--daily', type=int, default=10, dest='daily', help='Analyse n daily commits.')
        self.parser.add_argument('--codechecker', action='store_true', dest='codechecker', help='Use CodeChecker as scheduler.')

class RepoInfo:
    def __init__(self, repo, env: Environment):
        self.repo_name = repo["project"]
        self.repo_dir = Path(env.PWD / f"repos/{self.repo_name}")
        self.build_type = repo["build_type"]
        self.default_options = repo["config_options"] if repo.get("config_options") else []
        self.branch = repo["branch"]
        self.out_of_tree = True if repo.get("out_of_tree") is None else repo.get("out_of_tree")
        
        self.abs_repo_path = str(self.repo_dir.absolute())
        if env.analyze_opts.codechecker:
            self.workspace = f"{self.abs_repo_path}_workspace/codechecker_{env.timestamp}"
        else:
            self.workspace = f"{self.abs_repo_path}_workspace/{env.timestamp}_{env.analyze_opts.inc}"

def IncAnalyzerAction(Repo: UpdateConfigRepository, version_stamp, repo_info: RepoInfo, env: Environment, result_file, result_file_specific, init_csv) -> UpdateConfigRepository:
    if Repo is None:
        # Analysis first commit as baseline.
        Repo = UpdateConfigRepository(repo_info.repo_name, repo_info.abs_repo_path, env, build_root=f"{repo_info.abs_repo_path}_build", default_options=repo_info.default_options,
                        version_stamp=version_stamp, default_build_type=repo_info.build_type, can_skip_configure=False, workspace=repo_info.workspace, out_of_tree=repo_info.out_of_tree)
        
    else:
        Repo.update_version(version_stamp)
    Repo.process_one_config()
    return Repo

def CodeCheckerAction(Repo: UpdateConfigRepository, version_stamp, repo_info: RepoInfo, env: Environment) -> UpdateConfigRepository:
    if Repo is None:
        # Analysis first commit as baseline.
        Repo = UpdateConfigRepository(repo_info.repo_name, repo_info.abs_repo_path, env, build_root=f"{repo_info.abs_repo_path}_build", default_options=repo_info.default_options,
                        version_stamp=version_stamp, default_build_type=repo_info.build_type, can_skip_configure=False, workspace=repo_info.workspace, out_of_tree=repo_info.out_of_tree)
        add_to_csv(["project", "version", "File Number", "Report Number", "CSA", "Total"], None, Repo.summary_csv_path(), True)
    else:
        Repo.update_version(version_stamp)
    Repo.only_clean_and_configure()
    start_time = time.time()
    try:
        os.chdir(Repo.default_config.build_path)
        codechecker_cmd = ["CodeChecker", "check"]
        codechecker_cmd.extend(["-b", f"\"{Repo.default_config.build_script}\""])
        codechecker_cmd.extend(["--analyzers", "clang-tidy"])
        codechecker_cmd.extend([f"-j {env.analyze_opts.jobs}"])
        # Remove duplicate compile command to make sure each file is analyzed only once.
        codechecker_cmd.extend(["--compile-uniqueing", "symlink"])
        codechecker_cmd.extend(["-o", f"{Repo.default_config.codechecker_path}"])
        if env.analyze_opts.verbose:
            codechecker_cmd.extend(["--verbose", "debug_analyzer"])
        codechecker_script = " ".join(codechecker_cmd)
        logger.debug(f"[CodeChecker Script] {codechecker_script}")
        p = subprocess.run(codechecker_script, shell=True, check=True, text=True, capture_output=True)
        logger.debug(f"[CodeChecker Success]\nstdout:\n{p.stdout}")
        if p.stderr:
            logger.debug(f"stderr:\n{p.stderr}\n")
    except subprocess.CalledProcessError as e:
        logger.debug(f"[CodeChecker Error]\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}\n")
    
    total_time = time.time() - start_time
    # Parse reports
    try:
        parse_cmd = ["CodeChecker", "parse"]
        parse_cmd.extend(['-e', 'html'])
        parse_cmd.extend([f"{Repo.default_config.codechecker_path}", '-o', f"{Repo.default_config.codechecker_path / 'html'}"])
        parse_script = commands_to_shell_script(parse_cmd)
        logger.debug(f"[CodeChecker Parse Script] {parse_script}")
        p = subprocess.run(parse_script, shell=True, check=True, text=True, capture_output=True)
        logger.debug(f"[CodeChecker Parse Success]\nstdout:\n{p.stdout}")
        if p.stderr:
            logger.debug(f"stderr:\n{p.stderr}\n")
    except subprocess.CalledProcessError as e:
        logger.debug(f"[CodeChecker Parse Error]\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}\n")
    # Capture Tools Time
    tools_time_file_path = str(Repo.default_config.codechecker_path / 'metadata.json')
    tools_time = 0.0
    if os.path.exists(tools_time_file_path):
        with open(tools_time_file_path, 'r') as f:
            json_tools_time = json.load(f)
            timestamp = json_tools_time["tools"][0]["timestamps"]
            tools_time = timestamp["end"] - timestamp["begin"]
    # Parse Summary
    processed_files_number = 0
    reports_number = 0
    statistics_file_path = str(Repo.default_config.codechecker_path / 'statistics.txt')
    if os.path.exists(statistics_file_path):
        with open(statistics_file_path, 'r') as f:
            for line in f.readlines():
                line = line.strip()
                if line.startswith("Number of processed analyzer result files"):
                    processed_files_number = line.split(' ')[-1]
                elif line.startswith("Number of analyzer reports"):
                    reports_number = line.split(' ')[-1]

    add_to_csv(None, [[Repo.name, version_stamp, processed_files_number, reports_number,
                        ("%.3lf" % tools_time), ("%.3lf" % total_time)]], Repo.summary_csv_path(), False)
    os.chdir(env.PWD)
    return Repo

def main(args):
    parser = RepoParser()
    opts = parser.parse_args(args)
    env = Environment(opts)
    repos = 'repos/repos.json'
    test_repos = 'repos/test_grpc.json'
    FFmpeg = 'repos/test_ffmpeg.json'
    grpc = 'repos/test_grpc.json'
    ica_demo = 'repos/test_ica_demo.json'

    repo_list = repos

    result_file = f'repos/result/{env.timestamp}_{env.analyze_opts.inc}_result.csv'
    result_file_specific = f'repos/result/{env.timestamp}_{env.analyze_opts.inc}_result_specific.csv'
    # result_file = 'repos/result/result_all.csv'
    # result_file_specific = 'repos/result/result_all_specific.csv'
    
    with open(repo_list, 'r') as f:
        repo_json = json.load(f)
    Repo = None
    
    class STATUS(Enum):
        BEGIN = auto()
        NORMAL = auto()
        CLONE_FAILED = auto()
        CHECK_FAILED = auto()
    status = STATUS.BEGIN
    init_csv = True

    for repo in repo_json:
        os.chdir(env.PWD)
        repo_info = RepoInfo(repo, env)
        
        if opts.repo and opts.repo != repo_info.repo_name and opts.repo != os.path.basename(repo_info.repo_dir):
            continue
        if repo_info.repo_name in ignore_repos:
            logger.info(f"{repo_info.repo_name} is in ignore repo list")
            continue

        if Repo is None:
            if not clone_project(repo_info.repo_name):
                status = STATUS.CLONE_FAILED
                continue
            update_submodules(repo_info.repo_dir)

        commits = get_recent_n_daily_commits(repo_info.repo_dir, opts.daily, repo_info.branch) if opts.daily>0 else [commit['hash'] for commit in repo['commits']]
        for commit_sha in commits:
            status = STATUS.NORMAL
            if checkout_target_commit(repo_info.abs_repo_path, commit_sha):
                logger.info(f"[Git Checkout] checkout {repo_info.repo_name} to {commit_sha}")
                commit_date = get_head_commit_date(repo_info.repo_dir)
                version_stamp = f"{commit_date}_{commit_sha[:6]}"
                if opts.codechecker:
                    Repo = CodeCheckerAction(Repo, version_stamp, repo_info, env)
                else:
                    Repo = IncAnalyzerAction(Repo, version_stamp, repo_info, env, result_file, result_file_specific, init_csv)
                    init_csv = False
            else:
                status = STATUS.CHECK_FAILED
                logger.error(f"[Checkout Commit] {repo_info.repo_name} checkout to {commit_sha} failed!")
        if Repo:
            logger.info('---------------END SUMMARY-------------\n'+Repo.session_summaries)
            headers, datas = read_csv(Repo.summary_csv_path(specific=False))
            add_to_csv(headers, datas, result_file, init_csv)
            headers, datas = read_csv(Repo.summary_csv_path(specific=True))
            add_to_csv(headers, datas, result_file_specific, init_csv)
            Repo = None

if __name__ == "__main__":
    main(sys.argv[1:])