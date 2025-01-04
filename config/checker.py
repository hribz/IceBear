import json
import os
import re

def list_files(directory):
    return [file for file in os.listdir(directory) if os.path.isfile(os.path.join(directory, file))]
            

if __name__ == '__main__':
    checkers_file = filter(lambda x: x.endswith('checkers.json'), list_files('.'))
    preprocessor_matcher = re.compile(r'preprocessor|macro|comment', re.IGNORECASE)
    preprocessor_checkers = {
        'total checkers': 0
    }

    for file in checkers_file:
        checkers = json.load(open(file, 'r'))
        analyzer = checkers['analyzer']
        preprocessor_checkers[analyzer] = {
            'total checkers': len(checkers['labels'].keys()),
            'preprocessor checkers': 0,
            'checker list': []
        }
        preprocessor_checkers['total checkers'] += len(checkers['labels'].keys())

        for checker in checkers['labels'].keys():
            if preprocessor_matcher.search(checker):
                preprocessor_checkers[analyzer]['checker list'].append(checker)
        preprocessor_checkers[analyzer]['preprocessor checkers'] = len(preprocessor_checkers[analyzer]['checker list'])
    

    with open('preprocessor.json', 'w') as f:
        json.dump(preprocessor_checkers, f, indent=4)