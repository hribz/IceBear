#include <iostream>
#include <vector>
#include <algorithm>

// 函数：计算两个数的除法
int divide(int a, int b) {
    return a / b;  // 潜在的除0错误
}

// 函数：根据条件返回一个除数
int getDivisor(int x, int y) {
    if (x > y) {
        return x - y;
    } else if (x < y) {
        return y - x;
    } else {
        return 0;  // 当x == y时，返回0
    }
}

// 函数：计算数组中元素的某种复杂运算
double complexCalculation(int a, int b) {
    // 获取除数
    int divisor = getDivisor(a, b);

    // 计算某种复杂运算
    double result = divide(a + b, b);  // 潜在的除0错误

    return result;
}

// 主函数
int main() {
    int a = 5, b = 0; // 注意：a == b，会导致除0错误

    // 进行复杂计算
    double result = complexCalculation(a, b);

    std::cout << "Result of complex calculation: " << result << std::endl;

    return 0;
}