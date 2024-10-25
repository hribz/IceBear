template <template <typename> class T> class template_template_class {};

template <template <template <typename> class T> class T> class container { };

container<template_template_class> c1;

template <typename T> class template_class {};

template_class<int> c2;