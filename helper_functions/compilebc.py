import multiprocessing
import os, sys
import re
import subprocess
from multiprocessing import Pool
import shutil
import json

dbg = False
def regx_get(regx, line, index):
    m = re.search(regx, line)
    if m != None and len(m.groups()) > index:
        return m.groups()[index]
    return None

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

clang_path =  "/home/zzhan173/Linux_kernel_UC_KLEE/install/bin/clang"
def compile_bc_extra(option, PATH, kernel, filename = None):
    #option = "compile" or "check"
    regx = r'echo \'[ \t]*CC[ \t]*(([A-Za-z0-9_\-.]+\/)+([A-Za-z0-9_.\-]+))\';'
    #base = os.path.join(self.case_path, 'linux')
    #base = "/home/zzhan173/repos/linux"
    #path = os.path.join(base, 'llvmclang_log')
    #path = os.path.join(base, 'clang_log')
    path = kernel+'/clang_log'
    #clang_path = '/data3/zheng/clangs/clang11/clang11.0.1/bin/clang'
    #clang_path = "/home/zzhan173/repos/Linux_kernel_UC_KLEE/build/llvm-project/build/bin/clang"
    #clang_path = "/data3/zheng/clangs/clang10/clang10/bin/clang"
    #newclang_path = "/home/zzhan173/repos/Linux_kernel_UC_KLEE/build/llvm-project/build/bin/clang"

    newcmds = []
    #used for debug
    bcfiles = []
    with open(path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            #if "CC      fs/namespace.o" not in line:
            #    continue
            if filename:
                if filename not in line:
                    continue
            p2obj = regx_get(regx, line, 0)
            obj = regx_get(regx, line, 2)
            if p2obj == None or obj == None:
                """cmds = line.split(';')
                for e in cmds:
                    call(e, cwd=base)"""
                continue
            if 'arch/x86/boot' in p2obj \
                or 'arch/x86/entry/vdso' in p2obj \
                or 'arch/x86/realmode' in p2obj:
                continue
            #print("CC {}".format(p2obj))
            #print(line)
            new_cmd = []
            try:
                #clang_path = '{}/tools/llvm/build/bin/clang'.format(self.proj_path)
                idx1 = line.index(clang_path)
                idx2 = line[idx1:].index(';')
                cmd = line[idx1:idx1+idx2].split(' ')
                if cmd[0] == clang_path:
                    new_cmd.append(cmd[0])
                    new_cmd.append('-emit-llvm -g -O0 -fno-short-wchar -fno-discard-value-names -fno-inline -fno-inline-functions')
                    #if sourcecoverage:
                    #    new_cmd.append(' -fprofile-instr-generate -fcoverage-mapping')
                    #new_cmd.append('-emit-llvm -g -fno-short-wchar')
                    #if cmd[0] == 'wllvm':
                    #    new_cmd.append('{}/tools/llvm/build/bin/clang'.format(self.proj_path))
                    #    new_cmd.append('-emit-llvm')
                new_cmd.extend(cmd[1:])

            except ValueError:
                print("'No \'wllvm\' or \';\' found in \'{}\''.format(line)")
                print(line)
                continue
                #self.case_logger.error('No \'wllvm\' or \';\' found in \'{}\''.format(line))
                #raise CompilingError
            #print("new_cmd:", new_cmd)
            while new_cmd[-1] == "":
                new_cmd = new_cmd[:-1]
            idx_obj = len(new_cmd)-2
            st = new_cmd[idx_obj]
            if st[len(st)-1] == 'o':
                new_cmd[idx_obj] = st[:len(st)-1] + 'bc'
                bcfiles += [st[:len(st)-1] + 'bc']
            else:
                print("{} is not end with .o".format(new_cmd[idx_obj]))
                continue
            
            newcmd = " ".join(new_cmd)
            newcmd = newcmd.replace("-O2 ","")
            newcmd = newcmd.replace("-Os ","")
            newcmd = newcmd.replace("-fshort-wchar ","")
            newcmd = newcmd.replace("-fno-inline-small-functions ","")
            #newcmd = newcmd.replace(clang_path, newclang_path)
            #print(newcmd)
            newcmd = "cd "+kernel+";"+newcmd
            newcmds += [newcmd]
    if option == "check":
        print("\n not compile file:")
        notcompiledbc = []
        for bcfile in bcfiles:
            if not os.path.exists(kernel+"/"+bcfile):
                notcompiledbc += [kernel+"/"+bcfile]
                print(kernel+"/"+bcfile)
        #for cmd in newcmds:
        #    if any(bcfile in cmd for bcfile in notcompiledbc):
        #        print(cmd)
    if option == "compile":
        with open(kernel+"/compile_bc_commands", "w") as f:
            for newcmd in newcmds:
                f.write(newcmd+"\n")
            #print(newcmd)
        print("number of bc files:",len(newcmds))
        with Pool(32) as p:
            p.map(command, newcmds)
        #targetdir = "/home/zzhan173/Qemu/OOBW/pocs/433f4ba1/63de3747/source"
        #targetdir = "/home/zzhan173/Qemu/OOBW/pocs/eb73190f/dd52cb879063/source"
        #targetdir = "/home/zzhan173/Qemu/OOBW/pocs/253a496d/b3c424eb6a1a/source"
        #targetdir = sys.argv[2]+"/source"
    if option == "copy":
        targetdir = PATH + "/source"
        if not os.path.exists(targetdir):
            os.mkdir(targetdir)
        copy_bcfiles(targetdir, bcfiles, kernel)


def copy_bcfiles(targetdir, bcfiles, sourcedir):
    for bcfile in bcfiles:
        if not os.path.exists(sourcedir+"/"+bcfile):
            continue
        src = sourcedir+"/"+bcfile
        dst = targetdir+"/" + bcfile
        cfile = sourcedir+"/"+bcfile.replace(".bc", ".c")
        dstcfile = targetdir+"/" + bcfile.replace(".bc", ".c")

        dstfolder = os.path.dirname(dst)
        if not os.path.exists(dstfolder):
            os.makedirs(dstfolder)
        shutil.copy(src, dst)
        if not os.path.exists(cfile):
            print(cfile, "not exists")
            continue
        shutil.copy(cfile, dstcfile)

#def format_file_command(PATH):
#    if dbg:
#        print("clang format File:",PATH)
#    string = "/data4/zheng/Linux_kernel_UC_KLEE/install/bin/clang-format -style=\"{BreakBeforeBraces: Stroustrup}\" -i "+PATH
#    #result = command(string)
#    return string

def get_indent(line):
    indent = ""
    for i in range(len(line)):
        if line[i] not in [" ", "\t"]:
            break
        indent += line[i]
    return indent

def format_file_command(PATH):
    new_buf = []
    #print(PATH)
    with open(PATH, "r") as f:
        try:
            s_buf = f.readlines()
        except:
            print("format_file_command readlines except", PATH)
            return
    for line in s_buf:
        if "} else if (" in line and "\\" not in line:
            linelist = line.split("} else if (")
            if len(linelist) >2:
                print(line)
                new_buf += [line]
                continue
            line1 = linelist[0]+"}\n"
            indent = get_indent(line)
            line2 = indent+"else if ("+linelist[1]
            new_buf += [line1, line2]
        elif "} else {" in line and "\\" not in line:
            linelist = line.split("} else {")
            line1 = linelist[0]+"}\n"
            indent = get_indent(line)
            line2 = indent+"else {"+linelist[1]
            new_buf += [line1, line2]
        else:
            new_buf += [line]
    with open(PATH, "w") as f:
        for line in new_buf:
            f.write(line)

def format_dir_commands(PATH):
    commandlist = []
    if dbg:
        print("clang format Dir:",PATH)
    filelist = os.listdir(PATH)
    for filename in filelist:
        path = PATH+"/"+filename
        if os.path.isdir(path):
            commandlist += format_dir_commands(path)
        elif os.path.isfile(path):
            #if path.endswith(".h") or path.endswith(".c"):
            if path.endswith(".c"):
                #commandlist += [format_file_command(path)]
                commandlist += [path]
    return commandlist

def format_linux(kernel = "/home/zzhan173/repos/linux"):
    format_linux_b8fe393f999a291a9ea6(kernel)
    commands = format_dir_commands(kernel)
    print("size of files to be formatted:", len(commands))
    with Pool(32) as p:
        #p.map(command, commands)
        p.map(format_file_command, commands)

def format_linux_b8fe393f999a291a9ea6(kernel):
    filepath = kernel + "/net/qrtr/Kconfig"
    if os.path.exists(filepath):
        s_buf2 = []
        with open(filepath, "r") as f:
            s_buf = f.readlines()
        for line in s_buf:
            if "depends on ARCH_QCOM || COMPILE_TEST" in line:
                continue
            s_buf2 += [line]
        with open(filepath, "w") as f:
            for line in s_buf2:
                f.write(line)
# currently it can insert some lines according to codeadaptation json file
# note: it should not be done when compile bc
# todo: then there is a line matching issue, unless the added lines are added only before the crash line
def adapt_code(repo, codeadaptation):
    with open(codeadaptation) as f:
        # it will contain the added lines 
        file_index_lines = json.load(f)
    for filename in file_index_lines:
        index_lines = file_index_lines[filename]
        s_buf2 = []
        with open(repo+"/"+filename, "r") as f:
            s_buf = f.readlines()
        for i in range(len(s_buf)):
            index = str(i)
            if index in index_lines:
                s_buf2 += index_lines[index]
            s_buf2 += [s_buf[i]]
        with open(repo+"/"+filename, "w") as f:
            for line in s_buf2:
                f.write(line)


def adapt_end_report(repo):
    print("adapt_end_report()")
    addedlines = [
        "\tstruct task_struct *t;\n",
        "\tunsigned long *area;\n",
        "\tunsigned long pos;\n",
        "\tunsigned long i;\n",
        '\tpr_err("==================================================================\\n");\n',
        "\tt = current;\n",
        "\tarea = t->kcov_area;\n",
        "\tpos = READ_ONCE(area[0]);\n",
        "\tfor (i = 1; i < pos + 1; i++) {\n",
        '\t\tpr_err("KCOV: %lx\\n", area[i]);\n',
        '\t\t}\n',
        '\tpr_err("Done!");\n',
    ]
    filename = repo + "/mm/kasan/report.c"
    if not os.path.exists(filename):
        print(filename, "not exist. Need to manually add code")
        exit()

    with open(filename, "r") as f:
        s_buf = f.readlines()
    for i in range(len(s_buf)):
        line = s_buf[i]
        if line.startswith("static void end_report"):
            s_buf2 = s_buf[:i+2] + addedlines + s_buf[i+2:]
            break;
    else:
        print("don't find suitable location to insert code. Need to manually add code")
        exit()
    with open(filename, "w") as f:
        for line in s_buf2:
            f.write(line)

def adapt_CONFIG_LOG_BUF_SHIFT(PATH):
    filename = PATH + "/config"
    with open(filename, "r") as f:
        s_buf = f.readlines()
    for i in range(len(s_buf)):
        line = s_buf[i]
        if line.startswith("CONFIG_LOG_BUF_SHIFT="):
            s_buf[i] = "CONFIG_LOG_BUF_SHIFT=25\n"
            break
    else:
        print("don't find suitable location to change value of CONFIG_LOG_BUF_SHIFT. Need to manually add code")
        return
    with open(filename, "w") as f:
        for line in s_buf:
            f.write(line)

def get_config_withoutkasan(PATH):
    print("get_config_withoutkasan()")
    with open(PATH+"/config", "r") as f:
        s_buf = f.readlines()
    for i in range(len(s_buf)):
        line = s_buf[i]
        if "CONFIG_KASAN=y" in line:
            s_buf[i] = "# CONFIG_KASAN is not set\n"
        if "CONFIG_KCOV=y" in line:
            s_buf[i] = "# CONFIG_KCOV is not set\n"
        if "CONFIG_MODVERSIONS=y" in line:
            s_buf[i] = "# CONFIG_MODVERSIONS is not set\n"
    with open(PATH+"/config_withoutkasan", "w") as f:
        for line in s_buf:
            f.write(line)

def compile_gcc(PATH, kernel, clang=None):
    #if PATH[-1] == "/":
    #    PATH = PATH[:-1]
    #if not commit:
    #    if PATH.split("/")[-1] in ["alloc", "crash"]:
    #        commit = PATH.split("/")[-2]
    #    else:
    #        commit = PATH.split("/")[-1]
    #string1 = "cd /home/zzhan173/repos/linux;find . -name '*.bc' | xargs rm; git checkout -f "+commit+";make mrproper"
    string1 = "cd " + kernel + ";make mrproper"
    print(string1)
    result = command(string1)
    #print("adapt_code()")
    #if os.path.exists(PATH+"/codeadaptation.json"):
    #    adapt_code("/home/zzhan173/repos/linux", PATH+"/codeadaptation.json")
    #print("format_linux()")
    #format_linux()
    #string1 = "cd /home/zzhan173/repos/linux;cp "+PATH+"/config_withoutkasan .config;make olddefconfig;make -j32"
    if clang:
        string1 = "cd " + kernel + ";cp "+PATH+"/config_withoutkasan .config;make olddefconfig CC="+clang_path+";make -j32 CC="+clang_path
    else:
        string1 = "cd " + kernel + ";cp "+PATH+"/config_withoutkasan .config;make olddefconfig;make -j32"
    print(string1)
    #if not os.path.exists(PATH+"/config_withoutkasan"):
    #    print("config_withoutkasan doesn't exist")
    #    exit()
    result = command(string1)

def get_dryruncommands(kernel):
    #clang_path = "/data3/zheng/clangs/clang11/clang11.0.1/bin/clang"
    #string1 = "cd /home/zzhan173/repos/linux;make olddefconfig CC="+clang_path
    string1 = "cd " + kernel +";make olddefconfig CC="+clang_path
    print(string1)
    result = command(string1)
    string1 = "cd " + kernel + "; make -n CC="+clang_path+" > clang_log"
    print(string1)
    result = command(string1)

# [compile/check/format] [targetdir] [specific filepath]
if __name__ == "__main__":
    print(sys.argv)
    if(len(sys.argv) > 3):
        funcname = sys.argv[3]
    option = sys.argv[1]
    targetdir = sys.argv[2]
    #compile_bc_extra(funcname)
    #compile_bc_extra()
    if option == "dryrun":
        compile_gcc(targetdir)
        get_dryruncommands()
    elif option == "format":
        format_linux()
    elif option == "compile":
        #option == "compile" or "check"
        compile_bc_extra("compile")
    elif option == "copy":
        compile_bc_extra("copy", targetdir)
    elif option == "check":
        compile_bc_extra("check", None, targetdir)
    elif option == "compilefile":
        compile_bc_extra("compile", None, sys.argv[2])
