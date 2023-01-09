# We need more accurate line guidance besides low-prioirty linelist
import os,sys
import subprocess
import json
import ast
import cfg_analysis

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

#parse the result from LLVM BB_lines analyzer and get the dictionary for each function
def get_BB_lines_dic(PATH):
    with open(PATH+"/completecoverlineinfo", "r") as f:
        completecoverlineinfo = f.readlines()
        funcnamelist = ast.literal_eval(completecoverlineinfo[-1][:-1])

    if not os.path.exists(PATH+"/order_func_whitelines/func_BB_lines"):
        os.mkdir(PATH+"/order_func_whitelines/func_BB_lines")
        os.mkdir(PATH+"/order_func_whitelines/func_line_BBs")
    
    PATH += "/order_func_whitelines/"
    BB_lines = PATH + "/BB_lines"
    with open(BB_lines, "r") as f:
        s_buf = f.readlines()
    
    func_BB_lines = {}
    func_line_BBs = {}

    for line in s_buf:
        line = line[:-1]
        if line.startswith("Function: "):
            funcname = line.split(": ")[1]
            if funcname in func_BB_lines:
                print("multiple definition for functions:", funcname)
            func_BB_lines[funcname] = {}
            func_line_BBs[funcname] = {}
        elif line.startswith("BB: "):
            BB = line.split("BB: ")[1]
            func_BB_lines[funcname][BB] = []
        elif line.startswith("Line: "):
            Line = line.split("Line: ")[1]
            func_BB_lines[funcname][BB] += [Line]
            if Line not in func_line_BBs[funcname]:
                 func_line_BBs[funcname][Line] = []
            func_line_BBs[funcname][Line] += [BB]
    #    func_BB_lines[funcname] = sorted(func_BB_lines[funcname].items(), key = lambda x: x[0].split("-")[1])
    for funcname in func_BB_lines:
        if funcname not in funcnamelist:
            continue
        func_BB_lines[funcname] = {key:value for key, value in sorted(func_BB_lines[funcname].items(), key=lambda x: int(x[0].split("-")[-1]))}
        with open(PATH +"/func_BB_lines/"+funcname+".json", 'w') as f:
            json.dump(func_BB_lines[funcname], f, indent=4)
    for funcname in func_line_BBs:
        if funcname not in funcnamelist:
            continue
        func_line_BBs[funcname] =  {key:value for key, value in sorted(func_line_BBs[funcname].items(), key=lambda x: int(x[0].split(":")[1]))}
        with open(PATH +"/func_line_BBs/"+funcname+".json", 'w') as f:
            json.dump(func_line_BBs[funcname], f, indent=4)
    with open(PATH +"/func_BB_lines", 'w') as f:
        json.dump(func_BB_lines, f, indent=4)
    with open(PATH +"/func_line_BBs", 'w') as f:
        json.dump(func_line_BBs, f, indent=4)

#input: PATH+"/completecoverlineinfo"
def get_func_whitelist_inorder(PATH, funcname):
    #coverlineinfo = PATH + "/completecoverlineinfo"
    coverlineinfo = PATH + "/completecoverlineinfo_filter"

    with open(coverlineinfo, "r") as f:
        s_buf = f.readlines()

    func_lines = [line[:-1] for line in s_buf if " "+funcname+" " in line]
    func_lines = [line for line in func_lines  if line.startswith("0x")]

    filter_func_lines = []
    pre_sourceline = ""
    for line in func_lines:
        sourceline = line.split(" ")[2]
        if sourceline == pre_sourceline:
            continue
        pre_sourceline = sourceline
        filter_func_lines += [line]
    return filter_func_lines
    #for line in filter_func_lines:
    #    print(line)

# input PATH+"/completecoverlineinfo" PATH+"/built-in_tag.bc"
def get_func_BBlist_inorder(PATH, funcname):
    filter_func_lines = get_func_whitelist_inorder(PATH, funcname)
    with open(PATH+"/order_func_whitelines/linelist_inorder/"+funcname, 'w') as f:
        for line in filter_func_lines:
            f.write(line+"\n")

    #used for split calling the same function for multiple times
    BB_reachBBs = cfg_analysis.get_BB_reachBBs(PATH, funcname)
    if not BB_reachBBs:
        return None
    
    BBs = []
    prevBB = ""
    with open(PATH+"/order_func_whitelines/func_line_BBs/"+funcname+".json", 'r') as f:
        line_BBs = json.load(f)
    
    cmov_lines = get_cmov_lines(PATH)
    for line in filter_func_lines:
        if "/home/zzhan173/repos/linux/" not in line:
            continue
        sourceinfo = line.split("/home/zzhan173/repos/linux/")[1]
        if sourceinfo not in line_BBs:
            print(sourceinfo, "not in", funcname, "line_BBs")
            continue
        BB = line_BBs[sourceinfo]
        # ignore the same BB (both lines exist in the same BB)
        if BB == prevBB:
            continue
        if sourceinfo in cmov_lines:
            print("cmove line:", sourceinfo)
            BB.append("cmove line")
        BBs += [BB]
        prevBB = BB
        print(sourceinfo, BB)

    
    
    # When a line has multiple corresponding BBs, then we don’t log the BB relationship (to avoid corner cases)
    # When BB1 cannot reach BB2, it implies that BB2 is in another function call
    BBs2 = []
    #BB_targetBB = {}
    prevBB = ""
    for BBlist in BBs:
        if len(BBlist) > 1:
            prevBB = ""
            BBs2 += [""]
            continue
        currentBB = BBlist[0]
        if prevBB:
            if currentBB not in BB_reachBBs[prevBB]:
                print(prevBB,"cannot reach", currentBB, ", implies another function call")
                BBs2 += ["----------"]
        #if prevBB != "":
        #    BB_targetBB[prevBB] = currentBB
        BBs2 += [currentBB]
        prevBB = currentBB
    with open(PATH+"/order_func_whitelines/BBlist_inorder/"+funcname, 'w') as f:
        for line in BBs2:
            f.write(line+"\n")
    return BBs2

