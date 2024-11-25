output=$(diff test.py test1.py)
if [ $? -eq 1 ]; then
    echo "$output" > diff_info.txt
fi