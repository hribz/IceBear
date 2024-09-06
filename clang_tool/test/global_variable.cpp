template <class T>
void clang_analyzer_dump(T);

int number = 0;
int *number_ptr = &number;

struct S1 {
    char *ch;
    int *a = nullptr;
};

const struct S1 s1 = {};
int* const int_nullptr = nullptr;
const int zero = 1;

int foo(int* const ptr = int_nullptr, int div = zero) {
    clang_analyzer_dump(ptr);
    clang_analyzer_dump(int_nullptr);
    clang_analyzer_dump(s1);
    *ptr = 0;
    *(s1.a) = 0;
    return 1/div;
}

int main() {
    int *b;
    int c[10];
    return foo();
}