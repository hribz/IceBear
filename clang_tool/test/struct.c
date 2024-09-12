struct S1 {
    int a;
    int b;
    
    int (*func)(int );
};

int print(int a) {
    return a;
}

int main() {
    struct S1 s1;
    s1.a = 1;
    s1.func = print;
    s1.func(s1.a);
    return 0;
}