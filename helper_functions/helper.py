import os,sys,subprocess
import match_targetlines
import json

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

def compare_dics(dic1, dic2):
    for ele in dic1:
        if ele not in dic2:
            print(ele,"not in the latter dic")
        if dic1[ele] != dic2[ele]:
            print(ele, dic1[ele], dic2[ele])


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

def get_cleancallstack(PATH):
    cleancallstack = []
    calltracefunclist = []
    with open(PATH+"/callstack", "r") as f:
        s_buf = f.readlines()
    for line in s_buf:
        line = line[:-1].strip()
        funcname = line.split(" ")[0]
        if "+" in funcname:
            funcname = funcname.split("+")[0]
        sourceline = line.split(" ")[1]
        if funcname+" "+sourceline not in  cleancallstack:
            cleancallstack.append(funcname+" "+sourceline)
            calltracefunclist.append(funcname)
    with open(PATH+"/cleancallstack", "w") as f:
        for line in cleancallstack:
            f.write(line+"\n")
    with open(PATH+"/calltracefunclist", "w") as f:
        for line in calltracefunclist:
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
    ref_linux = "/home/zzhan173/repos/reflinux"
    target_linux = "/home/zzhan173/repos/linux"
    if PATH[-1] == "/":
        PATH = PATH[:-1]
    commit = PATH.split("/")[-1]
    string1 = "cd "+ref_linux+"; git checkout -f "+commit
    print(string1)
    result = command(string1)

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
    with open(PATH+"/format_line_targetline.json", "w") as f:
        json.dump(format_line_targetline, f, indent=4, sort_keys=True)

def get_targetline_format(PATH):
    if not os.path.exists(PATH+"/cleancallstack_format"):
        get_cleancallstack_format(PATH)

    with open(PATH+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()

    targetline_format = s_buf[0][:-1].split(" ")[1]
    with open(PATH+"/targetline", "w") as f:
        f.write(targetline_format+"\n")

# get the clean call stack after formatting.
# requirement: cleancallstack, format_line_targetline which logs the matching between before-format line and after-format line
def get_cleancallstack_format(PATH):
    if not os.path.exists(PATH+"/format_line_targetline.json"):
        get_matchedlines_afterformat(PATH)

    with open(PATH+"/format_line_targetline.json") as f:
        format_line_targetline = json.load(f)
    with open(PATH+"/cleancallstack", "r") as f:
        s_buf = f.readlines()
    cleancallstack_format = []
    for line in s_buf:
        funcname, line_ref = line[:-1].split(" ")
        line_format = format_line_targetline[line_ref]
        cleancallstack_format += [funcname+" "+line_format]

    with open(PATH+"/cleancallstack_format", "w") as f:
        for line in cleancallstack_format:
            f.write(line+"\n")

# generate the BB where caller calls callee in callstack. 
# Requirement: cleancallstack_format (the call stack after code format), line_BBinfo.json which includes matching between line and BB
def get_mustBBs(PATH):
    mustBBs = []
    with open(PATH+"/line_BBinfo.json") as f:
        line_BBinfo = json.load(f)
    with open(PATH+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()

    for line in s_buf:
        line_ref = line[:-1].split(" ")[1]
        if line_ref in line_BBinfo and len(line_BBinfo[line_ref]) == 1:
            mustBBs += [line_BBinfo[line_ref][0]]

    with open(PATH+"/mustBBs", "w") as f:
        for BB in mustBBs:
            f.write(BB + "\n")

# generate the indirectcall in refkernel.
# Requirement: cleancallstack_format (the call stack after code format), line_BBinfo.json which includes matching between line and BB
def get_indirectcalls(PATH):
    indirectcalls = {}
    with open(PATH+"/built-in_tag.ll", "r") as f:
        bcfile = f.readlines()
    with open(PATH+"/line_BBinfo.json") as f:
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
        # only when the calller line corresponds unique BB, we generate the indirect call mapping. Thus there may be FNs which requires adding manually
        if callerline in line_BBinfo and len(line_BBinfo[callerline]) == 1:
            BB = line_BBinfo[callerline][0]
            indirectcall = Check_indirectcall(bcfile, BB, callee)
            if indirectcall:
                indirectcalls[callerline] = callee
                print("found indirect call", caller, callee, callerline, BB)

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
            break;
        elif "call" in line and "@" not in line.split("call")[1].split("(")[0]:
            indirectcall = True
        index += 1

    if not directcall and indirectcall:
        return True
    return False

if __name__ == "__main__":
    caller = "netlink_sendmsg"
    callee = "netlink_unicast"
    PATH = "/data/zzhan173/Qemu/OOBW/pocs/0d1c3530/b74b991fb8b9"
    #get_callBB(PATH, caller, callee)
    #get_matchedlines_afterformat(PATH)
    get_targetline_format(PATH)
    #get_cleancallstack_format(PATH)
    get_indirectcalls(PATH)
    get_mustBBs(PATH)