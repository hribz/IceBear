from collections import defaultdict
import hashlib
import os
from pathlib import Path
import sys
import json
from typing import Dict, Iterable, List, Set
import yaml
from enum import Enum, auto
from pydantic import BaseModel, Field

from IncAnalysis.logger import logger

class HashType(Enum):
    PATH = auto()
    CONTEXT = auto()

hash_type = HashType.PATH
current_version = ""

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

class Report(BaseModel):
    versions: list
    specific_info: dict
    report_hash: str

    def __eq__(self, other):
        if isinstance(other, Report):
            return self.report_hash == other.report_hash
        return False

    def __hash__(self):
        return hash(self.report_hash)

class AllUniqueReports(BaseModel):
    CSA: Dict[str, Report] = Field(default_factory=dict)
    GSA: Dict[str, Report] = Field(default_factory=dict)
    CppCheck: Dict[str, Report] = Field(default_factory=dict)
    ClangTidy: Dict[str, Report] = Field(default_factory=dict)
    new_reports_num: Dict[str, int] = Field(default_factory=lambda: defaultdict(int), exclude=True)

    def get_reports(self, analyzer_name: str) -> Dict[str, Report]:
        return getattr(self, analyzer_name)
    
    def update_reports(self, analyzer_name, specific_info, report_hash) -> int:
        analyzer_reports: Dict[str, Report] = getattr(self, analyzer_name)
        if report_hash in analyzer_reports:
            if current_version not in analyzer_reports[report_hash].versions:
                analyzer_reports[report_hash].versions.append(current_version)
                return 1
            else:
                return 0
        else:
            analyzer_reports[report_hash] = Report(versions=[current_version], specific_info=specific_info, report_hash=report_hash)
            if analyzer_name not in self.new_reports_num:
                self.new_reports_num[analyzer_name] = 0
            self.new_reports_num[analyzer_name] += 1
            return 1

class AnalyzerStatistics(BaseModel):
    total: int = 0
    configs: Dict[str, int] = Field(default_factory=dict)

class Summary(BaseModel):
    total: int = 0
    CSA: AnalyzerStatistics = Field(default_factory=AnalyzerStatistics)
    GSA: AnalyzerStatistics = Field(default_factory=AnalyzerStatistics)
    CppCheck: AnalyzerStatistics = Field(default_factory=AnalyzerStatistics)
    ClangTidy: AnalyzerStatistics = Field(default_factory=AnalyzerStatistics)

class Statistics(BaseModel):
    summary: Summary = Field(default_factory=Summary)
    diff: Summary = Field(default_factory=Summary)
    ClangTidyDistribution: Dict[str, int] = Field(default_factory=dict)

    def update_analyzer_statistics(self, analyzer_name: str, report_num: int, current_version: str):
        getattr(self.summary, analyzer_name).total += report_num
        getattr(self.summary, analyzer_name).configs[current_version] = report_num
        self.summary.total += report_num

    def update_diff_statistics(self, analyzer_name: str, new_reports_count: int, current_version: str):
        getattr(self.diff, analyzer_name).total += new_reports_count
        getattr(self.diff, analyzer_name).configs[current_version] = new_reports_count
        self.diff.total += new_reports_count

    def update_clang_tidy_distribution(self, distribution: Dict[str, int]):
        self.ClangTidyDistribution = distribution

all_unique_reports: AllUniqueReports
statistics: Statistics

def parse_yaml(result_file, analyzer) -> int:
    if not os.path.exists(result_file):
        return 0
    if os.path.getsize(result_file) == 0:
        return 0
    with open(result_file, 'r') as f:
        try:
            report = yaml.safe_load(f)
        except Exception as e:
            logger.info(e)
            return 0
    report_num = 0
    diagnostics = report['Diagnostics']
    for diagnostic in diagnostics:
        file = diagnostic['DiagnosticMessage']['FilePath']
        offset = diagnostic['DiagnosticMessage']['FileOffset'] if hash_type == HashType.CONTEXT else "-"
        message = diagnostic['DiagnosticMessage']['Message']
        specific_info = {
            "DiagnosticName": diagnostic['DiagnosticName'],
            "DiagnosticMessage": {
                "FilePath": file,
                "Offset": offset,
                "Message": message,
            },
            "Level": diagnostic['Level']
        }
        report_hash = dict_hash(specific_info)
        report_num += all_unique_reports.update_reports(analyzer, specific_info, report_hash)
    return report_num

