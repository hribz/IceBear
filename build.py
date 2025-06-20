import os
import sys
import argparse
import subprocess


def run_cmake_build(llvm_dir, clang_dir, jobs, root_path):
    build_dir = os.path.join(os.path.dirname(root_path), "build")
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    os.chdir(build_dir)

    try:
        cmake_command = ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"]
        if llvm_dir:
            cmake_command.extend(["-DLLVM_DIR=" + llvm_dir])
        if clang_dir:
            cmake_command.extend(["-DClang_DIR=" + clang_dir])

        cmake_script = " ".join(cmake_command)
        print(f"Running CMake: {cmake_script}")
        subprocess.check_call(cmake_command)

        print("Running CMake build...")
        build_command = ["cmake", "--build", ".", "--", "-j", str(jobs)]
        subprocess.check_call(build_command)

    except subprocess.CalledProcessError as e:
        print(f"CMake build failed with error: {e}")
        sys.exit(1)

    finally:
        os.chdir(os.path.dirname(root_path))


def generate_icebear_script(icebear_script_path, root_path):
    current_dir = os.path.dirname(root_path)

    # Check if uv is available and project uses uv
    uv_available = (
        subprocess.run(["which", "uv"], capture_output=True, text=True).returncode == 0
    )
    has_uv_lock = os.path.exists(os.path.join(current_dir, "uv.lock"))

    if uv_available and has_uv_lock:
        script_content = f"""#!/bin/bash
# IceBear - A scheduler for C/C++ static analysis tools
export ICEBEAR_EXEC_DIR="$(pwd)"
(cd "{current_dir}" && uv run icebear "$@")
"""
    else:
        # Fallback to direct Python execution
        script_content = f"""#!/bin/bash
# IceBear - A scheduler for C/C++ static analysis tools
export PYTHONPATH="{current_dir}:$PYTHONPATH"
python {os.path.join(current_dir, 'icebear/__init__.py')} "$@"
"""

    with open(icebear_script_path, "w") as f:
        f.write(script_content)

    os.chmod(icebear_script_path, 0o755)
    print(f"Generated icebear script at: {icebear_script_path}")


def main():
    root_path = os.path.abspath(__file__)

    parser = argparse.ArgumentParser(
        description="Generate icebear script and run CMake build."
    )
    parser.add_argument(
        "--llvm-dir", help="Path to LLVM directory for CMake configuration"
    )
    parser.add_argument(
        "--clang-dir", help="Path to Clang directory for CMake configuration"
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        help="Number of parallel jobs for CMake build",
    )
    args = parser.parse_args()

    run_cmake_build(args.llvm_dir, args.clang_dir, args.jobs, root_path)

    icebear_script_path = os.path.join(os.path.dirname(root_path), "icebear/icebear")
    generate_icebear_script(icebear_script_path, root_path)


if __name__ == "__main__":
    main()
