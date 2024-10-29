#define NAMESPACE_START namespace c{
#define NAMESPACE_END }

namespace a { namespace b { namespace c { } using namespace c; }}

namespace a {
namespace b {
NAMESPACE_START
int foo() {
    return 1;
}

int main() {
    foo();
    return 0;
}
NAMESPACE_END
}
}