def parse_sarif(result_file, analyzer) -> int:
    if not os.path.exists(result_file):
        return 0
    if os.path.getsize(result_file) == 0:
        return 0
    with open(result_file, 'r') as f:
        try:
            sarif_json = json.load(f)
        except Exception as e:
            logger.info(f"{result_file} is not sarif format, please check gsa running status.")
            return 0
        report_num = 0
        results = sarif_json["runs"][0]["results"]
        for result in results:
            if analyzer == 'GSA' and not result['ruleId'].startswith('-Wanalyzer'):
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
            specific_info = {
                "ruleId": result['ruleId'],
                "level": result['level'],
                "message": result['message']['text'],
                "file": file,
                "region": region
            }
            report_hash = dict_hash(specific_info)
            report_num += all_unique_reports.update_reports(analyzer, specific_info, report_hash)
    return report_num

analyzers = ['CSA', 'GSA', 'CppCheck']

def get_statistics_from_workspace(workspace, inc):
    for analyzer_name in analyzers:
        analyzer_path = os.path.join(workspace, analyzer_name)
        reports_path = os.path.join(analyzer_path, f'{inc}-reports')
        if not os.path.exists(reports_path):
            continue

        output_path = os.path.join(reports_path, current_version)    
        report_num = 0

        if analyzer_name.endswith('CSA'):
            if not os.path.exists(output_path):
                continue
            for report in list_files(output_path):
                specific_info = {
                    "file": os.path.dirname('/'+report),
                    "report": os.path.join(output_path, report)
                }
                report_hash = os.path.basename(report)
                report_num += all_unique_reports.update_reports(analyzer_name, specific_info, report_hash)
        elif analyzer_name.endswith('ClangTidy'):
            if not os.path.exists(output_path):
                continue
            for file in list_files(output_path):
                yaml_file = os.path.join(output_path, file)
                report_num = parse_yaml(yaml_file, analyzer_name)
        elif analyzer_name.endswith('CppCheck'):
            result_file = os.path.join(output_path, 'result.json')
            report_num = parse_sarif(result_file, analyzer_name)
        elif analyzer_name.endswith('GSA'):
            if not os.path.exists(output_path):
                continue
            for file in list_files(output_path):
                sarif_file = os.path.join(output_path, file)
                report_num += parse_sarif(sarif_file, analyzer_name)

        statistics.update_analyzer_statistics(analyzer_name, report_num, current_version)
    
    if 'ClangTidy' in analyzers:
        kinds = {}
        for report in all_unique_reports.get_reports('ClangTidy').values():
            kind = report.specific_info['DiagnosticName']
            if kind in kinds.keys():
                kinds[kind] += 1
            else:
                kinds[kind] = 1
        sorted_kinds = sorted(kinds.items(), key=lambda item: item[1], reverse=True)
        statistics.update_clang_tidy_distribution({kind[0]: kind[1] for kind in sorted_kinds})

def postprocess_workspace(workspace, this_version, hash_ty, inc, output_news=True):
    global hash_type, current_version, all_unique_reports, statistics
    logger.info("[Postprocessing Reports]")
    current_version = this_version
    hash_type = HashType.CONTEXT if hash_ty == 'context' else HashType.PATH

    reports_summary_file = os.path.join(workspace, f'reports_summary_{inc}.json')
    if os.path.exists(reports_summary_file):
        statistics = Statistics(**json.load(open(reports_summary_file, 'r')))
    else:
        statistics = Statistics()
    unique_reports_file = os.path.join(workspace, f'unique_reports_{inc}.json')
    if os.path.exists(unique_reports_file):
        all_unique_reports = AllUniqueReports(**json.load(open(unique_reports_file, 'r')))
    else:
        all_unique_reports = AllUniqueReports()

    get_statistics_from_workspace(workspace, inc)

    if output_news:
        with open(unique_reports_file, 'w') as f:
            json.dump(all_unique_reports.model_dump(), f, indent=3)

        for analyzer_name in analyzers:
            statistics.update_diff_statistics(
                analyzer_name, 
                all_unique_reports.new_reports_num[analyzer_name],
                this_version
            )

    with open(reports_summary_file, 'w') as f:
        json.dump(statistics.model_dump(), f, indent=3)