export PATH_PROJECT=$PWD

rm -rf $PATH_PROJECT/cmake-build
mkdir $PATH_PROJECT/cmake-build
cd $PATH_PROJECT/cmake-build
cmake -DCMAKE_BUILD_TYPE=Debug \
  -DLLVM_CONFIG_BINARY=$PATH_PROJECT/install/bin/llvm-config \
  -DENABLE_SOLVER_Z3=ON \
  -DZ3_INCLUDE_DIRS=$PATH_PROJECT/install/include \
  -DZ3_LIBRARIES=$PATH_PROJECT/install/lib/libz3.so \
  -DENABLE_UNIT_TESTS=OFF \
  -DENABLE_SYSTEM_TESTS=OFF \
  -DENABLE_TCMALLOC=OFF \
  -DENABLE_DOXYGEN=OFF \
  -G "CodeBlocks - Unix Makefiles" \
  -DCMAKE_INSTALL_PREFIX=$PATH_PROJECT/install \
  ..
make -j
make install
cd ..
