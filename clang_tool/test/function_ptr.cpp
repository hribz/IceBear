void foo() {}
void bar(int) {}
typedef void (*func_ptr)();
typedef void (*func_ptr_int)(int);

void callback(func_ptr func) {
  func();
}

int main() {
  // 变量初始化
  func_ptr p1 = foo;
  
  // 显式取地址
  func_ptr_int p2 = &bar;
  
  // 函数参数
  callback(foo);
  
  // 数组初始化
  func_ptr arr[] = {foo};  // bar会被过滤
  
  // 返回语句
  auto get_ptr = [] { return foo; };
  
  // 条件表达式
  func_ptr p3 = true ? foo: foo;  // bar会被过滤

  p3();
}