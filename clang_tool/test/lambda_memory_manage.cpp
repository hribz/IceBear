namespace {
    int main() {
        int n = 0;
        auto func1 = [n](int a){n;};
        n++;
        func1(1);
        auto func2 = func1;
        union {
            int x;
            int y;
        } u;
        auto u1 = u;
        
        return u1.x;
    }
}

