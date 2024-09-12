int const ZERO = 0;
int const ONE = ZERO + 1;
int two = ONE + 1;
int *ptr = nullptr;

class C1 {
public:
    class C2 {
        public:
        constexpr static int aa = 0;
    };
    constexpr static int const a = 0;
    int b = a;
    int c = ONE;

    C1(): b(a), c(a) {}
    C1(int arg): b(arg), c(a) {}

    int func(int arg1 = ONE,
        int arg2 = two) {
        int ret = ONE;
        *(ptr) += ONE + this->a;
        // int const b = 1/(this->a);
        return ret;
    }
};

namespace my_space {
    namespace inner {
        int const a = 0;
    }
}

int main() {
    // my_space::inner::a;
    // two;
    // {ONE;}
    // C1 c1{ONE};
    // c1.func();
    // c1.func(100);
    // C1 *c2 = new C1(ONE);
    // two++;
    // two = 1/my_space::inner::a;
    C1::C2 c12;
    two = 1/c12.aa;
    return 0;
}