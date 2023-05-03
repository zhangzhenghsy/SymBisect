import prioritylist
import sys, os
import subprocess
import helper
import cover_lineinfo
import compilebc

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

if __name__ == "__main__":
    option = sys.argv[1]
    PATH = "/home/zzhan173/OOBW2022/c8af247de385/59f2f4b8a757"
    PATH = "/home/zzhan173/OOBW2022/c993ee0f9f81/91265a6da44d"
    if not PATH:
        PATH = sys.argv[2]
    if PATH[-1] == "/":
        PATH = PATH[:-1]
    if option == "tmptest":
        helper.get_callstack(PATH)
    #1) Compile the refkernel with given config, note that we need to format the kernel first to keep consistent with later BC files
    # Manual work1: config file;
    if option == "compile_refkernel":
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
    #2) Manual work2: get KCOV output vm.0 from syzkaller reproducer
    # requirement repro.syz, compiled kernel from 0), compiled corresponding syzkaller tool
    if option == "get_cover_from_vmlog":
        prioritylist.get_cover_from_vmlog(PATH)

    if option == "get_cover_lineinfo":
        prioritylist.get_cover_lineinfo(PATH)
        if not os.path.exists(PATH + "/targetline"):
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
    #1.2) compile kernels to bcfiles in repos/linux
    if option == "compile_bcfiles":
        compile_bcfiles(PATH)
        # link_bclist_fromcover and get_tagbcfile
        prioritylist.get_bcfile_fromcover(PATH)
    
    if option == "get_lineguidance":
        prioritylist.get_complete_coverage_coverline(PATH)
        prioritylist.get_linelist(PATH)
        prioritylist.get_BBlist(PATH)
        prioritylist.get_BBlinelist_doms(PATH)
        prioritylist.cfg_analysis.get_cfg_files(PATH)
        prioritylist.copy_lineguidance(PATH)

    if option == "generate_kleeconfig":
        prioritylist.generate_kleeconfig(PATH, [])
