import prioritylist
import sys, os
import subprocess
import helper
import cover_lineinfo
import compilebc
import cfg_analysis
import shutil

patchcommit_syzbothash = {
    "c993ee0f9f81":"797c55d2697d19367c3dabc1e8661f5810014731",
    "b293dcc473d2":"b32f38fe8c743a79f4420f3d0cdb3a9dbc9a5549",
    "a6763080856f":"a1c13f6ee9868a7c554305d5aea7a4dc5a8e1d7a"
}

patchcommit_linux_ref_link = {
        "b293dcc473d2":"https://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git/snapshot/linux-next-6abab1b81b657ca74b7c443e832d95c87901e75b.tar.gz",
        "a6763080856f":"https://git.kernel.org/pub/scm/linux/kernel/git/netdev/net-next.git/snapshot/net-next-000fe940e51f03210bd5fb1061d4d82ed9a7b1b6.tar.gz"
        }

def download_linux_ref(PATH):
    print("download_linux_ref")
    PATH = "/".join(PATH.split("/")[:-1])
    patchcommit = PATH.split("/")[-1]
    link = patchcommit_linux_ref_link[patchcommit]

    string1 = "cd "+PATH+"; wget "+ link
    #print(string1)
    print(command(string1))

    filename = link.split("/")[-1]
    if not os.path.exists(PATH+"/"+filename):
        print("Download fail")
        return
    string1 = "cd " + PATH + ";tar -xf " + filename
    print(string1)
    command(string1)

    dirname = filename.split(".")[0]
    string1 = "cd " + PATH + ";mv "+dirname + " linux_ref"
    command(string1)

def copy_vmlog(PATH):
    print("copy_vmlog()")
    PATH = PATH if PATH[-1] != "/" else PATH[:-1]
    patchcommit = PATH.split("/")[-2]
    syzbothash = patchcommit_syzbothash[patchcommit][:7]
    src = "/home/zzhan173/SyzMorph/projects/test/completed/" + syzbothash + "/Ucklee/qemu-"+syzbothash+"-zheng_kernel.log0"
    dst = PATH+"/vm.log"
    print("src:", src)
    print("dst:", dst)
    shutil.copy(src, dst)

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

# PATH: path to the directory of case.
# kernel: path to the kernel to be compiled into bc 
def compile_bcfiles(PATH, kernel = None):
    print("\ncompile_bcfiles()\n")
    if not kernel:
        kernel = PATH + "/linux_ref"
    compilebc.get_config_withoutkasan(PATH)
    compilebc.format_linux(kernel)
    compilebc.compile_gcc(PATH, kernel)
    compilebc.get_dryruncommands(kernel)
    compilebc.compile_bc_extra("compile", PATH, kernel)
    compilebc.compile_bc_extra("copy", PATH, kernel)
    compilebc.compile_bc_extra("check", PATH, kernel)

def run_SyzMorph(PATH):
    print("run_SyzMorph()")
    patchcommit = PATH.split("/")[-2]
    syzbothash = patchcommit_syzbothash[patchcommit]

    string1 = "cd /home/zzhan173/SyzMorph; . venv/bin/activate "
    #subprocess.run(string1, shell=True)
    string1 += "&& python3 syzmorph syzbot --proj test --get " + syzbothash + " --addition"
    string1 += "&& python3 syzmorph run --proj test --case " + syzbothash + " --config ./my.cfg --ucklee"
    print(string1)

    process = subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()
    print("Output of the run_SyzMorph command:", str(output))
    if error:
        print("Error:", str(error))

    return_code = process.returncode
    print("Return code: ", return_code)

def compile_refkernel(PATH):
    download_linux_ref(PATH)
    prioritylist.copy_refkernel(PATH)
    # Add -fno-inline-small-functions in Makefile
    # Format the code to avoid 2 BBs in a line
    # Call adapt_end_report() to add print in end_report() /mm/kasan/report.c
    # Change default CONFIG_LOG_BUF_SHIFT to max possible value 25
    prioritylist.compile_gcc(PATH)
    # Copy the compiled kernel/vmlinux to PATH
    prioritylist.copy_compiledkernel(PATH)
    # Get and store debuginfo from vmlinux, stored as tmp_o (get dumpresult of vmlinux by the way)
    prioritylist.get_vmlinux_dbginfo_parallel(PATH)
    # Used for SyzMorph
    shutil.copy(PATH+"/bzImage", "/home/zzhan173/OOBW2022")

