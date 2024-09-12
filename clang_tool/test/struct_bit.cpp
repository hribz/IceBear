struct S1 {
    unsigned int a : 1;
    unsigned int b : 1;
    unsigned int c : 2;
    unsigned int d : 4;

    int e;

    S1(): a(0), b(3), c(0), d(0), e(0) {}
};

int main() {
    struct S1 s1;
    return ((char *)&(s1.e)) - ((char *)&(s1));
}