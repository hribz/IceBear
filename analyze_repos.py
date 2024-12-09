import subprocess
import json
from pathlib import Path

repo_list = 'repos/repos.json'

with open(repo_list, 'r') as f:
    repo_json = json.load(f)
CWD = Path('.').absolute()

for repo in repo_json:
    repo_name = repo["project"]
    if repo_name == 'grpc/grpc':
        # grpc has been analyzed.
        continue
    repo_dir = CWD / f"repos/{repo_name}"
    abs_repo_path = str(repo_dir.absolute())

    try:
        make_clean = f"make -C {abs_repo_path}_build clean &> /dev/null"
        p = subprocess.run(make_clean, shell=True, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        pass  # 忽视错误，继续执行后续代码
    try:
        inline_cmd = f"time python repo_controller.py --inc=inline --analyze=no-ctu -j24 --repo='{repo_name}' &> tmp_inline.log"
        p = subprocess.run(inline_cmd, shell=True, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        pass  # 忽视错误，继续执行后续代码

    try:
        make_clean = f"make -C {abs_repo_path}_build clean &> /dev/null"
        p = subprocess.run(make_clean, shell=True, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        pass  # 忽视错误，继续执行后续代码
    try:
        func_cmd = f"time python repo_controller.py --inc=func --analyze=no-ctu -j24 --repo='{repo_name}' &> tmp_func.log"
        p = subprocess.run(func_cmd, shell=True, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        pass  # 忽视错误，继续执行后续代码
    
    try:
        make_clean = f"make -C {abs_repo_path}_build clean &> /dev/null"
        p = subprocess.run(make_clean, shell=True, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        pass  # 忽视错误，继续执行后续代码
    try:
        file_cmd = f"time python repo_controller.py --inc=file --analyze=no-ctu -j24 --repo='{repo_name}' &> tmp_file.log"
        p = subprocess.run(file_cmd, shell=True, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        pass  # 忽视错误，继续执行后续代码