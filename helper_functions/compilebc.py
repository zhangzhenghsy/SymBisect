import multiprocessing
import os, sys
import re
import subprocess
from multiprocessing import Pool
import shutil

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
def compile_bc_extra(option, targetdir, filename = None):
    #option = "compile" or "check"
    sourcecoverage = False
    #option = sys.argv[1]
    regx = r'echo \'[ \t]*CC[ \t]*(([A-Za-z0-9_\-.]+\/)+([A-Za-z0-9_.\-]+))\';'
    #base = os.path.join(self.case_path, 'linux')
    #base = "/home/zzhan173/repos/linux"
    #path = os.path.join(base, 'llvmclang_log')
    #path = os.path.join(base, 'clang_log')
    path = '/home/zzhan173/repos/linux/clang_log'
    clang_path = '/data2/zheng/clangs/clang11/clang11.0.1/bin/clang'
    #clang_path = "/home/zzhan173/repos/Linux_kernel_UC_KLEE/build/llvm-project/build/bin/clang"
    #clang_path = "/data2/zheng/clangs/clang10/clang10/bin/clang"
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
                    new_cmd.append('-emit-llvm -g -O0 -fno-short-wchar -fno-discard-value-names')
                    if sourcecoverage:
                        new_cmd.append(' -fprofile-instr-generate -fcoverage-mapping')
                    #new_cmd.append('-emit-llvm -g -fno-short-wchar')
                    #if cmd[0] == 'wllvm':
                    #    new_cmd.append('{}/tools/llvm/build/bin/clang'.format(self.proj_path))
                    #    new_cmd.append('-emit-llvm')
                new_cmd.extend(cmd[1:])

            except ValueError:
                print("'No \'wllvm\' or \';\' found in \'{}\''.format(line)")
                #self.case_logger.error('No \'wllvm\' or \';\' found in \'{}\''.format(line))
                #raise CompilingError
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
            #newcmd = newcmd.replace(clang_path, newclang_path)
            #print(newcmd)
            newcmds += [newcmd]
    if option == "check":
        print("\n not compile file:")
        notcompiledbc = []
        for bcfile in bcfiles:
            if not os.path.exists(bcfile):
                notcompiledbc += [bcfile]
                print(bcfile)
        #for cmd in newcmds:
        #    if any(bcfile in cmd for bcfile in notcompiledbc):
        #        print(cmd)
    if option == "compile":
        for newcmd in newcmds:
            print(newcmd)
        print("number of bc files:",len(newcmd))
        with Pool(32) as p:
            p.map(command, newcmds)
        #targetdir = "/home/zzhan173/Qemu/OOBW/pocs/433f4ba1/63de3747/source"
        #targetdir = "/home/zzhan173/Qemu/OOBW/pocs/eb73190f/dd52cb879063/source"
        #targetdir = "/home/zzhan173/Qemu/OOBW/pocs/253a496d/b3c424eb6a1a/source"
        #targetdir = sys.argv[2]+"/source"
        if not os.path.exists(targetdir):
            os.mkdir(targetdir)
        copy_bcfiles(targetdir, bcfiles)


def copy_bcfiles(targetdir, bcfiles):
    for bcfile in bcfiles:
        if not os.path.exists(bcfile):
            continue
        src = bcfile
        dst = targetdir+"/" + bcfile
        cfile = bcfile.replace(".bc", ".c")
        dstcfile = targetdir+"/" + cfile

        dstfolder = os.path.dirname(dst)
        if not os.path.exists(dstfolder):
            os.makedirs(dstfolder)
        shutil.copy(src,dst)
        shutil.copy(cfile, dstcfile)

def format_file_command(PATH):
    if dbg:
        print("clang format File:",PATH)
    string = "/data4/zheng/Linux_kernel_UC_KLEE/install/bin/clang-format -style=\"{BreakBeforeBraces: Stroustrup, IndentWidth: 4, SpaceBeforeParens: Never}\" -i "+PATH
    #result = command(string)
    return string

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
            if path.endswith(".h") or path.endswith(".c"):
                commandlist += [format_file_command(path)]
    return commandlist

def format_linux():
    commands = format_dir_commands("/home/zzhan173/repos/linux")
    print("size of files to be formatted:", len(commands))
    with Pool(32) as p:
        p.map(command, commands)

# [compile/check] [targetdir] [specific filepath]
if __name__ == "__main__":
    print(sys.argv)
    if(len(sys.argv) > 3):
        funcname = sys.argv[3]
    option = sys.argv[1]
    targetdir = sys.argv[2]
    #compile_bc_extra(funcname)
    #compile_bc_extra()
    format_linux()
    compile_bc_extra(option, targetdir)
