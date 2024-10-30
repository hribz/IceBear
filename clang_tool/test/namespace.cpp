# ifdef __clang_analyzer__
#define NAMESPACE_START namespace c{
#define NAMESPACE_END }
namespace a { namespace b { namespace c { } using namespace c; }}
# else
#define NAMESPACE_START
#define NAMESPACE_END
#endif


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