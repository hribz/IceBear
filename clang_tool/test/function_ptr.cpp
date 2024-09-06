class Sum {
public:
    int (*op)(int, int);
};

int add(int a, int b) {
    return a+b;
}

int main() {
    Sum s1;
    s1.op = add;
    return s1.op(1,2);
}