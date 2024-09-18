union U1{
    int *a;
    char *b;
};

U1 u1{nullptr};

int main() {
    u1.a = nullptr;
    *(u1.b) = '\0';
    return 0;
}