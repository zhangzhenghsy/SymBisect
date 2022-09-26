export PATH_PROJECT=$PWD

# build llvm & clang
cd $PATH_PROJECT/build
#rm -rf llvm-project
#git clone https://github.com/llvm/llvm-project.git
cd llvm-project
#git checkout tags/llvmorg-11.0.1
#mkdir build && cd build
cd build
cmake -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_ENABLE_PROJECTS="clang;lld" \
  -DLLVM_TARGETS_TO_BUILD="X86" \
  -DCMAKE_INSTALL_PREFIX=$PATH_PROJECT/install \
  ../llvm
make -j20
make install
cd ../../..
