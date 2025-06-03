import json
import os
import re


def list_files(directory):
    return [
        file
        for file in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, file))
    ]


if __name__ == "__main__":
    checkers_file = filter(
        lambda x: x.endswith("checkers.json") and not x.startswith("infer"),
        list_files("."),
    )
    preprocessor_matcher = re.compile(r"preprocessor|macro|comment", re.IGNORECASE)
    preprocessor_checkers = {"total checkers": 0, "total enable checkers": 0}

    for file in checkers_file:
        checkers = json.load(open(file, "r"))
        analyzer = checkers["analyzer"]
        preprocessor_checkers[analyzer] = {
            "total checkers": len(checkers["labels"].keys()),
            "total enable checkers": len(
                [v for v in checkers["labels"].values() if "profile:default" in v]
            ),
            "preprocessor checkers": 0,
            "checker list": [],
            "enable checkers": [],
        }
        preprocessor_checkers["total checkers"] += preprocessor_checkers[analyzer][
            "total checkers"
        ]
        preprocessor_checkers["total enable checkers"] += preprocessor_checkers[
            analyzer
        ]["total enable checkers"]

        for checker in checkers["labels"].keys():
            if preprocessor_matcher.search(checker):
                preprocessor_checkers[analyzer]["checker list"].append(checker)
                if "profile:default" in checkers["labels"][checker]:
                    preprocessor_checkers[analyzer]["enable checkers"].append(checker)
        preprocessor_checkers[analyzer]["preprocessor checkers"] = len(
            preprocessor_checkers[analyzer]["checker list"]
        )

    with open("preprocessor.json", "w") as f:
        json.dump(preprocessor_checkers, f, indent=4)
