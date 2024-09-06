class Base {
public:
    virtual int foo() {
        return 0;
    }
};

class C1: Base {
public:
    int foo() {
        return 1;
    }
};

int main() {
    C1 b1;
    return b1.foo();
}