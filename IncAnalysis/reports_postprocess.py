from collections import defaultdict
import hashlib
import os
from pathlib import Path
import sys
import json
import yaml
from enum import Enum, auto

from IncAnalysis.logger import logger

class HashType(Enum):
    PATH = auto()
    CONTEXT = auto()

hash_type = HashType.PATH

def list_files(directory: str):
    if not os.path.exists(directory):
        return []
    return [str(p.relative_to(directory)) for p in Path(directory).rglob("*") if p.is_file()]

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

def parse_yaml(result_file):
    if not os.path.exists(result_file):
        return None
    if os.path.getsize(result_file) == 0:
        return None
    unique_reports = dict()
    with open(result_file, 'r') as f:
        try:
            report = yaml.safe_load(f)
        except Exception as e:
            logger.info(e)
            return None
    diagnostics = report['Diagnostics']
    for diagnostic in diagnostics:
        file = diagnostic['DiagnosticMessage']['FilePath']
        offset = diagnostic['DiagnosticMessage']['FileOffset'] if hash_type == HashType.CONTEXT else "-"
        message = diagnostic['DiagnosticMessage']['Message']
        report = {
            "specific_info": {
                "DiagnosticName": diagnostic['DiagnosticName'],
                "DiagnosticMessage": {
                    "FilePath": file,
                    "Offset": offset,
                    "Message": message,
                },
                "Level": diagnostic['Level']
            }
        }
        report_hash = dict_hash(report)
        report['hash'] = report_hash # type: ignore
        unique_reports[report_hash] = report
    return unique_reports


def parse_sarif(result_file, is_gsa=False):
    if not os.path.exists(result_file):
        return None
    if os.path.getsize(result_file) == 0:
        return None
    unique_reports = dict()
    with open(result_file, 'r') as f:
        try:
            sarif_json = json.load(f)
        except Exception as e:
            logger.info(f"{result_file} is not sarif format, please check gsa running status.")
            return None
        results = sarif_json["runs"][0]["results"]
        for result in results:
            if is_gsa and not result['ruleId'].startswith('-Wanalyzer'):
                continue
            message = result['message']['text']
            file = 'UNKNOWN'
            region = "-"
            # Find file path in artifacts
            if 'artifacts' in sarif_json["runs"][0]:
                file = sorted([artifact['location']['uri'] for artifact in sarif_json["runs"][0]['artifacts'] 
                              if 'location' in artifact and 'uri' in artifact['location']])
            elif 'physicalLocation' in result['locations'][-1]:
                file = sorted([i['physicalLocation']['artifactLocation']['uri'] for i in result['locations'] if 'physicalLocation' in i])
            if hash_type == HashType.CONTEXT:
                if 'physicalLocation' in result['locations'][-1] and 'region' in result['locations'][-1]['physicalLocation']:
                    region = {
                        'file': result['locations'][-1]['physicalLocation']['artifactLocation']['uri'],
                        'region': result['locations'][-1]['physicalLocation']['region']
                    }
            if hash_type == HashType.PATH and message.rfind("at line") != -1:
                # Ignore line number if under context-free mode.
                result['message']['text'] = message[:message.rfind("at line")]
            report = {
                "specific_info": {
                    "ruleId": result['ruleId'],
                    "level": result['level'],
                    "message": result['message']['text'],
                    "file": file,
                    "region": region
                }
            }
            report_hash = dict_hash(report)
            report['hash'] = report_hash # type: ignore
            unique_reports[report_hash] = report
    return unique_reports

analyzers = ['CSA', 'GSA', 'ClangTidy', 'CppCheck']

def get_statistics_from_workspace(workspace, this_version, inc):
    analyzers_folder = [os.path.join(workspace, analyzer) for analyzer in list_dir(workspace, analyzers)]
    
    all_reports_file= os.path.join(workspace, f'all_reports_{inc}.json')
    if os.path.exists(all_reports_file):
        statistics = json.load(open(all_reports_file, 'r'))
    else:
        statistics = {
            "summary": {
                "total": 0,
            },
            "diff": {
                "total": 0
            }
        }
    for k in analyzers:
        if k not in statistics:
            statistics[k] = [] # type: ignore

    for analyzer in analyzers_folder:
        reports_dir = f'{inc}-reports'
        reports_path = os.path.join(analyzer, reports_dir)
        analyzer_name = os.path.basename(analyzer)
        if analyzer_name not in analyzers:
            continue

        if analyzer_name not in statistics['summary']:
            statistics['summary'][analyzer_name] = { # type: ignore
                "total": 0
            }

        output_path = os.path.join(reports_path, this_version)
        reports = []
        if analyzer.endswith('CSA'):
            if not os.path.exists(output_path):
                continue
            for report in list_files(output_path):
                reports.append({
                    "specific_info": {
                        "file": os.path.dirname('/'+report),
                        "report": os.path.join(output_path, report)
                    },
                    "hash": os.path.basename(report)
                })
        elif analyzer.endswith('ClangTidy'):
            if not os.path.exists(output_path):
                continue
            unique_reports = dict()
            for file in list_files(output_path):
                yaml_file = os.path.join(output_path, file)
                yaml_result = parse_yaml(yaml_file)
                if yaml_result is None:
                    continue
                unique_reports.update(yaml_result)
            reports = list(unique_reports.values())
        elif analyzer.endswith('CppCheck'):
            result_file = os.path.join(output_path, 'result.json')
            sarif_result = parse_sarif(result_file)
            if sarif_result is None:
                continue
            reports = list(sarif_result.values())
        elif analyzer.endswith('Infer'):
            if not os.path.exists(os.path.join(output_path, 'report.json')):
                continue
            with open(os.path.join(output_path, 'report.json'), 'r') as f:
                infer_result = json.load(f)
                key_set = {'bug_type', 'qualifier', 'severity', 'category', 'procedure', 'file', 'key', 'bug_type_hum'}
                reports = [{k: v for k, v in result.items() if k in key_set} for result in infer_result]
        elif analyzer.endswith('GSA'):
            if not os.path.exists(output_path):
                continue
            unique_reports = dict()
            for file in list_files(output_path):
                sarif_file = os.path.join(output_path, file)
                sarif_result = parse_sarif(sarif_file, is_gsa=True)
                if sarif_result is None:
                    continue
                sarif_result = {k: v for k, v in sarif_result.items() 
                              if v['specific_info']['ruleId'].startswith('-Wanalyzer')}
                unique_reports.update(sarif_result)
            reports = list(unique_reports.values())

        if len(statistics[analyzer_name]) > 0 and this_version == statistics[analyzer_name][-1]['version']: # type: ignore
            old_reports = statistics[analyzer_name][-1]['reports'] # type: ignore
            statistics['summary'][analyzer_name]['total'] -= len(old_reports) # type: ignore
            statistics['summary'][analyzer_name][this_version] -= len(old_reports) # type: ignore
            statistics['summary']['total'] -= len(old_reports)
            statistics[analyzer_name][-1] = { # type: ignore
                'version': this_version,
                'reports': reports
            }
        else:
            statistics[analyzer_name].append({ # type: ignore
                'version': this_version,
                'reports': reports
            })
        statistics['summary'][analyzer_name]['total'] += len(reports) # type: ignore
        statistics['summary'][analyzer_name][this_version] = len(reports) # type: ignore
        statistics['summary']['total'] += len(reports)

    return statistics

