import os
import sys

from IncAnalysis.environment import ArgumentParser, Environment
from IncAnalysis.logger import logger
from IncAnalysis.reports_postprocess import postprocess_workspace
from IncAnalysis.repository import UpdateConfigRepository
from IncAnalysis.utils import makedir


class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument(
            "--repo",
            type=str,
            dest="repo",
            default=".",
            help="The directory of the project that need to be analyzed.",
        )
        self.parser.add_argument(
            "--build",
            type=str,
            dest="build",
            default=None,
            help="The command used to build the project.",
        )
        self.parser.add_argument(
            "--build-dir",
            type=str,
            dest="build_dir",
            default=".",
            help="The directory to build the project.",
        )
        self.parser.add_argument(
            "-o",
            "--output",
            type=str,
            dest="output",
            default="./ice-bear-output",
            help="Store analysis results to directory.",
        )
        self.parser.add_argument(
            "-f",
            "--compilation-database",
            type=str,
            dest="cdb",
            help="Customize the input compilation database",
            default=None,
        )
        self.parser.add_argument(
            "-c", "--cache", type=str, dest="cache", help="Cache file path"
        )
        self.parser.add_argument(
            "--tag", type=str, dest="tag", help="Specific version stamp"
        )
        self.parser.add_argument(
            "--preprocess-only",
            dest="prep_only",
            action="store_true",
            help="Only preprocess and diff",
        )
        self.parser.add_argument(
            "--not-update-cache",
            dest="not_update_cache",
            action="store_true",
            help="Do not record or update cache",
        )
        self.parser.add_argument(
            "--report-hash",
            dest="hash_type",
            required=False,
            choices=["path", "context"],
            default="path",
            help="The way to calculate report hash. Currently supported modes "
            "are: [path, context].",
        )
        self.parser.add_argument(
            "--only-process-reports",
            dest="only_process_reports",
            action="store_true",
            help="Only postprocess reports",
        )


def main_impl(argv):
    parser = RepoParser()
    opts = parser.parse_args(argv)
    ice_bear_path = os.path.abspath(__file__)
    env = Environment(opts, os.path.dirname(ice_bear_path))

    # icebear script execution directory
    script_exec_dir = os.environ.get('ICEBEAR_EXEC_DIR', os.getcwd())
    logger.info(f"Script executed from directory: {script_exec_dir}")

    if not os.path.isabs(opts.repo):
        # handle relative path based on script execution directory
        repo_dir = os.path.join(script_exec_dir, opts.repo)
    else:
        repo_dir = opts.repo
    repo_dir = os.path.abspath(repo_dir)  # 确保是规范化的绝对路径
    print(f"Repository directory: {repo_dir}")
    
    # handle output path
    if not os.path.isabs(opts.output):
        output_dir = os.path.join(script_exec_dir, opts.output)
    else:
        output_dir = opts.output
    workspace = os.path.abspath(output_dir)
    
    # handle build_dir path
    build_dir = opts.build_dir
    if build_dir is not None and not os.path.isabs(opts.build_dir):
        build_dir = os.path.join(script_exec_dir, opts.build_dir)
    if build_dir is not None:
        build_dir = os.path.abspath(build_dir)
    
    # handle compilation database path
    cdb_dir = opts.cdb
    if cdb_dir is not None and not os.path.isabs(opts.cdb):
        cdb_dir = os.path.join(script_exec_dir, opts.cdb)
    if cdb_dir is not None:
        cdb_dir = os.path.abspath(cdb_dir)

    # handle cache path
    cache_path = opts.cache
    if cache_path is not None and not os.path.isabs(opts.cache):
        cache_path = os.path.join(script_exec_dir, opts.cache)
    if cache_path is not None:
        cache_path = os.path.abspath(cache_path)

    if not os.path.exists(repo_dir):
        logger.info(f"Please make sure repository {repo_dir} exists.")
        exit(1)

    makedir(workspace)

    build_command = opts.build

    if build_command is None and (cdb_dir is None or not os.path.exists(cdb_dir)):
        if cdb_dir is None:
            logger.info(
                "Please specify compilation database if your don't build through icebear."
            )
        else:
            logger.info(
                f"Please make sure compilation database file {cdb_dir} exists."
            )
        exit(1)

    if opts.tag:
        version_stamp = opts.tag
    else:
        version_stamp = env.timestamp

    # update cache path in env object
    if cache_path is not None:
        env.analyze_opts.cache = cache_path

    Repo = UpdateConfigRepository(
        os.path.basename(repo_dir),
        repo_dir,
        env,
        workspace=workspace,
        configure_scripts=[],
        build_script=build_command,
        build_root=build_dir,
        cdb=cdb_dir,
        need_build=build_command is not None,
        need_configure=False,
        version_stamp=version_stamp,
        default_build_type="unknown",
    )
    success = True
    if not opts.only_process_reports:
        success = Repo.process_one_config(summary_path="logs")
    if success:
        for inc in Repo.default_config.inc_levels:
            postprocess_workspace(
                workspace,
                version_stamp,
                env.analyze_opts.hash_type,
                inc,
                output_news=True,
            )
    logger.info(f"Analysis finished, results are stored in {workspace}.")


def main():
    main_impl(sys.argv[1:])


if __name__ == "__main__":
    main_impl(sys.argv[1:])
