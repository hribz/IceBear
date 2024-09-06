template <typename Op>
int generic_sum(int const *v, Op op, int len) {
    int ret = v[0];
    for (int i = 1; i < len; i++) {
        ret = op(ret, v[i]);
    }
    return ret;
}

int main() {
    int v[5] = {1,2,3,4,5};

    int s1 = generic_sum(v, [](int a, int b) {
        return a+b;
    }, 5);
    int s2 = generic_sum(v, [](int a, int b) {
        return a*b;
    }, 5); 
    
    return 0;
}