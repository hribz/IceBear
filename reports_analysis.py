import hashlib
import os
from pathlib import Path
import sys
import json
import yaml

from IncAnalysis.repository import UpdateConfigRepository, BuildType
from IncAnalysis.utils import *
from IncAnalysis.environment import *
from IncAnalysis.logger import logger
from IncAnalysis.utils import add_to_csv
from git_utils import *
from matplotlib_venn import venn2

def list_files(directory: str):
    if not os.path.exists(directory):
        return []
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def list_dir(directory: str, filt_set: set=None):
    if not os.path.exists(directory):
        logger.info(f"{directory} does not exist.")
        return []
    dir_list = [f for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]
    if filt_set:
        return list(filter(lambda x: (x in filt_set), dir_list))
    else:
        return dir_list

def collect_reports(analyzer_output_path: str):
    commit_to_reports = {}
    sub_dirs = list_dir(analyzer_output_path)
    for dir in sub_dirs:
        reports = list_files(os.path.join(analyzer_output_path, dir))
        commit_to_reports[dir] = reports
    return commit_to_reports

def all_reports(commit_to_reports) -> set:
    total_reports = set()
    for dir in commit_to_reports.keys():
        reports = commit_to_reports[dir]
        total_reports.update(set(reports))
    return total_reports


def dict_hash(diagnostic: dict, encoding='utf-8'):
    sha256 = hashlib.sha256()
    sha256.update(json.dumps(diagnostic, sort_keys=True).encode(encoding))
    return sha256.hexdigest()

class RepoParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.parser.add_argument('--repo', type=str, dest='repo', help='Only analyse specific repos.')
        self.parser.add_argument('--workspace1', type=str, dest='workspace1', help='Result path1.')
        self.parser.add_argument('--workspace2', type=str, dest='workspace2', help='Result path2.')
        self.parser.add_argument('--json1', type=str, dest='json1', help='Reports1 json statistics.')
        self.parser.add_argument('--json2', type=str, dest='json2', help='Reports2 json statistics.')

class RepoInfo:
    def __init__(self, repo, env: Environment, workspace):
        self.repo_name = repo["project"]
        self.repo_dir = Path(env.PWD / f"repos/{self.repo_name}")
        self.build_type = repo["build_type"]
        self.default_options = repo["config_options"] if repo.get("config_options") else []
        self.branch = repo["branch"]
        self.out_of_tree = True if repo.get("out_of_tree") is None else repo.get("out_of_tree")
        
        self.abs_repo_path = str(self.repo_dir.absolute())
        self.workspace = f"{self.abs_repo_path}_workspace/{workspace}"

class Report:
    def __init__(self, analyzer, version, report_name, specific_info):
        self.analyzer = analyzer
        self.version = version
        self.report_name = report_name
        self.specific_info = specific_info

    def __eq__(self, other):
        if isinstance(other, Report):
            return self.report_name == other.report_name and dict_hash(self.specific_info) == dict_hash(other.specific_info)
        return False

    def __hash__(self):
        return hash((self.report_name, self.specific_info.__str__()))
    
    def __to_json__(self):
        return {
            "version": self.version,
            "report name": self.report_name,
            "specific info": self.specific_info
        }


def diff_reports(reports1: set, reports2: set, dir1, dir2):
    diff1 = reports1.difference(reports2)
    diff2 = reports2.difference(reports1)
    diff = diff1.union(diff2)
    diff_json = {}
    if len(diff) == 0:
        logger.info(f"Congratulations! There is no difference between reports in {dir1} and {dir2}")
    else:
        if len(diff1) > 0:
            logger.info(f"Sad! There are {len(diff1)} reports only in {dir1}:")
            diff_json[dir1] = [i.__to_json__() for i in diff1]
        if len(diff2) > 0:
            logger.info(f"Sad! There are {len(diff2)} reports only in {dir2}:")
            diff_json[dir2] = [i.__to_json__() for i in diff2]
    return diff_json

analyzers = ['csa', 'clang-tidy', 'cppcheck']

