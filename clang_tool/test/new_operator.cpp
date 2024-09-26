class C1 {
    int a;
    int b;
};

int main() {
    C1 *c1 = new C1;
    delete c1;
    return 0;
}