def get_func_BB_targetBB(PATH, funcname):
    BBs2 = get_func_BBlist_inorder(PATH, funcname)
    if not BBs2:
        return {}
    ## currently we ignore the functions which are called for multiple times
    # update: use new strategy. see details in https://docs.google.com/document/d/1D8kYmhZGw8P2ax_5IRhzA6FmlZlw-OrYv4JAsaUSu_o/edit?usp=sharing
    #if "----------" in BBs2:
    #    return {}
    BB_childBBs = cfg_analysis.get_BB_childBBs(PATH, funcname)
    if not BB_childBBs:
        return {}
    
    BB_targetBB = {}
    prevBB = ""
    for line in BBs2:
        currentBB = line
        if currentBB == "----------":
            prevBB = ""
            continue
        if prevBB:
            # Only when BB1 has more than multiple child BBs
            if currentBB in BB_childBBs[prevBB] and len(BB_childBBs[prevBB]) >1:
                print("find a BB_targetBB map:", prevBB, currentBB)
                if prevBB not in BB_targetBB:
                    BB_targetBB[prevBB] = []
                if currentBB not in BB_targetBB[prevBB]:
                    BB_targetBB[prevBB] += [currentBB]
        prevBB = currentBB
    
    BB_targetBB_filter = {}
    for BB in BB_targetBB:
        if len(BB_targetBB[BB]) > 1:
            print(BB, "has multiple target BBs, skip")
            continue
        BB_targetBB_filter[BB] = BB_targetBB[BB][0]
    with open(PATH +"/order_func_whitelines/BB_targetBB/"+funcname+".json", 'w') as f:
            json.dump(BB_targetBB_filter, f, indent=4)
    
    return BB_targetBB_filter

Ignore_funcnamelist = ["trace_hardirqs_off", "rcu_lock_acquire"]
# prerequirement: completecoverlineinfo_filter
def get_all_func_BB_targetBB(PATH):
    if not os.path.exists(PATH+"/order_func_whitelines"):
        os.mkdir(PATH+"/order_func_whitelines")
        os.mkdir(PATH+"/order_func_whitelines/BBlist_inorder")
        os.mkdir(PATH+"/order_func_whitelines/linelist_inorder")
        os.mkdir(PATH+"/order_func_whitelines/func_BB_lines")
        os.mkdir(PATH+"/order_func_whitelines/func_line_BBs")
        os.mkdir(PATH+"/order_func_whitelines/BB_targetBB")

    cfg_analysis.get_cfg_files(PATH)
    with open(PATH+"/completecoverlineinfo_filter", "r") as f:
        completecoverlineinfo = f.readlines()
        funcnamelist = ast.literal_eval(completecoverlineinfo[-1][:-1])
    funcnamelist = [funcname for funcname in funcnamelist if funcname not in Ignore_funcnamelist]
    
    total_BB_targetBB = {}
    for funcname in funcnamelist:
        #print("get_func_BBlist_inorder for", funcname)
        #get_func_BBlist_inorder(PATH, funcname)
        print("get_func_BB_targetBB() for", funcname)
        local_BB_targetBB = get_func_BB_targetBB(PATH, funcname)
        total_BB_targetBB.update(local_BB_targetBB)
    
    with open(PATH +"/order_func_whitelines/BB_targetBB/total.json", 'w') as f:
            json.dump(total_BB_targetBB, f, indent=4)

# cmove, cmovb, cmova, , cmovbe, cmovns, cmovg, cmovge, cmovl
def get_cmov_lines(PATH):
    if os.path.exists(PATH+"/order_func_whitelines/cmov_lines"):
        with open(PATH+"/order_func_whitelines/cmov_lines", "r") as f:
            sourcelinelist = f.readlines()
        sourcelinelist = [line[:-1] for line in sourcelinelist]
        return sourcelinelist

    print("get_cmov_lines:")
    with open(PATH+"/dumpresult", "r") as f:
        s_buf = f.readlines()
    
    instlist = [line for line in s_buf if "cmov" in line]
    addrlist = set([line.split(":")[0] for line in instlist])
    #addrlist.sort()
    #print(addrlist)

    with open(PATH+"/completecoverlineinfo_filter", "r") as f:
        s_buf = f.readlines()
    s_buf = [line[2:] for line in s_buf if "0x" in line]

    sourcelinelist = [line.split(" ")[2][:-1] for line in s_buf if line.split(" ")[0] in addrlist]
    sourcelinelist = [line.split("/home/zzhan173/repos/linux/")[1] for line in sourcelinelist]
    sourcelinelist = list(set(sourcelinelist))
    print(sourcelinelist)

    #for Line in sourcelinelist:
    #    print(Line[:-1])
    with open(PATH+"/order_func_whitelines/cmov_lines", "w") as f:
        for line in sourcelinelist:
            f.write(line+"\n")
    return sourcelinelist


if __name__ == "__main__":
    PATH = "/home/zzhan173/OOBW2020-2021/e812cbbbbbb1/a0d54b4f5b21"
    funcname = "vfs_parse_fs_param"
    #get_func_whitelist_inorder(PATH, funcname)
    #get_BB_lines_dic(PATH)
    
    #get_func_BBlist_inorder(PATH, funcname)
    #get_all_func_BBlist_inorder(PATH)
    
    get_all_func_BB_targetBB(PATH)
    #get_cmov_lines(PATH)

    #get_func_BB_targetBB(PATH, "alloc_fs_context")
