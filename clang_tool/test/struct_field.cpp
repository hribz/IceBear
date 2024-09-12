// 内存布局与语言本身无关，因此CSA不会考虑内存布局

struct Example1 {
    char a;   // 1 byte
    int b;    // 4 bytes
    char c;   // 1 byte
};

// Example1 的内存布局:
// [ a(1 byte) | padding(3 bytes) | b(4 bytes) | c(1 byte) | padding(3 bytes) ]

struct Example2 {
    char a;   // 1 byte
    char c;   // 1 byte
    int b;    // 4 bytes
};

// Example2 的内存布局:
// [ a(1 byte) | c(1 byte) | padding(2 bytes) | b(4 bytes) ]

int main() {
    Example1 e1;
    Example2 e2;
    int test = &(e1.c) - &(e1.a);
    1/(test - 8);
    return test;
}