def main(args):
    parser = RepoParser()
    opts = parser.parse_args(args)
    if not opts.workspace1 or not opts.workspace2:
        print("Please specify workspace1 and workspace2.")
        exit(1)
    env = Environment(opts, os.path.dirname(os.path.abspath(__file__)))
    repos = 'repos/benchmark.json'
    total_summary = [{
        opts.workspace1: {
            "total reports": 0,
            "unique reports": 0,
            "new reports": 0,
            "diff reports": 0
        },
        opts.workspace2: {
            "total reports": 0,
            "unique reports": 0,
            "new reports": 0,
            "diff reports": 0
        }
    }]

    repo_list = repos
    
    with open(repo_list, 'r') as f:
        repo_json = json.load(f)

    for repo in repo_json:
        os.chdir(env.PWD)
        repo_info = RepoInfo(repo, env, opts.workspace1)
        repo_info2 = RepoInfo(repo, env, opts.workspace2)
        logger.TAG = repo_info.repo_name
        repo_summary = {
            "project": repo_info.repo_name
        }
        
        if opts.repo and opts.repo != repo_info.repo_name and opts.repo != os.path.basename(repo_info.repo_dir):
            continue
        if repo_info.repo_name in ignore_repos:
            logger.info(f"{repo_info.repo_name} is in ignore repo list")
            continue
        if not os.path.exists(repo_info.workspace):
            logger.info(f"{repo_info.workspace} not exists")
            continue
        if not os.path.exists(repo_info2.workspace):
            logger.info(f"{repo_info2.workspace} not exists")
            continue

        def get_versions(workspace, analyzer):
            with open(os.path.join(workspace, 'reports_statistics.json'), 'r') as f:
                info = json.load(f)
                return [i['version'] for i in info[analyzer]]

        def get_statistics_from_workspace(workspace):
            analyzers_floder = [os.path.join(workspace, analyzer) for analyzer in list_dir(workspace, analyzers)]
            
            statistics = {
                "summary": {
                    "total": 0,
                    "unique": 0,
                    "new": 0
                }
            }
            for k in analyzers:
                statistics[k] = []
            baseline_reports_number = 0

            for analyzer in analyzers_floder:
                if analyzer.endswith('csa'):
                    reports_path = os.path.join(analyzer, 'csa-reports')
                    analyzer_name = 'csa'
                elif analyzer.endswith('clang-tidy'):
                    analyzer_name = 'clang-tidy'
                    reports_path = os.path.join(analyzer, 'clang-tidy-reports')
                elif analyzer.endswith('cppcheck'):
                    analyzer_name = 'cppcheck'
                    reports_path = os.path.join(analyzer, 'cppcheck-reports')
                elif analyzer.endswith('infer'):
                    analyzer_name = 'infer'
                    reports_path = os.path.join(analyzer, 'infer-reports')

                analyzer_to_class = {
                    'csa': "CSA", "clang-tidy": "ClangTidy", "cppcheck": "CppCheck"
                }
                versions = get_versions(workspace, analyzer_to_class[analyzer_name])
                statistics['summary'][analyzer_name] = {
                    "total": 0
                }

                analyzer_baseline_number = None
                for version in versions:
                    output_path = os.path.join(reports_path, version)
                    reports = []
                    if analyzer.endswith('csa'):
                        if not os.path.exists(output_path):
                            continue
                        reports = list_files(output_path)
                    elif analyzer.endswith('clang-tidy'):
                        if not os.path.exists(output_path):
                            continue

                        unique_reports = dict()
                        for file in list_files(output_path):
                            with open(os.path.join(output_path, file), 'r') as f:
                                report = yaml.safe_load(f)
                            diagnostics = report['Diagnostics']
                            for diagnostic in diagnostics:
                                report_hash = dict_hash({
                                    "DiagnosticName": diagnostic['DiagnosticName'],
                                    "DiagnosticMessage": {
                                        "Message": diagnostic['DiagnosticMessage']['Message'],
                                        "FilePath": diagnostic['DiagnosticMessage']['FilePath'],
                                    },
                                    "Level": diagnostic['Level'],
                                    "BuildDirectory": diagnostic['BuildDirectory']
                                })
                                unique_reports[report_hash] = {
                                    'kind': diagnostic['DiagnosticName'],
                                    'file': diagnostic['DiagnosticMessage']['FilePath'],
                                    'diagnostic': diagnostic['DiagnosticMessage']['Message'],
                                    'hash': report_hash
                                }
                        reports = list(unique_reports.values())
                    elif analyzer.endswith('cppcheck'):
                        if not os.path.exists(os.path.join(output_path, 'result.json')):
                            continue
                        with open(os.path.join(output_path, 'result.json'), 'r') as f:
                            cppcheck_result = json.load(f)
                            results = cppcheck_result["runs"][0]["results"]
                            for result in results:
                                message = result['message']['text']
                                if message.rfind("at line") != -1:
                                    result['message']['text'] = message[:message.rfind("at line")]
                                else:
                                    result['message']['text'] = message
                                report = {k:v for k, v in result.items() if k != 'locations'}
                                report['locations'] = result['locations'][-1]['physicalLocation']['artifactLocation']['uri']
                                reports.append(report)
                    elif analyzer.endswith('infer'):
                        if not os.path.exists(os.path.join(output_path, 'report.json')):
                            continue
                        with open(os.path.join(output_path, 'report.json'), 'r') as f:
                            infer_result = json.load(f)
                            key_set = {'bug_type', 'qualifier', 'severity', 'category', 'procedure', 'file', 'key', 'bug_type_hum'}
                            reports = [{k: v for k, v in result.items() if k in key_set} for result in infer_result]
                    
                    statistics[analyzer_name].append({
                        'version': version,
                        'reports': reports
                    })
                    statistics['summary'][analyzer_name]['total'] += len(reports)
                    statistics['summary'][analyzer_name][version] = len(reports)
                    statistics['summary']['total'] += len(reports)

                    if analyzer_baseline_number is None:
                        analyzer_baseline_number = len(reports)
                
                if analyzer_baseline_number is not None:
                    baseline_reports_number += analyzer_baseline_number

            logger.info(f"Total {statistics['summary']['total'] - baseline_reports_number} reports(without baseline) in {workspace}")

            return statistics
        
        statistics1 = get_statistics_from_workspace(repo_info.workspace)
        statistics2 = get_statistics_from_workspace(repo_info2.workspace)

        # [
        #     {'version': commit['version'], 'reports': [Report1, Report2, ...]},
        #     ......
        # ]
        def versions_and_reports(statistics: list) -> dict:
            versions_and_reports = {}
            first_version = None
            for analyzer in analyzers:
                analyzer_statistics = statistics[analyzer]
                for commit in analyzer_statistics:
                    version = commit['version']
                    if version not in versions_and_reports.keys():
                        versions_and_reports[version] = set()
                    if first_version is None:
                        first_version = version
                    reports_from_this_commit = commit['reports']
                    reports = set()
                    for report in reports_from_this_commit:
                        if isinstance(report, str):
                            report_name = report
                            specific_info = {}
                        else:
                            if "message" in report:
                                # cppcheck report
                                report_name = report["message"]["text"]
                            else:
                                # clang-tidy report
                                report_name = report["file"] + '-' + report["hash"]
                            specific_info = report
                        reports.add(Report(analyzer, version, report_name, specific_info))
                    versions_and_reports[version] = versions_and_reports[version].union(reports)
            return versions_and_reports, first_version
        
        def dump_veen_diagram(versions_and_reports, figure):
            if len(versions_and_reports.keys()) == 0:
                return 
            # Draw Venn diagram
            import matplotlib.pyplot as plt
            from venn import venn

            # 绘制Venn图
            plt.figure()
            venn(versions_and_reports, fmt='{size}', cmap='tab10')
            plt.savefig(figure)
            plt.close()
        
        versions_and_reports1, baseline_version1 = versions_and_reports(statistics1)
        # dump_veen_diagram(versions_and_reports1, f"{repo_info.workspace}/veen.png")
        versions_and_reports2, baseline_version2 = versions_and_reports(statistics2)
        # dump_veen_diagram(versions_and_reports2, f"{repo_info2.workspace}/veen.png")

        def all_reports_from_json(versions_and_reports: dict) -> set:
            reports = set()
            for val in versions_and_reports.values():
                reports = reports.union(val)
            return reports
        
        reports1 = all_reports_from_json(versions_and_reports1)
        reports2 = all_reports_from_json(versions_and_reports2)
        statistics1['summary']['unique'] = len(reports1)
        statistics2['summary']['unique'] = len(reports2)
        for analyzer in analyzers:
            if analyzer in statistics1['summary'].keys():
                statistics1['summary'][analyzer]['uique'] = len([i for i in reports1 if i.analyzer == analyzer])
            
            if analyzer in statistics2['summary'].keys():
                statistics2['summary'][analyzer]['uique'] = len([i for i in reports2 if i.analyzer == analyzer])

        def clang_tidy_diag_distribution(reports):
            kinds = {}
            for report in reports:
                if report.analyzer == 'clang-tidy':
                    kind = report.specific_info['kind']
                    if kind in kinds.keys():
                        kinds[kind] += 1
                    else:
                        kinds[kind] = 1
            return sorted(kinds.items(), key=lambda item: item[1], reverse=True)
        
        kinds1 = clang_tidy_diag_distribution(reports1)
        statistics1['summary']['clang-tidy distribution'] = { kind[0]: kind[1] for kind in kinds1 }
        kinds2 = clang_tidy_diag_distribution(reports2)
        statistics2['summary']['clang-tidy distribution'] = { kind[0]: kind[1] for kind in kinds2 }


        def new_reports(all_reports: set, baseline_reports:set, output_file):
            new_reports = all_reports.difference(baseline_reports)
            logger.info(f"Find {len(new_reports)} new reports in {output_file}")
            with open(output_file, 'w') as f:
                json.dump([i.__to_json__() for i in new_reports], f, indent=3)
            return new_reports

        new_reports1 = new_reports(reports1, versions_and_reports1[baseline_version1], os.path.join(repo_info.workspace, 'new_reports.json'))
        new_reports2 = new_reports(reports2, versions_and_reports2[baseline_version2], os.path.join(repo_info2.workspace, 'new_reports.json'))
        statistics1['summary']['new'] = len(new_reports1)
        statistics2['summary']['new'] = len(new_reports2)

        dir1 = repo_info.workspace
        dir2 = repo_info2.workspace
        diff_json = diff_reports(new_reports1, new_reports2, dir1, dir2)
        with open(os.path.join(repo_info.workspace, "reports_diff.json"), 'w') as f:
            json.dump(diff_json, f, indent=3)
            
        statistics1['summary']['diff'] = 0
        statistics2['summary']['diff'] = 0
        for key in diff_json.keys():
            if key == repo_info.workspace:
                statistics1['summary']['diff'] = len(diff_json[key])
                statistics1['summary']['diff reports'] = diff_json[key]
            elif key == repo_info2.workspace:
                statistics2['summary']['diff'] = len(diff_json[key])
                statistics2['summary']['diff reports'] = diff_json[key]

        with open(os.path.join(repo_info.workspace, 'merged_reports.json'), 'w') as f1, \
            open(os.path.join(repo_info2.workspace, 'merged_reports.json'), 'w') as f2:
            json.dump(statistics1, f1, indent=3)
            json.dump(statistics2, f2, indent=3)

        repo_summary[opts.workspace1] = statistics1['summary']
        repo_summary[opts.workspace2] = statistics2['summary']
        total_summary.append(repo_summary)

        def get_new_num_each_analayzer(new_reports, summary):
            for analyzer in analyzers:
                if f'new {analyzer}' not in summary:
                    summary[f'new {analyzer}'] = 0
                summary[f'new {analyzer}'] += len([i for i in new_reports if i.analyzer == analyzer])

        total_summary[0][opts.workspace1]['total reports'] += statistics1['summary']['total']
        total_summary[0][opts.workspace1]['unique reports'] += statistics1['summary']['unique']
        total_summary[0][opts.workspace1]['new reports'] += statistics1['summary']['new']
        total_summary[0][opts.workspace1]['diff reports'] += statistics1['summary']['diff']
        get_new_num_each_analayzer(new_reports1, total_summary[0][opts.workspace1])

        total_summary[0][opts.workspace2]['total reports'] += statistics2['summary']['total']
        total_summary[0][opts.workspace2]['unique reports'] += statistics2['summary']['unique']
        total_summary[0][opts.workspace2]['new reports'] += statistics2['summary']['new']
        total_summary[0][opts.workspace2]['diff reports'] += statistics2['summary']['diff']
        get_new_num_each_analayzer(new_reports2, total_summary[0][opts.workspace2])

    with open(os.path.join('repos', opts.workspace1 + '_and_' + opts.workspace2 + '.json'), 'w') as f:
        json.dump(total_summary, f, indent=4)

if __name__ == "__main__":
    main(sys.argv[1:])
    
