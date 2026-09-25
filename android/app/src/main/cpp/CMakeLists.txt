cmake_minimum_required(VERSION 3.22.1)
project(dkr_android LANGUAGES C CXX)

add_library(dkr_android SHARED dkr_android.cpp)

target_compile_features(dkr_android PRIVATE cxx_std_20)
target_link_libraries(dkr_android PRIVATE android log)
