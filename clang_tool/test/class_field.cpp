struct S1 {
    char *ch;
    int * const a;
    int const b = 0;

    // S1(): a(nullptr), b(0) { }
};

S1 s1{};
// S1 s2{};
int *ptr = nullptr;

class Example {
    int value;
public:
    Example(int v) : value(v) {}
    int& getValue() const { return const_cast<int&>(value); }  // 去掉const性
};
Example const example{s1.b};
float const f = (float)(s1.b);

int const ONE = 10;

int main() {
    *(ptr) = 0;
    1 / s1.b;
    Example ex(5);
    ex.getValue() = 10;  // 可以通过getValue修改成员变量
    return 0;
}