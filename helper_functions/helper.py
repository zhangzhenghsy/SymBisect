import os,sys,subprocess
import match_targetlines
import json
import threading
import psutil
import get_stuckfunction
import requests
import shutil

class Command(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None

    def run(self, timeout):
        def target():
            print('Thread started')
            self.process = subprocess.Popen(self.cmd, shell=True)
            self.process.communicate()
            print('Thread finished')

        thread = threading.Thread(target=target)
        thread.start()

        thread.join(timeout)
        if thread.is_alive():
            print('Terminating process')
            self.process.terminate()
            thread.join()
        return self.process.returncode

def kill(proc_pid):
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()

def command(string1, Timeout=None):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if Timeout:
        try:
            p.wait(timeout = Timeout)
        except subprocess.TimeoutExpired:
            kill(p.pid)
            return False
        return True
    result=p.stdout.readlines()
    return result

def compare_dics(dic1, dic2):
    for ele in dic1:
        if ele not in dic2:
            print(ele,"not in the latter dic")
        if dic1[ele] != dic2[ele]:
            print(ele, dic1[ele], dic2[ele])

def get_file_url(url, filename):
    r = requests.request(method='GET', url=url)
    text = r.text
    with open(filename, "w") as f:
        f.write(text)

def add_fnoinline_Makefile(PATH):
    with open(PATH, "r") as f:
        s_buf = f.readlines()
    s_buf2 = []

    insert = False
    for i in range(len(s_buf)):
        line = s_buf[i]
        s_buf2 += [line]
        if not insert:
            if "endif" in line and "KBUILD_CFLAGS += -Os" in s_buf[i-1]:
                insert = True
                s_buf2 += ["KBUILD_CFLAGS   += -fno-inline-small-functions\n"]
                continue
            if line == "\n" and "ifdef CONFIG_CC_OPTIMIZE_FOR_SIZE" in s_buf[i+1]:
                insert = True
                s_buf2 += ["KBUILD_CFLAGS   += -fno-inline-small-functions\n"]
                continue
            if "endif" in line and "KBUILD_CFLAGS += -Os" in s_buf[i-2]:
                insert = True
                s_buf2 += ["KBUILD_CFLAGS   += -fno-inline-small-functions\n"]
                continue

    if not insert:
        print("Don't find location to insert -fno-inline-small-functions in", PATH)
    else:
        print("Insert -fno-inline-small-functions at line", (i+1), PATH)

    with open(PATH, "w") as f:
        for line in s_buf2:
            f.write(line)

# Example: /home/zzhan173/repos/linux/arch/x86/kvm/../../../virt/kvm/kvm_main.c to /home/zzhan173/repos/linux/virt/kvm/kvm_main.c
# Example: /home/zzhan173/repos/linux/./arch/x86/include/asm/fpu/internal.h:528 to /home/zzhan173/repos/linux/arch/x86/include/asm/fpu/internal.h:528 
def simplify_path(PATH):
    elelist = PATH.split("/")

    while ".." in elelist:
        index = elelist.index("..")
        elelist = elelist[:index-1] + elelist[index+1:]

    while "." in elelist:
        index = elelist.index(".")
        elelist = elelist[:index] + elelist[index+1:]

    PATH = "/".join(elelist)
    return PATH

def get_callstack(PATH):
    print("get_callstack() from report.txt")
    with open(PATH+"/report.txt", "r") as f:
        s_buf = f.readlines()

    refkernels = ["syzkaller/managers/upstream-linux-next-kasan-gce-root/kernel/"]
    for refkernel in refkernels:
        for i in range(len(s_buf)):
            s_buf[i] = s_buf[i].replace(refkernel, "")

    for i in range(len(s_buf)):
        line = s_buf[i]
        if "Call Trace" in line:
            break
    else:
        print("Call Trace not detected")
        return False
    s_buf = s_buf[i+1:]

    entry_funcs = ["do_sys", "_sys_", "syscall"]
    for i in range(len(s_buf)):
        if any(func in s_buf[i] for func in entry_funcs):
            break
    else:
        print("Entry Function not detected")
        return False
    s_buf = s_buf[:i]

    Ignore_funcs = ["kasan", "memcpy"]
    startline = 0
    for i in range(len(s_buf)):
        if any(func in s_buf[i] for func in Ignore_funcs):
            startline = i
    s_buf = s_buf[startline+1:]
    #print(s_buf)
    with open(PATH+"/callstack", "w") as f:
        for line in s_buf:
            f.write(line)
    return s_buf

def get_allocate_callstack(PATH):
    print("get_allocate_callstack() from report.txt")
    with open(PATH+"/report.txt", "r") as f:
        s_buf = f.readlines()

    refkernels = ["syzkaller/managers/upstream-linux-next-kasan-gce-root/kernel/"]
    for refkernel in refkernels:
        for i in range(len(s_buf)):
            s_buf[i] = s_buf[i].replace(refkernel, "")

    for i in range(len(s_buf)):
        line = s_buf[i]
        if "Allocated by" in line:
            break
    else:
        print("Allocated Trace not detected")
        return False
    s_buf = s_buf[i+1:]

    entry_funcs = ["do_sys", "_sys_", "syscall", "start_kernel"]
    for i in range(len(s_buf)):
        if any(func in s_buf[i] for func in entry_funcs):
            break
    else:
        print("Entry Function not detected")
        return False
    s_buf = s_buf[:i]

    Ignore_funcs = ["kasan", "memcpy"]
    startline = 0
    for i in range(len(s_buf)):
        if any(func in s_buf[i] for func in Ignore_funcs):
            startline = i
    s_buf = s_buf[startline+1:]
    return s_buf

def get_callfunctions(s_buf):
    callfunctions = []
    prevfuncname = ""
    for line in s_buf:
        line = line[:-1].strip()
        funcname = line.split(" ")[0]
        if "+" in funcname:
            funcname = funcname.split("+")[0]
        if funcname == prevfuncname:
            continue
        callfunctions += [funcname]
    return callfunctions
        
def get_cleancallstack(PATH):
    cleancallstack = []
    with open(PATH+"/callstack", "r") as f:
        s_buf = f.readlines()
    prevfuncname = ""
    for line in s_buf:
        line = line[:-1].strip()
        funcname = line.split(" ")[0]
        if "+" in funcname:
            funcname = funcname.split("+")[0]
        if funcname == prevfuncname:
            print("get_cleancallstack() funcname == prevfuncname Ignore one:", funcname)
            continue
        sourceline = line.split(" ")[1]
        if funcname+" "+sourceline not in  cleancallstack:
            cleancallstack.append(funcname+" "+sourceline)
        prevfuncname = funcname
    with open(PATH+"/cleancallstack", "w") as f:
        for line in cleancallstack:
            f.write(line+"\n")


def get_callstackfiles(PATH):
    if not os.path.exists(PATH+"/cleancallstack"):
        get_cleancallstack(PATH)
    with open(PATH+"/cleancallstack", "r") as f:
        s_buf = f.readlines()
    funclist = [line.split(" ")[1].split(":")[0] for line in s_buf]
    return funclist

# This function should be called after the the kernel in /home/zzhan173/repos/linux is formatted
# This function is used to generate 1) targetline 2) get the lines where caller call callee in the stack
def get_matchedlines_afterformat(PATH):
    #ref_linux = "/home/zzhan173/repos/reflinux"
    ref_linux = PATH + "/../linux_ref"
    #target_linux = "/home/zzhan173/repos/linux"
    target_linux = PATH + "/linux_ref"
    #if PATH[-1] == "/":
    #    PATH = PATH[:-1]
    #commit = PATH.split("/")[-1]
    #string1 = "cd "+ref_linux+"; git checkout -f "+commit
    #print(string1)
    #result = command(string1)

    filelist = get_callstackfiles(PATH)

    format_line_targetline = {}
    for filename in filelist:
        PATH1 = ref_linux + "/" + filename
        PATH2 = target_linux + "/" + filename
        result = match_targetlines.get_matchedlines_git(PATH1, PATH2)
        line_targetline = {}
        for key in result:
            line_targetline[filename + ":"+str(key)] = filename + ":" + str(result[key])
        format_line_targetline.update(line_targetline)
    with open(PATH+"/lineguidance/format_line_targetline.json", "w") as f:
        json.dump(format_line_targetline, f, indent=4, sort_keys=True)

def get_targetline_format(PATH):
    with open(PATH+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()

    targetline_format = s_buf[0][:-1].split(" ")[1]
    with open(PATH+"/targetline", "w") as f:
        f.write(targetline_format+"\n")

# get the clean call stack after formatting.
# requirement: cleancallstack, format_line_targetline which logs the matching between before-format line and after-format line
def get_cleancallstack_format(PATH):
    print("get_cleancallstack_format()")
    get_matchedlines_afterformat(PATH)

    if os.path.exists(PATH+"/cleancallstack_format_correct"):
        print("Use cleancallstack_format_correct(manual get) as cleancallstack_format_correct")
        shutil.copy(PATH+"/cleancallstack_format_correct", PATH+"/cleancallstack_format")
        #check_cleancallstack_format(PATH)
        return

    with open(PATH+"/lineguidance/format_line_targetline.json") as f:
        format_line_targetline = json.load(f)
    with open(PATH+"/cleancallstack", "r") as f:
        s_buf = f.readlines()
    cleancallstack_format = []
    for line in s_buf:
        funcname, line_ref = line[:-1].split(" ")
        line_format = format_line_targetline[line_ref]
        line_format = simplify_path(line_format)
        cleancallstack_format += [funcname+" "+line_format]

    with open(PATH+"/cleancallstack_format", "w") as f:
        for line in cleancallstack_format:
            f.write(line+"\n")
    check_result = check_cleancallstack_format(PATH)
    if not check_result:
        print("check_cleancallstack_format return False, require manual check exit()")
        exit()

# Sometimes the callstack we got from report.txt is not accurate, it ignores some simple function in the middle
# For example, 8e28bba73ed1772a6802, vfs_get_tree->squashfs_get_tree->get_tree_bdev

def check_cleancallstack_format(PATH):
    print("check_cleancallstack_format()")
    result = True
    with open(PATH+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()
    for i in range(len(s_buf) -1):
        callee = s_buf[i][:-1]
        callee_func, callee_line = callee.split(" ")
        caller = s_buf[i+1][:-1]
        
        coverline_checkresult = check_cleancallstack_format_coverline(PATH, caller, callee_func)
        src_checkresult = check_cleancallstack_format_src(PATH, caller, callee_func)
        result = coverline_checkresult or src_checkresult
        if not result:
            print("coverline_checkresult:", coverline_checkresult, "src_checkresult:", src_checkresult)
    return result

def check_cleancallstack_format_coverline(PATH, caller, callee_func):
    callee_funcs = get_callee_afterline_fromcoverline(PATH, caller)
    #print("caller:", caller, "  callee:", callee, "\ncallees in coverline:", callee_funcs, callee_func in callee_funcs)
    if not callee_funcs:
        return None
    if callee_funcs and callee_func not in callee_funcs:
        print("callee", callee_func, "not in callees of caller",caller, " in coverline", callee_funcs)
        return False
    return True

def check_cleancallstack_format_src(PATH, callerline, callee_func):
    caller_func, caller_line = callerline.split(" ")
    caller_file, caller_srcnum = caller_line.split(":")
    filepath = PATH + "/linux_ref/" + caller_file
    with open(filepath, "r") as f:
        s_buf = f.readlines()
    caller_srccode = s_buf[int(caller_srcnum)-1][:-1]
    if "->" in caller_srccode:
        return None
    if callee_func not in caller_srccode:
        print(callee_func, "not in ",caller_func, caller_line, caller_srccode)
        return False
    return True

def get_callee_afterline_fromcoverline(PATH, caller_line):
    callee_funcs = []
    with open(PATH+"/coverlineinfo", "r") as f:
        s_buf = f.readlines()
    for i in range(len(s_buf)):
        line = s_buf[i]
        if caller_line in line:
            addr = line.split(" ")[0]
            for j in range(i+1, len(s_buf)):
                nextline = s_buf[j]
                if addr in nextline:
                    continue
                nextaddr = nextline.split()[0]
                if nextaddr not in s_buf[j+1]:
                    calleefunc = nextline.split()[1]
                    callee_funcs += [calleefunc]
                    break
                elif caller_line in s_buf[j+1]:
                    calleefunc = nextline.split()[1]
                    callee_funcs += [calleefunc]
                    break
            beforeline = s_buf[i-1]
            if beforeline.split(" ")[0] == addr:
                callee_funcs += [beforeline.split(" ")[1]]
    callee_funcs = [func for func in set(callee_funcs)]
    if not callee_funcs:
        callee_funcs = get_callee_afterline_fromcompletecoverline(PATH, caller_line)
    return callee_funcs

def get_callee_afterline_fromcompletecoverline(PATH, caller_line):
    print("get_callee_afterline_fromcompletecoverline")
    caller_func, caller_linenum = caller_line.split(" ")
    callee_funcs = []
    with open(PATH+"/completecoverlineinfo", "r") as f:
        s_buf = f.readlines()
    for i in range(len(s_buf)):
        line = s_buf[i]
        if caller_line in line:
            addr = line.split(" ")[0]
            for j in range(i+1, len(s_buf)):
                nextline = s_buf[j]
                if addr in nextline:
                    continue
                nextaddr= nextline.split()[0]
                calleefunc = nextline.split()[1]
                if calleefunc == caller_func:
                    continue
                if nextaddr not in s_buf[j+1]:
                    callee_funcs += [calleefunc]
                    break
                elif caller_line in s_buf[j+1]:
                    callee_funcs += [calleefunc]
                    break
            beforeline = s_buf[i-1]
            if beforeline.split(" ")[0] == addr:
                callee_funcs += [beforeline.split(" ")[1]]
    callee_funcs = [func for func in set(callee_funcs)]
    return callee_funcs
# generate the BB where caller calls callee in callstack. 
# Requirement: cleancallstack_format (the call stack after code format), line_BBinfo.json which includes matching between line and BB
def get_mustBBs(PATH):
    print("get_mustBBs()", PATH)
    mustBBs = []
    with open(PATH+"/lineguidance/line_BBinfo.json") as f:
        line_BBinfo = json.load(f)
    with open(PATH+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()

    for line in s_buf:
        line_ref = line[:-1].split(" ")[1]
        print(line_ref)
        if line_ref in line_BBinfo and len(line_BBinfo[line_ref]) == 1:
            mustBBs += [line_BBinfo[line_ref][0]]
            print(line_BBinfo[line_ref][0])

    with open(PATH+"/mustBBs", "w") as f:
        for BB in mustBBs:
            f.write(BB + "\n")

# generate the indirectcall in refkernel.
# Requirement: cleancallstack_format (the call stack after code format), line_BBinfo.json which includes matching between line and BB
def get_indirectcalls(PATH):
    print("get_indirectcalls()")
    indirectcalls = {}
    with open(PATH+"/built-in_tag.ll", "r") as f:
        bcfile = f.readlines()
    with open(PATH+"/lineguidance/line_BBinfo.json") as f:
        line_BBinfo = json.load(f)
    with open(PATH+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()
    # get the caller callee map from the cleancallstack
    for i in range(len(s_buf)-1):
        callee = s_buf[i]
        caller = s_buf[i+1]
        callee = callee.split(" ")[0]
        callerline = caller[:-1].split(" ")[1]
        caller = caller.split(" ")[0]
        #print("callerline:", callerline)
        # only when the calller line corresponds unique BB, we generate the indirect call mapping. Thus there may be FNs which requires adding manually
        #if callerline in line_BBinfo and len(line_BBinfo[callerline]) == 1:
        #    BB = line_BBinfo[callerline][0]
        #    #print("BB:", BB)
        #    indirectcall = Check_indirectcall(bcfile, BB, callee)
        #    if indirectcall:
        #        indirectcalls[callerline] = callee
        #        print("found indirect call", caller, callee, callerline, BB)
        
        if callerline in line_BBinfo:
            directcall = False
            for BB in line_BBinfo[callerline]:
                directcall = Check_directcall(bcfile, BB, callee)
                if directcall:
                    break
            if not directcall:
                indirectcalls[callerline] = callee
                print("found indirect call", caller, callee, callerline, BB)
        else:
            print("callerline", callerline, "not in line_BBinfo")

    with open(PATH+"/indirectcalls", "w") as f:
        for callerline in indirectcalls:
            f.write(callerline + " "+indirectcalls[callerline] + "\n")


# Check if there is an indirect call to callee in the BB
# bcfile is the buffer of LLVM bc file.
def Check_indirectcall(bcfile, BB, callee):
    BBline = [line for line in bcfile if line.startswith(BB)]

    if len(BBline) > 1:
        print("there are multiple definitions for", BB)
    index = bcfile.index(BBline[0])

    indirectcall = False
    directcall = False
    while not bcfile[index+1].startswith("built-in.bc-"):
        line = bcfile[index]
        if "@"+callee in line and "call" in line:
            directcall = True
            break
        elif "call" in line and "@" not in line.split("call")[1].split("(")[0]:
            indirectcall = True
        index += 1

    if not directcall and indirectcall:
        return True
    return False

# Check if there is an direct call to callee in the BB
# bcfile is the buffer of LLVM bc file.
def Check_directcall(bcfile, BB, callee):
    BBline = [line for line in bcfile if line.startswith(BB)]

    if len(BBline) > 1:
        print("there are multiple definitions for", BB)
    index = bcfile.index(BBline[0])

    #indirectcall = False
    directcall = False
    while not bcfile[index+1].startswith("built-in.bc-"):
        line = bcfile[index]
        if "@"+callee in line and "call" in line:
            directcall = True
            break
        #elif "call" in line and "@" not in line.split("call")[1].split("(")[0]:
        #    indirectcall = True
        index += 1

    if directcall:
        return True
    return False

def add_skipfunction(configpath, skipfuncname):
    print("add_skipfunction:", skipfuncname, "in", configpath)
    with open(configpath) as f:
        config = json.load(f)
    config["13_skip_function_list"] += [skipfuncname]
    with open(configpath, 'w') as f:
        json.dump(config, f, indent=4, sort_keys=True)

def automate_addskipfunction(configfile):
    # whether the execution can be completed in timelimit
    result = False
    #configfile = "/data/zzhan173/Qemu/OOBW/pocs/0d1c3530/b74b991fb8b9/configs/ori_sock_sendmsg.json"
    casepath = configfile.split("/configs/")[0]
    string1 = "cd /home/zzhan173/Linux_kernel_UC_KLEE/; klee --config=" + configfile + " 2>" + casepath + "/output"

    #string2 = "cd /home/zzhan173/Linux_kernel_UC_KLEE/; python get_lineoutput.py output > lineoutput"
    string2 = "cd " + casepath + "; python /home/zzhan173/Linux_kernel_UC_KLEE/get_lineoutput.py output > lineoutput" 
    while True:
        result = command(string1, 600)
        # if completed the execution within time limit, it will return True
        if result:
            break
        result2 = command(string2)
        # there is a 97_calltrace option in config
        callstack_functions = get_stuckfunction.get_callstack_functions(configfile)
        skipfuncname = get_stuckfunction.get_func_percent(casepath, callstack_functions)
        add_skipfunction(configfile, skipfuncname)

# Get the common caller of allocation trace/crash trace. It can be used as entry function point
# PATH example: /data3/zzhan173/OOBR/b8fe393f999a291a9ea6/refkernel
def get_common_caller(PATH):
    reportpath = PATH + "/report.txt"
    if not os.path.exists(reportpath):
        print(reportpath, "not exist")
        return None
    with open(reportpath, "r") as f:
        s_buf = f.readlines()
    if not any("Call Trace:" in line for line in s_buf):
        return None
    if not any("Allocated by" in line for line in s_buf):
        return None
    allocate_callstack = get_allocate_callstack(PATH)
    if not allocate_callstack:
        return None
    allocate_functions = get_callfunctions(allocate_callstack)
    callstack =  get_callstack(PATH)
    if not callstack:
        return None
    crash_functions = get_callfunctions(callstack)
    print("crash_functions:", crash_functions)
    print("allocate_functions:", allocate_functions)
    for function in allocate_functions:
        if function in crash_functions:
            return function
    return None

# PATH1 example: /data3/zzhan173/OOBR/b8fe393f999a291a9ea6/refkernel
# PATH2 example: /data4/zzhan173/OOBR/b8fe393f999a291a9ea6/linux-v5.6
def generate_kleeconfig_newentry(PATH1, PATH2):
    print("generate_kleeconfig_newentry()", PATH2)
    new_entryfunc = get_common_caller(PATH1)
    print("new_entryfunc:", new_entryfunc)

    configpath = PATH2 + "/configs/config_cover_doms.json"
    if not os.path.exists(configpath):
        return
    backup = PATH2 + "/configs/config_cover_doms_old.json"
    if not os.path.exists(backup):
        string1 = "cd "+ PATH2 + "/configs; cp config_cover_doms.json config_cover_doms_old.json"
        command(string1)
    
    with open(configpath, "r") as f:
        config = json.load(f)
    oldcalltrace = config['97_calltrace']
    if not new_entryfunc:
        print("no common entry", PATH2)
        if len(oldcalltrace) > 5:
            config['97_calltrace'] = oldcalltrace[-5:]
            config['3_entry_function'] = oldcalltrace[-5]
    elif new_entryfunc not in oldcalltrace:
        print("new_entryfunc not in oldcalltrace", new_entryfunc, PATH2)
        if len(oldcalltrace) > 5:
            config['97_calltrace'] = oldcalltrace[-5:]
            config['3_entry_function'] = oldcalltrace[-5]
    else:
        print("new_entryfunc in oldcalltrace", PATH2)
        config['97_calltrace'] = oldcalltrace[oldcalltrace.index(new_entryfunc):]
        config['3_entry_function'] = new_entryfunc
    with open(configpath, "w") as f:
        json.dump(config, f, indent=4)

if __name__ == "__main__":
    #caller = "netlink_sendmsg"
    #callee = "netlink_unicast"
    #PATH = "/data/zzhan173/Qemu/OOBW/pocs/0d1c3530/b74b991fb8b9"
    #get_callBB(PATH, caller, callee)
    #get_matchedlines_afterformat(PATH)
    #get_targetline_format(PATH)
    #get_cleancallstack_format(PATH)
    #get_indirectcalls(PATH)
    #get_mustBBs(PATH)
    
    #configfile = "/data/zzhan173/Qemu/OOBW/pocs/0d1c3530/b74b991fb8b9/configs/ori_sock_sendmsg.json"
    #string1 = "cd /home/zzhan173/Linux_kernel_UC_KLEE/; klee --config=" + configfile + " 2>output"
    #print(string1)
    
    #command = Command(string1)
    #result = command.run(timeout = 60)
    #result = command(string1, 60)
    #print(result)

    #configfile = "/home/zzhan173/OOBW2020-2021/3b0c40612471/f40ddce88593/configs/fbcon_modechanged.json"
    #automate_addskipfunction(configfile)

    #PATH = "/data3/zzhan173/OOBR/b8fe393f999a291a9ea6/refkernel"
    PATH = sys.argv[1]
    result = get_common_caller(PATH)
    print(result)

    #PATH1 = sys.argv[1]
    #PATH2 = sys.argv[2]
    #generate_kleeconfig_newentry(PATH1, PATH2)
