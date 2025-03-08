import hashlib
import os
from pathlib import Path
import sys
import json
import yaml

from IncAnalysis.logger import logger

def list_files(directory: str):
    if not os.path.exists(directory):
        return []
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def list_dir(directory: str, filt_set=None):
    if not os.path.exists(directory):
        return []
    dir_list = [f for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]
    if filt_set:
        return list(filter(lambda x: (x in filt_set), dir_list))
    else:
        return dir_list

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

analyzers = ['clang-tidy', 'cppcheck', 'csa']

def get_statistics_from_workspace(workspace):
    analyzers_floder = [os.path.join(workspace, analyzer) for analyzer in list_dir(workspace, analyzers)]
    
    statistics = {
        "summary": {
            "total": 0,
            "new": 0
        }
    }
    for k in analyzers:
        statistics[k] = [] # type: ignore
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
        
        def get_versions(workspace, analyzer):
            origin_statistics_file = os.path.join(workspace, 'reports_statistics.json')
            if os.path.exists(origin_statistics_file):
                with open(origin_statistics_file, 'r') as f:
                    info = json.load(f)
                    return [i['version'] for i in info[analyzer]]
            return None

        versions = get_versions(workspace, analyzer_to_class[analyzer_name])
        if versions is None:
            versions = sorted(list_dir(reports_path))
        statistics['summary'][analyzer_name] = { # type: ignore
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
                result_file = os.path.join(output_path, 'result.json')
                if not os.path.exists(result_file):
                    continue
                if os.path.getsize(result_file) == 0:
                    continue
                with open(result_file, 'r') as f:
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
            
            statistics[analyzer_name].append({ # type: ignore
                'version': version,
                'reports': reports
            })
            statistics['summary'][analyzer_name]['total'] += len(reports) # type: ignore
            statistics['summary'][analyzer_name][version] = len(reports) # type: ignore
            statistics['summary']['total'] += len(reports)

            if analyzer_baseline_number is None:
                analyzer_baseline_number = len(reports)
        
        if analyzer_baseline_number is not None:
            baseline_reports_number += analyzer_baseline_number

    return statistics

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

def get_versions_and_reports(statistics):
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

def postprocess_workspace(workspace, this_versions, output_news=True):
    logger.info("[Postprocessing Reports]")
    statistics = get_statistics_from_workspace(workspace=workspace)
    
    versions_and_reports, baseline_version = get_versions_and_reports(statistics)

    def old_and_now_reports_from_json(versions_and_reports: dict, this_versions):
        old_reports = set()
        now_reports = set()
        for version, val in versions_and_reports.items():
            if version in this_versions:
                now_reports = now_reports.union(val)
            else:
                old_reports = old_reports.union(val)
        return old_reports, now_reports
    
    old_reports, now_reports = old_and_now_reports_from_json(versions_and_reports, this_versions)
    reports = old_reports.union(now_reports)

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
    
    kinds = clang_tidy_diag_distribution(reports)
    statistics['summary']['clang-tidy distribution'] = { kind[0]: kind[1] for kind in kinds } # type: ignore
    
    def new_reports(old_reports: set, now_reports:set, output_file, now_file):
        new_reports = now_reports.difference(old_reports)
        with open(output_file, 'w') as f:
            json.dump([i.__to_json__() for i in new_reports], f, indent=3)

        with open(now_file, 'w') as f:
            json.dump([i.__to_json__() for i in now_reports], f, indent=3)
        return new_reports

    if output_news:
        new_reports1 = new_reports(old_reports, now_reports
                                , os.path.join(workspace, 'new_reports.json')
                                , os.path.join(workspace, 'reports.json'))
        statistics['summary']['new'] = len(new_reports1)

    with open(os.path.join(workspace, 'all_reports.json'), 'w') as f:
        json.dump(statistics, f, indent=3)