def get_cover_from_vmlog(PATH):
    run_SyzMorph(PATH)
    copy_vmlog(PATH)
    prioritylist.get_cover_from_vmlog(PATH)

def get_cover_lineinfo(PATH):
    prioritylist.get_cover_lineinfo(PATH)
    #if not os.path.exists(PATH + "/targetline"):
    if not os.path.exists(PATH+"/lineguidance/"):
        os.mkdir(PATH+"/lineguidance/")
    helper.get_callstack(PATH)
    # get clean callstack and corresponding files
    helper.get_cleancallstack(PATH)
    # get clean callstack after code format
    # It will call  get_matchedlines_afterformat(PATH)
    helper.get_cleancallstack_format(PATH)
    # Get targetline from the clean callstack after code format
    helper.get_targetline_format(PATH)
    with open(PATH+"/targetline", "r") as f:
        targetline = f.readlines()[0][:-1]
        print("targetline:", targetline)
    # if find the (last) target_line in coverlineinfo, then cut the lines after it
    find_targetline = cover_lineinfo.cut_cover_line(PATH, targetline)
    if find_targetline:
        prioritylist.get_cover_lineinfo(PATH)
    

def get_lineguidance(PATH):
    prioritylist.get_complete_coverage_coverline(PATH)
    prioritylist.get_linelist(PATH)
    prioritylist.get_BBlist(PATH)
    prioritylist.get_BBlinelist_doms(PATH)
    prioritylist.cfg_analysis.get_cfg_files(PATH)
    prioritylist.copy_lineguidance(PATH)

def generate_kleeconfig(PATH):
    helper.get_mustBBs(PATH)
    cfg_analysis.get_func_BB_targetBBs(PATH)
    prioritylist.generate_kleeconfig(PATH, [])
    if not os.path.exists(PATH+"/configs"):
        os.mkdir(PATH+"/configs")
    shutil.copy(PATH+"/config_cover_doms.json", PATH+"/configs/config_cover_doms.json")

if __name__ == "__main__":
    option = sys.argv[1]
    PATH = "/home/zzhan173/OOBW2022/c8af247de385/59f2f4b8a757"
    PATH = "/home/zzhan173/OOBW2022/c993ee0f9f81/91265a6da44d"
    PATH = "/home/zzhan173/OOBW2022/b293dcc473d2/6abab1b81b65"
    PATH = "/home/zzhan173/OOBW2022/a6763080856f/000fe940e51f"
    if len(sys.argv) > 2:
        PATH = sys.argv[2]
    if PATH[-1] == "/":
        PATH = PATH[:-1]
    if option == "tmptest":
        run_SyzMorph(PATH)
    # Manual work1: config; report.txt;
    #1) Compile the refkernel with given config, note that we need to format the kernel first to keep consistent with later BC files
    if option == "compile_refkernel":
        compile_refkernel(PATH)
    #2) Manual work2: get KCOV output vm.0 from syzkaller reproducer (already automated)
    # requirement repro.syz, compiled kernel from 0), compiled corresponding syzkaller tool
    if option == "get_cover_from_vmlog":
        get_cover_from_vmlog(PATH)
    if option == "get_cover_lineinfo":
        get_cover_lineinfo(PATH)
    #1.2) compile kernels to bcfiles in repos/linux
    if option == "compile_bcfiles":
        compile_bcfiles(PATH)
        # link_bclist_fromcover and get_tagbcfile (and corresponding .ll files)
        prioritylist.get_bcfile_fromcover(PATH)
    if option == "get_lineguidance":
        get_lineguidance(PATH)
    #if option == "generate_kleeconfig":
        generate_kleeconfig(PATH)
