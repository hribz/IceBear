class C1;

class C2 {
public:
    C1 *c1;

    int foo(int *);
};

class C1 {
public:
    int a;
};

struct S1 {
    char *ch;
    int *a;

    S1();
};

S1::S1(): a(nullptr) {}

const S1 s1;

// member can't redeclared out of class scope
// int C2::foo(int *);

int C2::foo(int *ptr = s1.a) {
    this->c1 = (C1 *)new C1;
    this->c1->a = 100;
    *ptr = 0;
    int ret = this->c1->a;
    delete this->c1;
    return ret;
}

// redecleared in same/outer scope is valid
// int main();

int main() {
    C2 c2;
    int *b;
    int c[10];
    struct S1 s2;
    return c2.foo(s2.a);
}