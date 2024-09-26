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
    // CallGraph: main -> Base::foo
    //    CSA:    main -> C1::foo()
    int div = b1->foo();
    // 1 / div;
    // div = Base().foo();
    // div = C1().foo();
    div = 1 / div;
    return 0;
}