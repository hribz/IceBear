#include <algorithm>
#include <string>

int main () {
    union {
        int x;
    } u;
    return u.x;
}