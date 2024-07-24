import json
from typing import List, Dict
from dataclasses import dataclass
from dataclass_wizard import fromdict, asdict
from pathlib import Path

@dataclass
class CMakeReply:
    kind: str
    version: Dict
    def __init__(self):
        self.kind = ''
        self.version = {}

@dataclass
class CodeModel(CMakeReply):
    ''' paths
    {
		"build" : "...",
		"source" : "..."
	}
    '''
    paths: Dict
    @dataclass
    class Configurations:
        name: str
        ''' directories
        [
            {
                "source": "...",
                "build": "...",
                ,...,
                "jsonFile": "..."
            }
        ]
        '''
        directories: List[Dict]
        ''' projects
        [
            {
                "name": "...",
                "parentIndex": "...",
                ,...,
                "targetIndexes": "..."
            }
        ]
        '''
        projects: List[Dict]
        ''' targets
        [
            {
                "name": "...",
                "id": "...",
                ,...,
                "jsonFile": "..."
            }
        ]
        '''
        targets: List[Dict]

    configurations: List[Configurations]

    def from_json(self):
        pass


@dataclass
class Directory(CMakeReply):
    ''' paths
    {
		"build" : "...",
		"source" : "..."
	}
    '''
    paths: Dict
    installers: List[Dict]
    ''' backtraceGraph
    {
		"commands" : [...],
		"files" : [...],
        "nodes": [{...}, ..., {...}]
	}
    '''
    backtraceGraph: Dict

    def __init__(self):
        super().__init__()

    def from_json(self):
        pass


@dataclass
class Target(CMakeReply):
    name: str
    id: str
    type: str
    TYPES = ['EXECUTABLE', 'STATIC_LIBRARY', 'SHARED_LIBRARY', 'MODULE_LIBRARY',
                   'OBJECT_LIBRARY', 'INTERFACE_LIBRARY', 'UTILITY']
    backtrace: int
    folder: Dict
    ''' paths
    {
		"build" : "...",
		"source" : "..."
	}
    '''
    paths: Dict
    nameOnDisk: str

    ''' artifacts
    [
		{
			"path" : "lib/libopencv_core.so"
		}
	]
    '''
    artifacts: List[Dict]

    isGeneratorProvided: bool
    install: Dict
    link: Dict
    archive: Dict
    ''' dependencies
    [
		{
			"id" : "ippiw::@5f1c6d7264a9a7781a27"
			"backtrace" : 10,
		}
	]
    '''
    dependencies: List[Dict]
    fileSets: List[Dict]
    ''' sources
    [
        {
			"path" : "modules/core/include/opencv2/core.hpp",
            "compileGroupIndex" : 0,
			"sourceGroupIndex" : 0,
            "isGenerated" : true,
            "fileSetIndex" : 0,
			"backtrace" : 4,
		}
    ]
    '''
    sources: List[Dict]
    ''' sourceGroups
    [
        {
			"name" : "Include\\opencv2",
			"sourceIndexes" : [ 0 ]
		}
    ]
    '''
    sourceGroups: List[Dict]
    ''' compileGroups
    [
        {
			"sourceIndexes": 0,
            "language": "CXX",
            ,...,
            "compileCommandFragments": {
                "fragment" : "..."
            },
            "includes" : [
                {
                    "path" : "...",
                    "isSystem" : true,
                    "backtrace" : 0
                }
            ],
            "defines" : [
                {
                    "define" : "__OPENCV_BUILD=1"
                }
            ]
		}
    ]
    '''
    compileGroups: List[Dict]
    backtraceGraph: Dict
    
    def __init__(self):
        super().__init__()


@dataclass
class Cache(CMakeReply):
    @dataclass
    class Entry:
        name: str
        value: str
        type: str
        properties: List[Dict]
    entries: List[Entry]

    def __init__(self):
        super().__init__()


@dataclass
class CMakeFiles(CMakeReply):
    paths: Dict
    inputs: List[Dict]

    def __init__(self):
        super().__init__()


def main():
    build_dir = Path('/home/xiaoyu/cmake-analyzer/cmake-projects/opencv/build')
    cmake_reply_dir = build_dir / '.cmake/api/v1/reply'
    codemodel = None
    cache = None
    cmake_files = None
    targets = []

    for path in cmake_reply_dir.rglob('*'):
        if path.is_file():
            with open(path.absolute(), 'rb') as f:
                data = json.loads(f.read())
            if path.name.startswith("codemodel"):
                # print(codemodel_data)
                codemodel = fromdict(CodeModel, data)
            elif path.name.startswith("cache"):
                cache = fromdict(Cache, data)
            elif path.name.startswith("cmakeFiles"):
                cmake_files = fromdict(CMakeFiles, data)
            elif path.name.startswith("target"):
                targets.append(fromdict(Target, data))



main()
