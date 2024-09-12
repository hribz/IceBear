template <typename T>
void foo(T x) {
    // Example AST node: An integer literal '0'
    int y = 0;
}

void bar() {
    foo(42);    // Instantiates foo<int>
    foo(3.14);  // Instantiates foo<double>
}

class B1 {
public:
    void func() {}
};

class B2: B1 {
public:
    void func() {}
};

class D : public B2 {
    // Example AST node: Reference to func()
    void callFunc() { func(); }
};
