#!/bin/bash

# 比较两个文件夹的差异，并输出到 diff_output.txt
diff -r $1 $2 > diff_output.txt

# 找出同名文件的差异行，并输出到 same_file_diff.txt
grep "diff -r" diff_output.txt > same_file_diff.txt

# 获取两个文件夹中的所有文件名列表
find $1 -type f | sed 's|preprocess/||' | sort > build1_files.txt
find $2 -type f | sed 's|preprocess/||' | sort > build2_files.txt

# 找出不同名文件，并输出到 different_files.txt
comm -3 build1_files.txt build2_files.txt > different_files.txt
