export PATH_PROJECT=$PWD

# build z3
cd $PATH_PROJECT/build
#rm -rf z3
git clone https://github.com/Z3Prover/z3.git
cd z3
git checkout z3-4.8.9
python3 scripts/mk_make.py --prefix=$PATH_PROJECT/install
cd build
make -j
make install
cd $PATH_PROJECT
