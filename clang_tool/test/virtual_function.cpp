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
    int foo() override {
        return 0;
    }
};

class C2: public Base {
public:
    int foo() override {
        return 0;
    }
};

int main() {
    C1 c1;
    Base *b1 = &c1;
    // CallGraph: main -> Base::foo
    //    CSA:    main -> C1::foo()
    int div = b1->foo();
    c1.foo();

    C2 c2;
    Base *b2 = &c2;
    c2.foo();
    
    // 1 / div;
    // div = Base().foo();
    // div = C1().foo();
    div = 1 / div;
    return 0;
}