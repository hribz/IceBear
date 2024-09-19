class Base {
private:
    int a;
    int b;
public:
    virtual int foo() {
        return 1;
    }
};

class C1: public Base {
public:
    int foo() {
        return 0;
    }
};

int main() {
    C1 c1;
    Base *b1 = &c1;
    int div = b1->foo();
    // 1 / div;
    // div = Base().foo();
    // div = C1().foo();
    1 / div;
    return 0;
}