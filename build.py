import os
import sys
import argparse
import subprocess

def run_cmake_build(llvm_dir, jobs):
    """
    运行 CMake 构建
    """
    # 创建 build 目录
    build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build')
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    # 进入 build 目录
    os.chdir(build_dir)

    try:
        # 运行 CMake 配置
        cmake_command = ['cmake', '..', '-DCMAKE_BUILD_TYPE=Release']
        if llvm_dir:
            cmake_command.extend(['-DLLVM_DIR=' + llvm_dir])
        
        print("Running CMake configuration...")
        subprocess.check_call(cmake_command)

        # 运行 CMake 构建
        print("Running CMake build...")
        build_command = ['cmake', '--build', '.', '--', '-j', str(jobs)]
        subprocess.check_call(build_command)

    except subprocess.CalledProcessError as e:
        # 如果 CMake 配置或构建失败，输出错误信息并终止程序
        print(f"CMake build failed with error: {e}")
        sys.exit(1)

    finally:
        # 返回项目根目录
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

def generate_icebear_script(icebear_script_path):
    """
    生成 icebear 脚本
    """
    # 获取当前脚本所在的目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 生成 icebear 脚本内容
    script_content = f"""#!/bin/bash

# 设置 PYTHONPATH（如果需要）
export PYTHONPATH=$PYTHONPATH:{current_dir}

# 运行 IceBear.py 并传递所有参数
python {os.path.join(current_dir, 'IceBear.py')} "$@"
"""

    # 将内容写入 icebear 脚本
    with open(icebear_script_path, 'w') as f:
        f.write(script_content)

    # 赋予脚本可执行权限
    os.chmod(icebear_script_path, 0o755)

    print(f"Generated icebear script at: {icebear_script_path}")

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Generate icebear script and run CMake build.')
    parser.add_argument('--llvm-dir', help='Path to LLVM directory for CMake configuration')
    parser.add_argument('-j', '--jobs', type=int, default=1, help='Number of parallel jobs for CMake build')
    args = parser.parse_args()

    # 运行 CMake 构建
    run_cmake_build(args.llvm_dir, args.jobs)

    # 生成 icebear 脚本
    icebear_script_path = os.path.join(os.path.dirname(__file__), 'icebear')
    generate_icebear_script(icebear_script_path)

if __name__ == "__main__":
    main()