class Report:
    def __init__(self, analyzer, version, specific_info, report_hash):
        self.analyzer = analyzer
        self.version = version
        self.specific_info = specific_info
        self.report_hash = report_hash

    def __eq__(self, other):
        if isinstance(other, Report):
            return self.report_hash == other.report_hash
        return False

    def __hash__(self):
        return hash(self.report_hash)
    
    def __to_json__(self):
        return {
            "version": self.version,
            "specific info": self.specific_info,
            "hash": self.report_hash
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
                reports.add(Report(analyzer, version, report['specific_info'], report['hash']))
            versions_and_reports[version] = versions_and_reports[version].union(reports)
    return versions_and_reports, first_version

def postprocess_workspace(workspace, this_version, hash_ty, inc, output_news=True):
    global hash_type
    logger.info("[Postprocessing Reports]")
    hash_type = HashType.CONTEXT if hash_ty == 'context' else HashType.PATH
    statistics = get_statistics_from_workspace(workspace, this_version, inc)
    
    versions_and_reports, baseline_version = get_versions_and_reports(statistics)

    def old_and_now_reports_from_json(versions_and_reports: dict, this_version):
        old_reports = set()
        now_reports = set()
        for version, val in versions_and_reports.items():
            if version == this_version:
                now_reports = now_reports.union(val)
            else:
                old_reports = old_reports.union(val)
        return old_reports, now_reports
    
    old_reports, now_reports = old_and_now_reports_from_json(versions_and_reports, this_version)
    reports = old_reports.union(now_reports)

    def clang_tidy_diag_distribution(reports):
        kinds = {}
        for report in reports:
            if report.analyzer == 'ClangTidy':
                kind = report.specific_info['DiagnosticName']
                if kind in kinds.keys():
                    kinds[kind] += 1
                else:
                    kinds[kind] = 1
        return sorted(kinds.items(), key=lambda item: item[1], reverse=True)
    
    kinds = clang_tidy_diag_distribution(reports)
    statistics['summary']['ClangTidy Distribution'] = { kind[0]: kind[1] for kind in kinds } # type: ignore
    
    def new_reports(old_reports: set, now_reports:set, output_file, now_file):
        new_reports = now_reports.difference(old_reports)
        classified_new_reports = defaultdict(list)
        for report in new_reports:
            classified_new_reports[report.analyzer].append(report.__to_json__())

        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            all_new_reports = json.load(open(output_file, 'r'))
        else:
            all_new_reports = defaultdict(list)
        for analyzer in classified_new_reports.keys():
            all_new_reports[analyzer].extend(classified_new_reports[analyzer])
        with open(output_file, 'w') as f:
            json.dump(all_new_reports, f, indent=3)

        with open(now_file, 'w') as f:
            json.dump([i.__to_json__() for i in now_reports], f, indent=3)
        return classified_new_reports

    if output_news:
        classified_new_reports = new_reports(old_reports, now_reports
                                , os.path.join(workspace, f'new_reports_{inc}.json')
                                , os.path.join(workspace, f'reports_{inc}.json'))
        statistics['diff']['total'] = 0
        for analyzer_name in analyzers:
            if analyzer_name not in statistics['diff']:
                statistics['diff'][analyzer_name] = { # type: ignore
                    "total": 0
                }
            statistics['diff'][analyzer_name]['total'] += len(classified_new_reports[analyzer_name]) # type: ignore
            statistics['diff'][analyzer_name][this_version] = len(classified_new_reports[analyzer_name]) # type: ignore
            statistics['diff']['total'] += statistics['diff'][analyzer_name]['total'] # type: ignore

    with open(os.path.join(workspace, f'all_reports_{inc}.json'), 'w') as f:
        json.dump(statistics, f, indent=3)