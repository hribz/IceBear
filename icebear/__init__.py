import sys
import os
from pathlib import Path

from IncAnalysis.environment import Environment, ArgumentParser
from IncAnalysis.repository import UpdateConfigRepository
from IncAnalysis.logger import logger
from IncAnalysis.utils import makedir
from IncAnalysis.reports_postprocess import postprocess_workspace


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

    opts.repo = os.path.abspath(opts.repo)
    if not os.path.exists(opts.repo):
        logger.info(f"Please make sure repository {opts.repo} exists.")
        exit(1)
    repo = os.path.abspath(opts.repo)

    workspace = os.path.abspath(opts.output)
    makedir(workspace)

    build_command = opts.build
    build_root = opts.build_dir
    if build_root:
        build_root = os.path.abspath(opts.build_dir)
    if build_command is None and (opts.cdb is None or not os.path.exists(opts.cdb)):
        if opts.cdb is None:
            logger.info(
                f"Please specify compilation database if your don't build through icebear."
            )
        else:
            logger.info(
                f"Please make sure compilation database file {opts.cdb} exists."
            )
        exit(1)

    cdb = opts.cdb
    if opts.cdb is not None and os.path.exists(opts.cdb):
        cdb = os.path.abspath(opts.cdb)

    if opts.tag:
        version_stamp = opts.tag
    else:
        version_stamp = env.timestamp

    Repo = UpdateConfigRepository(
        os.path.basename(repo),
        repo,
        env,
        workspace=workspace,
        configure_scripts=[],
        build_script=build_command,
        build_root=build_root,
        cdb=cdb,
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
