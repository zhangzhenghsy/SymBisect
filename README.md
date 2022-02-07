# Linux_kernel_UC_KLEE

Linux_kernel_UC_KLEE is an under constraint symbolic execution engine for the Linux kernel based on [KLEE](https://github.com/klee/klee).

- KLEE: v2.2
- LLVM/Clang: 11
- OS: Ubuntu 20.04

## Feature

- handle some the Linux kernel functions, e.g., kmalloc()
- under constraint symbolic execution
- terminate state at low priority basic block and stop at target basic block, which could be set in config json
- handle indirect function call by MLTA default, also accept specify callee from config json
- easily expanded, just inherit class [Listener](https://github.com/ZHYfeng/Linux_kernel_UC_KLEE/blob/master/lib/Kernel/Listener/Listener.h) and add it in function [preparation()](https://github.com/ZHYfeng/Linux_kernel_UC_KLEE/blob/master/lib/Kernel/Listener/ListenerService.cpp#L76)

## Build

```shell
sudo apt install -y git cmake vim curl make unzip
sudo apt install -y autoconf automake libtool g++ build-essential pkg-config flex bison 
sudo apt install -y libgflags-dev libgtest-dev libc++-dev libssl-dev libelf-dev libsqlite3-dev
```
### build with apt install llvm & z3 (sudo)
```shell
sudo apt install llvm-11 clang-11 z3
mkdir ./cmake-build
cd ./cmake-build
cmake -DCMAKE_BUILD_TYPE=Debug \
  -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config-11 \
  -DENABLE_SOLVER_Z3=ON \
  -DENABLE_UNIT_TESTS=OFF \
  -DENABLE_SYSTEM_TESTS=OFF \
  -DENABLE_TCMALLOC=OFF \
  -DENABLE_DOXYGEN=OFF \
  -G "CodeBlocks - Unix Makefiles" \
  ..
make -j
```
### build llvm & z3 & klee (no sudo)
```shell
export PATH_PROJECT=$PWD
mkdir $PATH_PROJECT/build
mkdir $PATH_PROJECT/install

# build llvm & clang
cd $PATH_PROJECT/build
git clone https://github.com/llvm/llvm-project.git
cd llvm-project
git checkout tags/llvmorg-11.0.0
mkdir build && cd build
cmake -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_ENABLE_PROJECTS="clang;lld" \
  -DLLVM_TARGETS_TO_BUILD="X86" \
  -DCMAKE_INSTALL_PREFIX=$PATH_PROJECT/install \
  ../llvm
make -j10
make install

# build z3
cd $PATH_PROJECT/build
git clone git@github.com:Z3Prover/z3.git
cd z3
git checkout z3-4.8.9
python3 scripts/mk_make.py --prefix=$PATH_PROJECT/install
cd build
make -j
make install

# build klee
mkdir $PATH_PROJECT/cmake-build
cd $PATH_PROJECT/cmake-build
cmake -DCMAKE_BUILD_TYPE=Debug \
  -DLLVM_CONFIG_BINARY=$PATH_PROJECT/install/bin/llvm-config \
  -DENABLE_SOLVER_Z3=ON \
  -DENABLE_UNIT_TESTS=OFF \
  -DENABLE_SYSTEM_TESTS=OFF \
  -DENABLE_TCMALLOC=OFF \
  -DENABLE_DOXYGEN=OFF \
  -G "CodeBlocks - Unix Makefiles" \
  -DCMAKE_INSTALL_PREFIX=$PATH_PROJECT/install \
  ..
make -j
make install

# generate environment.sh
cd $PATH_PROJECT
echo "export PATH=$PATH_PROJECT/install/bin:\$PATH" >> environment.sh
echo "export PKG_CONFIG_PATH=$PATH_PROJECT/install/lib/pkgconfig:\$PKG_CONFIG_PATH" >> environment.sh
echo "export PATH_PROJECT=$PATH_PROJECT" >> environment.sh
```

## Usage
```shell
klee --config=config.json
```
look at [config.json](https://github.com/ZHYfeng/Linux_kernel_UC_KLEE/blob/master/config.json) to know more about the config json file.
