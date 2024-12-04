make -C /home/xiaoyu/cmake-analyzer/IncAnalyzer/repos/grpc/grpc_build clean &> /dev/null
time python repo_controller.py --inc=inline --analyze=no-ctu -j24 --repo='grpc/grpc' &> tmp_inline.log

make -C /home/xiaoyu/cmake-analyzer/IncAnalyzer/repos/grpc/grpc_build clean &> /dev/null
time python repo_controller.py --inc=func --analyze=no-ctu -j24 --repo='grpc/grpc' &> tmp_func.log

make -C /home/xiaoyu/cmake-analyzer/IncAnalyzer/repos/grpc/grpc_build clean &> /dev/null
time python repo_controller.py --inc=file --analyze=no-ctu -j24 --repo='grpc/grpc' &> tmp_file.log