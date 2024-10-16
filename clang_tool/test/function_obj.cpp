template <typename Op>
int generic_sum(int const *v, Op op, int len) {
    int ret = v[0];
    for (int i = 1; i < len; i++) {
        ret = op(ret, v[i]);
    }
    return ret;
}

auto func = [](int x) {
    return x;
};

int main() {
    int v[5] = {1,2,3,4,5};

    auto func1 = [](int a, int b) {
        return a+b;
    };

    auto func2 = [](auto x, auto y) {
        return x+y;
    };

    // {
    //     func1(1, 2);
    //     func(1);
    // }

    // func2(1, 2);

    int s1 = generic_sum(v, [](int a, int b) {
        return a+b;
    }, 5);
    int s2 = generic_sum(v, func2, 5); 
    
    return 0;
}