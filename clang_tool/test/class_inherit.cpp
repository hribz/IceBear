template<typename T>
class C1 {
public:
    T parent_field;
    virtual void func() {}
};

class C2: public C1<int> {
public:
    int child_field;
    void func() { }
};

int foo() {
    return 0;
}

int main() {
    C2 c2;
    c2.func();
    auto lamda = [] () {return 0;};
    c2.parent_field = 10;
    c2.child_field = 20;
    return 0;
}