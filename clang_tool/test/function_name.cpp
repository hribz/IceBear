// Some case for inconsistency between function name in .fs and .cg file.
#include <exception>
#include <functional>
#include <string>
#include <thread>
#include <vector>

class Parent {
public:
  class C1 {
  public:
    // case 1:
    // C1's copy ctor declared at here, argument `other` has type `const C1 &`
    // in writing.
    C1(const C1 &other);

    C1(int *other) : a(other) {}

    int *a;
  };
};

// case 1:
// C1's copy ctor's redeclared at here, argument `other` has type `const
// Parent::C1 &` in writing. The difference between argument's type in writing
// leads to inconsistency between function name in .fs and .cg file, because
// they found different declarations. So it's neccessary to found the same
// declaration by use `GetCanonicalDecl()`.
Parent::C1::C1(const Parent::C1 &other) : a(other.a) {}

using namespace std;

class TokenizeError : public exception {
public:
    explicit TokenizeError(const string &msg = "tokenize error") : msg_(msg) {}
    ~TokenizeError() throw() {}
    virtual const char *what() const throw() { return msg_.c_str(); }

private:
    string msg_;
};

// case 3:
// Dtors will be invoked automatically and won't appear in AST, but CSA will consider them.
// So there is no dtor in CallGraph, and we need to add them to CallGraph.
class raii {
public:
    raii(int i): a({i}) {}
    std::vector<int> a;
};

void ParseString(string *tok) {
    try {
        char ch = (*tok)[0];
        if (ch == '\"') {
            *tok += '\"';
        } else {
            // case 2:
            // In c++11, throw expr call correspond ctor firstly, and then
            // pass it to copy ctor as 1st parameter. But in c++20, clang++
            // optimize the redundant copy ctor. So, CSA will inline impilicit
            // copy ctor in c++11, but won't in c++20.(https://godbolt.org/z/j6az75o4d)
            throw TokenizeError("error parsing escape characters");
        }
    } catch(TokenizeError& err) {
        err.what();
    }
}

#if defined(__clang_analyzer__)
void csa_test() {
    // case 4: Only visiable when use CSA. 
}
#endif

class FunctionPtr {
public:
    FunctionPtr(bool (*func)(void)): function_(func) {}
    typedef bool (*InternalFunctionType)(void);
    InternalFunctionType function_;
    bool invoke() {
        // case 5:
        // CG don't know what is this function pointer,
        // but CSA could get this info by symbolic execution.
        return function_();
    }
};

int main() {
    int number = 10;
    Parent::C1 c1(&number);
    Parent::C1 c2 = c1;
    std::string s = "123";
    ParseString(&s);
    raii r1{10};
    #if defined(__clang_analyzer__)
    csa_test();
    #endif
    struct c_in_func {
        static bool foo() {
            return true;
        }
    };
    FunctionPtr fp = FunctionPtr(&c_in_func::foo);
    fp.invoke();

    return 0;
}