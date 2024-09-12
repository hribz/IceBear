template <class T>
void clang_analyzer_dump(T);

int number = 0;
int *number_ptr = &number;

int* const int_nullptr = nullptr;
const int zero = 0;
int zero_ = zero;

struct S1 {
    constexpr static int b=0;
    char * ch;
    int *a = nullptr;
    int d;
    int c;

    S1(): d(0), c(1/d) {
        c = 1/(*ch);
    }
};
const struct S1 s1 = {};
struct S1 s2 = {};

enum counter {
    ling, one, two
};

int foo(int* const ptr = int_nullptr, int div = zero_) {
    clang_analyzer_dump(ptr);
    clang_analyzer_dump(int_nullptr);
    clang_analyzer_dump(s1);
    *ptr = 0;
    // *(s1.a) = 0;
    return 1/div;
}

int main() {
    int *b = &number;
    int c[10];
    struct S1 s3 = S1();
    *(s3.ch) = '\0';
    foo();
    return 0;
}