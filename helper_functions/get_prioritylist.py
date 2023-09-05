import prioritylist
import sys, os
import subprocess
import helper
import cover_lineinfo
import compilebc
import cfg_analysis
import shutil
import json

def copy_vmlog(PATH, syzbothash):
    syzbothash = syzbothash[:7]
    print("copy_vmlog()")
    PATH = PATH if PATH[-1] != "/" else PATH[:-1]
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

SyzMorph_PATH = "/home/zzhan173/SyzMorph"
#run the syzmorph to add the case and get the config/report.txt files
#PATH example: /data3/zzhan173/OOBR/9fcea5ef6dc4dc72d334/refkernel
def run_SyzMorph_add(syzbothash):
    print("\nrun_SyzMorph_add()\n")
    string1 = "cd " + SyzMorph_PATH + "; . venv/bin/activate "
    #subprocess.run(string1, shell=True)
    string1 += "&& python3 syzmorph syzbot --proj test --get " + syzbothash + " --addition"
    process = subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()
    print("Output of the run_SyzMorph_add command:", str(output))
    if error:
        print("Error:", str(error))
    return_code = process.returncode
    print("Return code: ", return_code)


def run_SyzMorph_ucklee(syzbothash):
    print("run_SyzMorph_ucklee()\n")
    if os.path.exists("/home/zzhan173/SyzMorph/projects/test/completed/"+syzbothash[:7]):
        print("remove previous generated", "/home/zzhan173/SyzMorph/projects/test/completed/"+syzbothash[:7])
        shutil.rmtree("/home/zzhan173/SyzMorph/projects/test/completed/"+syzbothash[:7])
    string1 = "cd /home/zzhan173/SyzMorph; . venv/bin/activate "
    #subprocess.run(string1, shell=True)
    #string1 += "&& python3 syzmorph syzbot --proj test --get " + syzbothash + " --addition"
    string1 += "&& python3 syzmorph run --proj test --case " + syzbothash + " --config ./my.cfg --ucklee"
    print(string1)

    process = subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()
    print("Output of the run_SyzMorph command:", str(output))
    if error:
        print("Error:", str(error))

    return_code = process.returncode
    print("Return code: ", return_code)

def compile_refkernel(PATH, syzbothash):
    print("\ncompile_refkernel()\n")
    #download_linux_ref(PATH, syzbothash)
    prioritylist.copy_refkernel(PATH)
    # Add -fno-inline-small-functions in Makefile
    # Format the code to avoid 2 BBs in a line
    # Call adapt_end_report() to add print in end_report() /mm/kasan/report.c
    # Change default CONFIG_LOG_BUF_SHIFT to max possible value 25
    prioritylist.compile_gcc_clang(PATH)
    if not os.path.exists(PATH+"/linux_ref/vmlinux"):
        # try clang
        prioritylist.copy_refkernel(PATH)
        prioritylist.compile_gcc_clang(PATH, True)
    # Copy the compiled kernel/vmlinux to PATH
    prioritylist.copy_compiledkernel(PATH)
    # Get and store debuginfo from vmlinux, stored as tmp_o (get dumpresult of vmlinux by the way)
    prioritylist.get_vmlinux_dbginfo_parallel(PATH)
    # Used for SyzMorph
    shutil.copy(PATH+"/bzImage", "/home/zzhan173/OOBW2022")

def get_cover_from_vmlog(PATH, syzbothash):
    print("\nget_cover_from_vmlog()\n")
    if not os.path.exists(PATH+"/vm.log_correct"):
        run_SyzMorph_ucklee(syzbothash)
        copy_vmlog(PATH, syzbothash)
    else:
        print("skip run_SyzMorph_ucklee since vm.log_correct exists")
    prioritylist.get_cover_from_vmlog(PATH)

def get_cover_from_vmlog2(PATH):
    prioritylist.get_cover_from_vmlog(PATH)

def get_cover_lineinfo(PATH):
    print("\nget_cover_lineinfo()\n")
    prioritylist.get_cover_lineinfo(PATH)
    prioritylist.get_complete_coverage_coverline(PATH)
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
    print("\nget_lineguidance()\n")
    #prioritylist.get_complete_coverage_coverline(PATH)
    prioritylist.get_linelist(PATH)
    prioritylist.get_BBlist(PATH)
    prioritylist.get_BBlinelist_doms(PATH)
    prioritylist.cfg_analysis.get_cfg_files(PATH)
    prioritylist.copy_lineguidance(PATH)

def generate_kleeconfig(PATH):
    print("generate_kleeconfig()\n")
    helper.get_mustBBs(PATH)
    cfg_analysis.get_func_BB_targetBBs(PATH)
    prioritylist.generate_kleeconfig(PATH, [])
    if not os.path.exists(PATH+"/configs"):
        os.mkdir(PATH+"/configs")
    shutil.copy(PATH+"/config_cover_doms.json", PATH+"/configs/config_cover_doms.json")

if __name__ == "__main__":
    option = sys.argv[1]
    PATH = "/data3/zzhan173/OOBR/9fcea5ef6dc4dc72d334/refkernel"
    syzbothash = None
    if len(sys.argv) > 2:
        PATH = sys.argv[2]
    if PATH[-1] == "/":
        PATH = PATH[:-1]
    if len(sys.argv) > 3:
        syzbothash = sys.argv[3]
    if not syzbothash:
        syzbothash = PATH.split("/")[-2]
    if option == "tmptest":
        #helper.check_cleancallstack_format(PATH)
        #prioritylist.get_BB_lineinfo(PATH)
        #helper.get_indirectcalls(PATH)
        #generate_kleeconfig(PATH)
        with open(PATH+"/mustBBs", "r") as f:
            s_buf = f.readlines()
        MustBBs = [line[:-1] for line in s_buf]
        low_priority_bb_list = prioritylist.get_low_priority_bb_list(PATH, MustBBs)
    # Manual work1: config; report.txt;
    #1) Compile the refkernel with given config, note that we need to format the kernel first to keep consistent with later BC files
    if option == "compile_refkernel":
        compile_refkernel(PATH)
    #2) Manual work2: get KCOV output vm.0 from syzkaller reproducer (already automated)
    # requirement repro.syz, compiled kernel from 0), compiled corresponding syzkaller tool
    if option == "get_cover_from_vmlog":
        get_cover_from_vmlog2(PATH)
    if option == "get_cover_lineinfo":
        get_cover_lineinfo(PATH)
    #1.2) compile kernels to bcfiles in repos/linux
    if option == "compile_bcfiles":
        compile_bcfiles(PATH)
        # link_bclist_fromcover and get_tagbcfile (and corresponding .ll files)
        prioritylist.get_bcfile_fromcover(PATH)
    if option == "get_lineguidance":
        get_lineguidance(PATH)
    if option == "generate_kleeconfig":
        generate_kleeconfig(PATH)
    if option == "all":
        if not os.path.exists(PATH+"/vm.log_correct"):
            #run_SyzMorph_add(syzbothash)
            compile_refkernel(PATH, syzbothash)
        else:
            print("skip run_SyzMorph_add/compile_refkernel since vm.log_correct exists")
        if not os.path.exists(PATH+"/vm.log_correct"):
            print("Please generate the vm.log_correct manually")
            exit()
        get_cover_from_vmlog(PATH, syzbothash)
        get_cover_lineinfo(PATH)
        compile_bcfiles(PATH)
        prioritylist.get_bcfile_fromcover(PATH)
        get_lineguidance(PATH)
        generate_kleeconfig(PATH)
