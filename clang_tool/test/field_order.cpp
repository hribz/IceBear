struct FancyInt {
  int arr[10];
};
struct FancyLongLong {
  long long arr[10];
};

int magicInt(FancyInt const &f) {
  int z = (char*)&f.arr[1] - (char*)&f.arr[0];
  return 100 / (z-4); // Is it a div by zero?
}

int magicLongLong(FancyLongLong const &f) {
  int z = (char*)&f.arr[1] - (char*)&f.arr[0];
  return 100 / (z-4); // Is it a div by zero?
}