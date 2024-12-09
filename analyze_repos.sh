time python repo_controller.py --inc=inline --analyze=no-ctu -j24 &> tmp_inline.log

time python repo_controller.py --inc=func --analyze=no-ctu -j24 &> tmp_func.log

time python repo_controller.py --inc=file --analyze=no-ctu -j24 &> tmp_file.log