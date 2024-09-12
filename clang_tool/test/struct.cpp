struct S1 {
    int a;
    int b;

    S1() {}

    int func() {
        return a;
    }
};

int main() {
    S1 *s1 = new S1();
    s1->a = 0;
    (*s1).a = 1;
    s1->func();
    return 0;
}