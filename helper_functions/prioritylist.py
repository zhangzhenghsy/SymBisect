import os,sys
import subprocess
import ast
import json
import time
import dot_analysis
import concolic
import copy

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

def command_err(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stderr.readlines()
    return result

home_path = "/home/zzhan173/repos/Linux_kernel_UC_KLEE/build/llvm-project/build/"
def link_bclist(filelist, PATH, output="built-in.bc"):
    previouskernel = "/home/zzhan173/repos/linux/"
    newkernel = PATH+"/source/"
    link_cmd = home_path+"bin/llvm-link -o " + PATH+"/"+output
    for filename in filelist:
        bcpath = filename.replace(".c",".bc").replace(previouskernel,"")
        bcpath = newkernel + bcpath
        if not os.path.exists(bcpath):
            print(bcpath+" not exist")
            continue
        link_cmd = link_cmd + " " + bcpath
    print(link_cmd)
    result = command(link_cmd)
    print(result)

def link_allbc(PATH):
    link_cmd = "cd /home/zzhan173/repos/linux/;"
    link_cmd += home_path+'bin/llvm-link -o ' + PATH+'/built-in_all.bc `find ./ -name "*.bc" ! -name "timeconst.bc" ! -name "*.mod.bc"`'
    #base = "/home/zzhan173/repos/linux/"
    #p = subprocess.Popen(['/bin/bash','-c', link_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=base)
    #result=p.stdout.readlines()
    result = command(link_cmd)

    dis_cmd = home_path+'bin/llvm-dis ' + PATH+'/built-in_all.bc'
    result = command(dis_cmd)
    #p = subprocess.Popen(['/bin/bash','-c', dis_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=PATH)
    #result=p.stdout.readlines()

#def get_alldirctCG(PATH):
#    directCG_cmd = home_path+'bin/opt -print-callgraph '+PATH+'/built-in_all.bc 2>alldirctCG'
#    command(directCG_cmd)

# generate the direct Call graph for all compiled bc files
# get the corresponding file for function by the way
def get_func_callee_all(PATH):
    #kernel = "/home/zzhan173/repos/linux/"
    get_bclist_cmd = 'find /home/zzhan173/repos/linux/ -name "*.bc" ! -name "timeconst.bc" ! -name "*.mod.bc"'
    bclist = command(get_bclist_cmd)
    
    func_callees = {}
    func_file = {}
    for bcfile in bclist:
        #print bcfile
        bcfile = bcfile[:-1]
        directCG_cmd = home_path+'bin/opt -print-callgraph '+bcfile+' 2>localdirctCG'
        print("\n"+directCG_cmd)
        command(directCG_cmd)

        #the -print-callgraph will contain some functions which only declare in the file, we need to filter such cases
        if not os.path.exists(bcfile.replace(".bc", ".ll")):
            cmd = home_path+'bin/llvm-dis '+bcfile
            command(cmd)
        llfile = bcfile.replace(".bc", ".ll")
        funclist_fromll = get_funclist_fromll(llfile)
        func_file_fromll = get_func_file_fromll(llfile)

        func_callee = get_func_callee_1("./localdirctCG")
        #print func_callee
        for func in func_callee:
            if func not in funclist_fromll:
                continue
            #assume the all callees of function defined in .h file are also included 
            #if ".h" in func_file_fromll[func]:
            #    continue
            if func not in func_callees:
                print(func,func_file_fromll[func], func_callee[func])
                func_callees[func] = func_callee[func]
                func_file[func] = [bcfile.replace("/home/zzhan173/repos/linux/","")]
            else:
                if ".h" not in func_file_fromll[func]:
                    print("multiple definition for func ",func,"in",bcfile,"and",func_file[func])
                    func_callees[func] += func_callee[func]
                    func_file[func] += [bcfile.replace("/home/zzhan173/repos/linux/","")]
    
    with open(PATH +"/func_callees.json", 'w') as f:
        json.dump(func_callees,f, indent=4, sort_keys=True)
    with open(PATH +"/func_file.json", 'w') as f:
        json.dump(func_file,f,indent=4, sort_keys=True)

# generate the direct Call graph for a given compiled bc file
def get_func_callee_1(CGpath):
    func_callees = {}
    funcname = None
    callees = []
    external = False
    with open(CGpath,"r") as f:
        s_buf =f.readlines()
    for line in s_buf:
        if line.startswith("Call graph node for function:"):
            funcname = line.split("'")[1]
            if "." in funcname:
                funcname = funcname.split(".")[0]
            if funcname not in func_callees:
                func_callees[funcname] = []
        if not funcname:
            continue
        if " calls function" in line:
            callee = line[:-1].split(" calls function ")[1][1:-1]
            if "." in callee:
                callee = callee.split(".")[0]
            func_callees[funcname] += [callee]
        if line == "\n":
            #if len(func_callees[funcname]) == 0 and external:
            #    del func_callees[funcname]
            #external = False
            funcname = None
    return func_callees

def get_funclist_fromll(llfile):
    funclist = []
    with open(llfile,"r") as f:
        s_buf = f.readlines()
    for line in s_buf:
        if line.startswith("define"):
            funcname = line.split("@")[1].split("(")[0]
            funclist += [funcname]
    return funclist

donelist = []
# given Call graph, get the recursive callees for a given function
# then get the corresponding bclist 
def get_recursivecallees(PATH, funcname):
    with open(PATH +"/func_callees.json") as f:
        func_callees = json.load(f)
    with open(PATH +"/func_file.json") as f:
        func_file = json.load(f)
    
    for func in func_callees:
        func_callees[func] = list(set(func_callees[func]))
    calleelist = get_recursivecallee([funcname], func_callees)
    filelist = []
    for func in calleelist:
        if func not in func_file:
            print("not file name for",func)
            continue
        filelist += func_file[func]
    print("funclist ",len(calleelist))
    print(calleelist)
    filelist = list(set(filelist))
    print("filelist ",len(filelist))
    print(filelist)
    link_bclist(filelist, PATH, funcname+".bc")

def get_recursivecallee(calltrace, func_callees):
    global donelist
    funcname = calltrace[-1]
    calleelist = []
    #print funcname,calltrace
    if funcname not in func_callees:
        #print funcname,"not in func_callees"
        return []
    #print func_callees[funcname]
    for callee in func_callees[funcname]:
        if callee in calltrace:
            #print "circle call for ",callee,calltrace
            continue
        if callee in donelist:
            continue
        calleelist += [callee]
        calleelist += get_recursivecallee(calltrace+[callee],func_callees)
        donelist += [callee]
    calleelist = list(set(calleelist))
    return calleelist


def get_allfunc_file(PATH):
    with open(PATH+"/func_file.json") as f:
        another_func_file = json.load(f)
    with open(PATH+"/built-in_all.ll","r") as f:
        s_buf =f.readlines()
    llfile = PATH+"/built-in_all.ll"

    func_file = get_func_file_fromll(llfile)

    for funcname in func_file:
        filename = func_file[funcname]
        if ".h" in filename:
            continue
        if funcname not in another_func_file:
            #print funcname,"not in another_func_file"
            continue
        if filename != another_func_file[funcname].replace(".bc",".c"):
            print("not equal for",funcname, filename,another_func_file[funcname])
    return func_file

def get_func_file_fromll(llfile):
    with open(llfile,"r") as f:
        s_buf =f.readlines()
    func_file = {} 
    num_file = {}
    for line in s_buf:
        if "= !DIFile" not in line:
            continue
        num = line.split(" ")[0]
        infodic = get_line_dbginfo(line)
        filename = infodic["filename"]
        num_file[num] = filename

    for line in s_buf:
        if not line.startswith("!"):
            continue
        if line.split("(")[0].split("= ")[1] not in ["distinct !DISubprogram"]:
            continue
        infodic = get_line_dbginfo(line)
        funcname = infodic["name"]
        filenum = infodic["file"]
        filename = num_file[filenum]
        func_file[funcname] = filename
        #print funcname,filename
    return func_file


ADDR2LINE = 'addr2line'
def get_vmlinux_dbginfo(PATH):
    dumpresult = PATH+"/dumpresult"
    if not os.path.exists(dumpresult):
        print("generate dumpresult")
        string = "cd "+PATH+";objdump -d vmlinux > dumpresult"
        command(string)
        print("done!")
    
    t0=time.time()
    addrlist = []
    with open(dumpresult,"r") as f:
        s_buf = f.readlines()
    for line in s_buf:
        if line.startswith("ffff") and line[16]==":":
            addrlist += [line.split(":")[0]]
    with open(PATH+"/tmp_i","w") as f:
        for addr in addrlist:
            f.write(addr+"\n")
    image=PATH+"/"+"vmlinux"
    with open(PATH+'/tmp_i','r') as fi:
        with open(PATH+"/tmp_o",'w') as fo:
            subprocess.call([ADDR2LINE,'-afip','-e',image],stdin=fi,stdout=fo)
    t1=time.time()
    print(PATH,(t1-t0))

#[PATH]: path of directory which stores the coverage file/debuginfo file
#extract sourceinfo for coverage from debuginfo and store the info in coverlineinfo file
def get_cover_lineinfo(PATH, cover, output):
    #cover: coverage file generated by syzkaller reproducer
    #debugino: debug file (tmp_o) extracted from vmlinux
    debuginfo = PATH+"/tmp_o"
    with open(debuginfo,"r") as f:
        debug_buf = f.readlines()
    st = 0
    ed = len(debug_buf)-1

    with open(cover, "r") as f:
        s_buf = f.readlines()

    #numberlist = []
    funclist = []
    filelist = []
    lineinfolist = []
    for line in s_buf:
        #print(line[:-1])
        number = long(line[:-1],16)
        #number = 4*(number/4)
        lineinfos = get_lineinfo(debug_buf, st, ed, number)
        for lineinfo in lineinfos:
            lineinfolist += [str(hex(number))[:-1]+" "+lineinfo[0]+" "+lineinfo[1]]
            #print str(hex(number))[:-1],lineinfo[0],lineinfo[1]
            if lineinfo[0] not in funclist:
                funclist += [lineinfo[0]]
            if lineinfo[1].split(":")[0] not in filelist and ".c" in lineinfo[1]:
                filelist += [lineinfo[1].split(":")[0]]
        #numberlist += [str(hex(number))[:-1]]
        #print str(hex(number))[:-1]
    with open(output,"w") as f:
        for line in lineinfolist:
            f.write(line+"\n")
        f.write("number of c files:"+str(len(filelist))+"\n")
        f.write(str(filelist)+"\n")
        f.write("number of functions:"+str(len(funclist))+"\n")
        f.write(str(funclist)+"\n")
    #print "number of c files:",len(filelist)
    #print filelist
    #print "number of functions:",len(funclist)
    #print funclist

def link_bclist_fromcover(PATH):
    coverlineinfo = PATH+"/coverlineinfo"
    with open (coverlineinfo,"r") as f:
        s_buf =f.readlines()
    if 'number of c files' in s_buf[-4]:
        filelist =  ast.literal_eval(s_buf[-3][:-1])
        print("filelist:")
        print(filelist)
    else:
        print("filelist isnot in the reverse 3th line")
    link_bclist(filelist, PATH, "built-in.bc")

# given the address, get the information in the debuginfo    
def get_lineinfo(s_buf, st, ed, number):
    while "(inlined by)" in s_buf[st]:
        st -=1
    while "(inlined by)" in s_buf[ed]:
        ed -=1
    mid = (st+ed)/2
    while "(inlined by)" in s_buf[mid]:
        mid -=1
    #print st,ed,mid
    line = s_buf[mid]
    midnumber = long(line.split(":")[0], 16)
    #print "number:",hex(number),"midnumber:",hex(midnumber)

    if st == mid:
        for lineindex in range(st,ed+1):
            line = s_buf[lineindex]
            if "(inlined by)" in line:
                continue
            midnumber = long(line.split(":")[0], 16)
            if midnumber == number:
                return get_singleinfo(s_buf, lineindex)
        return []

    if midnumber == number:
        return get_singleinfo(s_buf, mid)
    elif midnumber < number:
        return get_lineinfo(s_buf, mid, ed, number)
    else:
        return get_lineinfo(s_buf, st, mid, number)

# given index of instruction in debuginfo, get the information
def get_singleinfo(s_buf, mid):
    #print "get_singleinfo:",mid
    totalinfo = []
    line = s_buf[mid]
    funcname = line.split(" ")[1]
    sourceinfo = line[:-1].split(" ")[3]
    totalinfo += [(funcname, sourceinfo)]

    while "(inlined by)" in s_buf[mid+1]:
        mid +=1
        line = s_buf[mid]
        funcname = line[:-1].split("inlined by) ")[1].split(" ")[0]
        sourceinfo = line[:-1].split(" ")[5]
        totalinfo += [(funcname, sourceinfo)]
    return totalinfo

#[number]: ffffffff817ac799 for example
# get the index in dumpresult for the given address
def get_dump_line(s_buf,st,ed, addr):
    if 'ff' not in s_buf[st]:
        st += 1
        return get_dump_line(s_buf,st,ed,addr)
    if 'ff' not in s_buf[ed]:
        ed -= 1
        return get_dump_line(s_buf,st,ed,addr)
    
    staddr = s_buf[st][:16]
    if staddr == addr:
        return st
    edaddr = s_buf[ed][:16]
    if edaddr == addr:
        return ed

    mid = (int)((st+ed)/2)
    if 'ff' not in s_buf[mid]:
        mid +=1

    midaddr = s_buf[mid][:16]
    if midaddr < addr:
        return get_dump_line(s_buf,mid,ed,addr)
    else:
        return get_dump_line(s_buf,st,mid,addr)

#[addr] example: 0xffffffff817ac799
# get the corresponding complete instructions addresses for the given BB address from dumpresult
def get_bb_addrs(s_buf, addr):
    addr = addr[2:]
    st = 0
    ed = len(s_buf) - 1
    index = get_dump_line(s_buf,st,ed, addr)
    addrs = ['0x'+addr]
    index +=1
    while '__sanitizer_cov_trace_pc' not in s_buf[index] and s_buf[index] != "\n":
        addr = '0x'+s_buf[index][:16]
        if addr not in addrs:
            addrs += [addr]
        index +=1
    return addrs

# for the BB addresses, try to generate the corresponding complete instructions addresses
# it requires dumpresult and coverage file
# it will be used in get_line_whitelist()
def get_complete_coverage(PATH):
    vmlinux = PATH + '/vmlinux'
    if not os.path.exists(vmlinux):
        print("no vmlinux")
        return

    dumpresult = PATH+"/dumpresult"
    if not os.path.exists(dumpresult):
        print("generate dumpresult")
        string = "cd "+PATH+";objdump vmlinux > dumpresult"
        command(string)
    with open(dumpresult,'r') as f:
        dumpresult = f.readlines()

    cover = PATH+"/cover"
    if not os.path.exists(cover):
        print("no coverage file")
        return
    with open(cover,'r') as f:
        bbcover = f.readlines()

    completeaddrs = []
    for line in bbcover:
        addr = line[:-1]
        #print(addr)
        bbaddrs = get_bb_addrs(dumpresult, addr)
        #print(bbaddrs)
        completeaddrs += bbaddrs

    with open(PATH+"/completecover",'w') as f:
        for addr in completeaddrs:
            f.write(addr+"\n")

#remove the duplicate, remove the prefix directory, sort the list
def refine_lineinfolist(lineinfolist):
    lineinfolist = list(set(lineinfolist))
    lineinfolist = [info for info in lineinfolist if "?" not in info]
    lineinfolist = [info.replace("/home/zzhan173/repos/linux/","") for info in lineinfolist]
    lineinfolist.sort(key = lambda x:int(x.split(":")[1]))
    lineinfolist.sort(key = lambda x:x.split(":")[0])
    return lineinfolist

# for each func in coverage file, get the source code line numbers for the covered instructions
# it requires completecoverlineinfo
# it will be used in get_line_blacklist()
def get_line_whitelist(PATH):
    lineinfo = PATH+"/completecoverlineinfo"
    func_whitelist = {}
    whitelist = []
    with open(lineinfo,"r") as f:
        s_buf = f.readlines()
    for line in s_buf:
        line = line[:-1]
        #print line
        if "number of c files" in line:
            break
        addr,func,info = line.split(" ")
        if func not in func_whitelist:
            func_whitelist[func] = [info]
            whitelist += [info]
            continue
        if info != func_whitelist[func][-1]:
            func_whitelist[func] += [info]
            whitelist += [info]
    
    for func in func_whitelist:
        func_whitelist[func] = refine_lineinfolist(func_whitelist[func])
    whitelist = refine_lineinfolist(whitelist)
    with open(PATH +"/func_line_whitelist.json", 'w') as f:
        json.dump(func_whitelist,f, indent=4, sort_keys=True)
    with open(PATH +"/line_whitelist.json", 'w') as f:
        json.dump(whitelist,f, indent=4, sort_keys=True)

# given an addr, get the complete addrs of the corresponding function
# s_buf is the dumpresult, addr_buf is the address of each line in s_buf (used for index function, which is more efficiency)
# addr example : ffffffff81004471
def get_func_addrs(PATH, addr, s_buf, addr_buf):
    t0 = time.time()
    #linelist = [line for line in s_buf if line.startswith(addr)]
    #print("get_func_addrs cost time1: ",  time.time()-t0)
    #if len(linelist) > 1:
    #    print("multiple corresponding lines in dumpresult: ", linelist)
    #line = linelist[0]
    #index = s_buf.index(line)
    index = addr_buf.index(addr)

    previndex = index-1
    while not s_buf[previndex].endswith(">:\n"):
        previndex -= 1
    funcname = s_buf[previndex].split("<")[1].split(">:")[0]
    while not s_buf[index] == "\n":
        index += 1
    addrlist = s_buf[previndex+1:index]
    addrlist = [line.split(":")[0] for line in addrlist if ":" in line]
    print(addr, "get_func_addrs() ", funcname, s_buf[previndex+1][:16], s_buf[index-1][:16], "addrlist:", len(addrlist))
    return set(addrlist)

def get_complete_func_addrs(PATH):
    t0 = time.time()
    cover = PATH+"/cover"
    with open(cover,'r') as f:
        bbcover = f.readlines()
    with open(PATH+"/dumpresult", "r") as f:
        s_buf = f.readlines()
    addr_buf = []
    for line in s_buf:
        if line.startswith("ff") and ":" in line:
            addr_buf += [line.split(":")[0]]
        else:
            addr_buf += [""]
    print("generate addr_buf correctly:", len(addr_buf)==len(s_buf))

    coveraddrs = [line[2:-1] for line in bbcover]
    complete_func_addrs = set()

    for coveraddr in coveraddrs:
        if coveraddr in complete_func_addrs:
            continue
        complete_func_addrs = complete_func_addrs.union(get_func_addrs(PATH, coveraddr, s_buf, addr_buf))
    print("get_complete_func_addrs cost time: ", time.time()-t0)
    return complete_func_addrs

# for each func in debuginfo (from vmlinux), get the corresponding source code line numbers from debuginfo
# update: consider the inlined function, that we should not collect the source code lines from the whole debuginfo. 
# Instead, we should collect the completelines from the functions in the coverage
# it requires the debuginfo
# it will be used in get_line_blacklist()
def get_line_completelist(PATH):
    debuginfo = PATH+"/tmp_o"
    func_completelist = {}
    completelist = []

    complete_func_addrs = get_complete_func_addrs(PATH)
    t0 = time.time()
    addr = "0xff"
    with open(debuginfo,"r") as f:
        s_buf = f.readlines()
    #count = 0
    for line in s_buf:
        #if count%1000 == 0:
        #    print("count:", count, "time:",time.time()-t0)
        #count += 1
        line = line[:-1]
        if "??" in line:
            continue
        if line.startswith("0xff"):
            addr = line.split(":")[0][2:]
        if addr not in complete_func_addrs:
            continue
        if "(inlined by)" not in line:
            func = line.split(" ")[1]
            info = line.split(" ")[3]
        else:
            func = line.split("inlined by) ")[1].split(" ")[0]
            info = line.split("inlined by) ")[1].split(" ")[2]
        if func not in func_completelist:
            func_completelist[func] = []
        if info not in func_completelist[func]:
            func_completelist[func] += [info]
            completelist += [info]
    for func in func_completelist:
        func_completelist[func] = refine_lineinfolist(func_completelist[func])
    completelist = refine_lineinfolist(completelist)
    with open(PATH+"/func_line_completelist.json", 'w') as f:
        json.dump(func_completelist, f, indent=4, sort_keys=True)
    with open(PATH+"/line_completelist.json", 'w') as f:
        json.dump(completelist, f, indent=4, sort_keys=True)
    print("get_line_completelist cost time:", time.time()-t0)


# for each func in func_line_whitelist, get the source code line numbers in the first BB, which is missed in coverage files.
# it's a makeup for line_whitelist, trying to avoid FP when generating line_blacklist
# it requires dumpresult of vmlinux, and debuginfo
def get_line_entryBBlist(PATH):
    with open(PATH +"/func_line_whitelist.json") as f:
        line_whitelist = json.load(f)

    dumpresult = PATH+"/dumpresult"
    with open(dumpresult,'r') as f:
        dumpresult = f.readlines()

    debuginfo = PATH+"/tmp_o"
    with open(debuginfo,"r") as f:
        debug_buf = f.readlines()
    st = 0
    ed = len(debug_buf)-1

    func_entrylist = {}
    entrylist = []
    index = 0
    while index < (len(dumpresult)-1):
        line = dumpresult[index]
        line = line[:-1]
        #print line
        if ">:" in line:
            func = line.split(" ")[1][1:-2]
            #only extracting the bblist for functions in whitelist(coverage)
            if func not in line_whitelist:
                index += 1
                continue
            func_entrylist[func] = []
            index +=1
            while '__sanitizer_cov_trace_pc' not in dumpresult[index]:
                if index == len(dumpresult)-1:
                    break
                #if dumpresult[index] == "\n":
                #    break
                if not dumpresult[index].startswith("ffff"):
                    break
                addr = long(dumpresult[index][:16],16)
                #print hex(addr)
                lineinfos = get_lineinfo(debug_buf, st, ed, addr)
                #source code line information
                linelist = [lineinfo[1] for lineinfo in lineinfos]
                func_entrylist[func] += linelist
                index += 1
            func_entrylist[func] = list(set(func_entrylist[func]))
            entrylist += func_entrylist[func]
            #func_entrylist[func].sort()
            #print func,func_entrylist[func]
        index +=1 
    for func in func_entrylist:
        func_entrylist[func] = refine_lineinfolist(func_entrylist[func])
    entrylist = refine_lineinfolist(entrylist) 
    with open(PATH+"/func_line_entryBBlist.json", 'w') as f:
        json.dump(func_entrylist, f, indent=4, sort_keys=True)
    with open(PATH+"/line_entryBBlist.json", 'w') as f:
        json.dump(entrylist, f, indent=4, sort_keys=True)
    #print(func_entrylist['do_mount'])

def get_line_blacklist(PATH):
    func_line_blacklist = {}
    line_blacklist = []
    with open(PATH +"/func_line_completelist.json") as f:
        func_line_completelist = json.load(f)

    with open(PATH +"/func_line_whitelist.json") as f:
        func_line_whitelist = json.load(f)

    with open(PATH +"/func_line_entryBBlist.json") as f:
        func_line_entryBBlist = json.load(f)

    for func in func_line_whitelist:
        whitelist = func_line_whitelist[func]
        if func in func_line_entryBBlist:
            entryBBlist = func_line_entryBBlist[func]
        else:
            entryBBlist = []
        blacklist = []
        for lineinfo in func_line_completelist[func]:
            if lineinfo not in whitelist and lineinfo not in entryBBlist:
                blacklist += [lineinfo]
        blacklist = list(set(blacklist))
        #blacklist.sort()
        func_line_blacklist[func] = blacklist
        line_blacklist += blacklist
    
    for func in func_line_blacklist:
        func_line_blacklist[func] = refine_lineinfolist(func_line_blacklist[func])
    line_blacklist = refine_lineinfolist(line_blacklist)
    ##delete the repo path prefix of the line info
    #BasePath = "/home/zzhan173/repos/linux/"
    #line_blacklist2 = {}
    #for func in line_blacklist:
    #    line_blacklist2[func] = []
    #    for info in line_blacklist[func]:
    #        newinfo = info.replace(BasePath, "")
    #        line_blacklist2[func] += [newinfo]
        #print func
        #print line_blacklist2[func]

    with open(PATH+"/func_line_blacklist.json", 'w') as f:
        json.dump(func_line_blacklist, f, indent=4, sort_keys=True)
    with open(PATH+"/line_blacklist.json", 'w') as f:
        json.dump(line_blacklist, f, indent=4, sort_keys=True)

#def get_blacklist(PATH):
#    blacklist = []
#
#    with open(PATH +"/line_blacklist.json") as f:
#        line_blacklist = json.load(f)
#
#    for func in line_blacklist:
#        for info in line_blacklist[func]:
#            if "?" in info:
#                continue
#            blacklist += [info]
#
#    blacklist.sort()
#    return blacklist

def generate_kleeconfig(PATH, option = "", parameterlist = []):
    config = {}

    #bcfile = PATH+"/do_mount_tag.bc"
    #bcfile = PATH+"/cover.bc"
    bcfile =  PATH+"/built-in_tag.bc"
    #config["2_bitcode"] = "/home/zzhan173/repos/Linux_kernel_UC_KLEE/configs/built-in_tag.bc"
    config["2_bitcode"] = bcfile
    
    # should be different in different cases
    #entryfunc = "do_mount"
    entryfunc = ""
    config["3_entry_function"] = entryfunc
    
    #target_bb_list = ["built-in.bc-do_mount-46"]
    target_bb_list = []
    config["10_target_bb_list"] = target_bb_list
    
    low_priority_bb_list = []
    config["11_low_priority_bb_list"] = low_priority_bb_list
    
    low_priority_function_list = []
    config["12_low_priority_function_list"] = low_priority_function_list
    config["13_skip_function_list"] = ["llvm.read_register.i64", "llvm.write_register.i64"]
    
    with open(PATH + "/line_blacklist_filterwithBB.json") as f:
        low_priority_line_list_BB = json.load(f)
    print("size of low_priority_line_list_BB:", len(low_priority_line_list_BB))
    with open(PATH +"/line_blacklist_filterwithfunctioncall.json") as f:
        low_priority_line_list_func = json.load(f)
    print("size of low_priority_line_list_func:", len(low_priority_line_list_func))
    #with open(PATH + "/line_blacklist_filterwithdoms.json") as f:
    #    low_priority_line_list_doms = json.load(f)
    #print("size of low_priority_line_list_doms:", len(low_priority_line_list_doms))

    if option == "functioncall":
        config["90_low_priority_line_list"] = low_priority_line_list_func
        output = PATH+"/config_cover_func.json"
    elif option == "BB":
        config["90_low_priority_line_list"] = low_priority_line_list_BB
        output = PATH+"/config_cover_BB.json"
    elif option == "doms":
        with open(PATH + "/line_blacklist_filterwithdoms.json") as f:
            low_priority_line_list_doms = json.load(f)
        print("size of low_priority_line_list_doms:", len(low_priority_line_list_doms))
        config["90_low_priority_line_list"] = low_priority_line_list_doms
        output = PATH+"/config_cover_doms.json"
    else:
        config["90_low_priority_line_list"] = []
        output = PATH+"/config_cover.json"
    if parameterlist:
        output = output.replace(".json", "_concolic.json")
        all_index_value = concolic.get_concolicmap(parameterlist)
        config["96_concolic_map"] = all_index_value
        
    config["91_print_inst"] = False
    config["92_indirectcall"] = {}
    config["93_whitelist"] = {}
    config["94_looplimit"] = 10
    config["95_kernelversion"] = "v5.8-rc6"
    with open(output, 'w') as f:
        json.dump(config, f, indent=4, sort_keys=True)

# get_BB_lineinfo from bcfile
def get_BB_lineinfo(PATH):
    bbfile = PATH+"/built-in_tag.ll"
    bb_lines ={}
    line_bb = {}
    with open(bbfile,"r") as f:
        s_buf =f.readlines()
    
    with open(PATH+"/dbginfo.json") as f:
        dbginfo = json.load(f)

    for line in s_buf:
        if line.startswith("built-in.bc-"):
            bb = line.split(":")[0]
            bb_lines[bb] = []
        if line.startswith("define "):
            continue
        if '!dbg !' in line:
            dbgnum = line[:-1].split("!dbg ")[1]
            if "!srcloc" in dbgnum:
                dbgnum = dbgnum.split(", !srcloc ")[0]
            if "!llvm.loop" in dbgnum:
                dbgnum = dbgnum.split(", !llvm.loop ")[0]
            if dbgnum in dbginfo:
                if "lineinfo" in dbginfo[dbgnum] and dbginfo[dbgnum]["lineinfo"] not in bb_lines[bb]:
                    lineinfo = dbginfo[dbgnum]["lineinfo"]
                    bb_lines[bb] += [lineinfo]
                    if lineinfo not in line_bb:
                        line_bb[lineinfo] = [bb]
                    else:
                        line_bb[lineinfo] += [bb]
            else:
                print("no dbginfo for",dbgnum)
    output = PATH+"/BB_lineinfo.json"
    with open(output, 'w') as f:
        json.dump(bb_lines, f, indent=4, sort_keys=True)

    output = PATH+"/line_BBinfo.json"
    with open(output, 'w') as f:
        json.dump(line_bb, f, indent=4, sort_keys=True)

def get_line_dbginfo(line):
    infodic = {}
    infolist = line.split("(")[1].split(")")[0].split(", ")
    for info in infolist:
        key = info.split(": ")[0]
        value = info.split(": ")[1]
        if key in ["filename","name"]:
            value = value[1:-1]
        infodic[key] = value
    return infodic

def get_dbginfo(PATH, bbfile=None):
    if not bbfile:
        bbfile = PATH+"/built-in_tag.ll"
    else:
        bbfile = PATH+"/"+bbfile
    with open(bbfile,"r") as f:
        s_buf =f.readlines()
    print(len(s_buf))
    num_info = {}

    for line in s_buf:
        if "= !DIFile" not in line:
            continue
        num = line.split(" ")[0]

        infodic = get_line_dbginfo(line)
        num_info[num] = infodic
    
    for line in s_buf:
        #if "= distinct !DILexicalBlock" not in line:
        if not line.startswith("!"):
            continue
        if line.split("(")[0].split("= ")[1] not in ["distinct !DISubprogram", "distinct !DILexicalBlock", "!DILexicalBlockFile"]:
            continue
        num = line.split(" ")[0]

        infodic = get_line_dbginfo(line)
        num_info[num] = infodic

    for line in s_buf:
        if not line.startswith("!"):
            continue
        #!379322 = !{!285, !263, !263, !263, !163, !162}
        if not "(" in line:
            continue
        #print line
        num = line.split(" ")[0]

        infodic = get_line_dbginfo(line)
        if 'file' not in infodic:
            if "scope" in infodic:
                scope = infodic["scope"]
                infodic['file'] = num_info[scope]["file"]

        if 'file' in infodic:
            filenum = infodic['file']
            filename = num_info[filenum]["filename"]
            infodic["filename"] = filename
            if "line" in infodic:
                infodic["lineinfo"] = filename+":"+infodic["line"]
        num_info[num] = infodic
        #print num,num_info[num]

    output = PATH+"/dbginfo.json"
    with open(output, 'w') as f:
        json.dump(num_info, f, indent=4, sort_keys=True)

#get line whitelist (including coverage whitelist and entryBBlinelist)
def get_completewhitelist(PATH):
    with open(PATH +"/line_whitelist.json") as f:
        line_whitelist = json.load(f)
    with open(PATH +"/line_entryBBlist.json") as f:
        line_entryBBlist = json.load(f)

    whitelist = line_whitelist+line_entryBBlist
    whitelist = refine_lineinfolist(whitelist)
    return whitelist

def get_line_blacklist_filterwithBB(PATH):
    with open(PATH +"/line_blacklist.json") as f:
        blacklist = json.load(f)

    #with open(PATH +"/line_whitelist.json") as f:
    #    line_whitelist = json.load(f)

    #with open(PATH +"/line_entryBBlist.json") as f:
    #    line_entryBBlist = json.load(f)
   
    #whitelist = line_whitelist+line_entryBBlist
    #whitelist = refine_lineinfolist(whitelist)
    whitelist = get_completewhitelist(PATH)
    filterlist = []

    with open(PATH+"/BB_lineinfo.json") as f:
        BB_lineinfo = json.load(f)
    with open(PATH+"/line_BBinfo.json") as f:
        line_BBinfo = json.load(f)

    for blackline in blacklist:
        if blackline not in line_BBinfo:
            continue
        BBlist = line_BBinfo[blackline]
        # all lines that are in the same BB of given line
        linelist = []
        for BB in BBlist:
            linelist += BB_lineinfo[BB]
        #print blackline,BB,linelist
        if any(line in whitelist for line in linelist):
            filterlist += [blackline]
            print("filter line:",blackline)

    for filterline in filterlist:
        blacklist.remove(filterline)
    with open(PATH+"/line_blacklist_filterwithBB.json","w") as f:
        json.dump(blacklist, f, indent=4, sort_keys=True)

# get the source code line numbers which contain function call
def get_line_blacklist_filterwithfunctioncall(PATH):
    with open(PATH+"/dbginfo.json", "r") as f:
        dbginfo = json.load(f)
    
    line_functioncall = []
    llfile = PATH+"/built-in_tag.ll"
    with open(llfile, "r") as f:
        s_buf =f.readlines()
    for line in s_buf:
        if " call " not in line:
            continue
        if "@llvm." in line:
            continue
        if "asm" in line:
            continue
        if "!dbg !" not in line:
            print(line)
            continue
        dbgnum = line[:-1].split("!dbg ")[1]
        dbglineinfo = dbginfo[dbgnum]["lineinfo"]
        line_functioncall += [dbglineinfo]
    line_functioncall = refine_lineinfolist(line_functioncall)

    #with open(PATH +"/line_blacklist.json") as f:
    with open(PATH +"/line_blacklist_filterwithBB.json") as f:
        blacklist = json.load(f)
    filterwithfunctioncall = []
    for line in blacklist:
        if line in line_functioncall:
            filterwithfunctioncall += [line]

    #line_functioncall = list(set(line_functioncall))
    #line_functioncall.sort(key = lambda x:int(x.split(":")[1]))
    #line_functioncall.sort(key = lambda x:x.split(":")[0])
    #output = PATH+"/line_functioncall.json"
    with open(PATH+"/line_functioncall.json", 'w') as f:
        json.dump(line_functioncall, f, indent=4, sort_keys=True)

    with open(PATH+"/line_blacklist_filterwithfunctioncall.json", 'w') as f:
        json.dump(filterwithfunctioncall, f, indent=4, sort_keys=True)
    return line_functioncall
    #for line in dbglineinfolist:
    #    print line

def get_line_blacklist_filterwithdoms(PATH):
    print(PATH +"/line_blacklist_filterwithBB.json")
    with open(PATH +"/line_blacklist_filterwithBB.json") as f:
        blacklist = json.load(f)

    whitelist = get_completewhitelist(PATH)

    with open(PATH+"/line_BBinfo.json") as f:
        line_BBinfo = json.load(f)
    whiteBBlist = []
    for line in whitelist:
        if line in line_BBinfo:
            whiteBBlist += line_BBinfo[line]
    #whiteBBlist = [line_BBinfo[line] for line in whitelist if line in line_BBinfo]
    #print("whiteBBlist: \n",whiteBBlist)

    blackBBlist = []
    for line in blacklist:
        if line in line_BBinfo:
            blackBBlist += line_BBinfo[line]
    #blackBBlist = [line_BBinfo[line] for line in blacklist if line in line_BBinfo]
    #print("blackBBlist: \n", blackBBlist)
    funclist = [BB.split(".bc-")[1].split("-")[0] for BB in blackBBlist]
    funclist = list(set(funclist))
    print("number of func in funclist:",len(funclist))
    #print(funclist)
    #return

    #BB:BBlist: if BB is executed, then all BBs in BBlist must be executed
    BB_mustBBs = {}
    for func in funclist:
        #print(func)
        func_BB_mustBBs = dot_analysis.get_node_mustnodes(PATH, func)
        #print(func,"BB_mustBBs:\n",func_BB_mustBBs)
        BB_mustBBs.update(func_BB_mustBBs)

    #print("BB_mustBBs:\n", json.dumps(BB_mustBBs, sort_keys=True, indent=4))
    total_mustBBs = []
    for whiteBB in whiteBBlist:
        func = whiteBB.split(".bc-")[1].split("-")[0]
        if func not in funclist:
            continue
        # it's possible that a BB doesn't have any mustBB, for example, BB-0 and then two separate branches
        if whiteBB not in BB_mustBBs:
            continue
        total_mustBBs += BB_mustBBs[whiteBB]

    filterlist = []
    for blackline in blacklist:
        if blackline not in line_BBinfo:
            continue
        blackBBlist = line_BBinfo[blackline]
        for blackBB in blackBBlist:
            if blackBB in total_mustBBs:
                filterlist += [blackline]
                print("filter line:",blackline)
                break
    
    for filterline in filterlist:
        blacklist.remove(filterline)
    with open(PATH+"/line_blacklist_filterwithdoms.json","w") as f:
        json.dump(blacklist, f, indent=4, sort_keys=True)

def get_whiteBBlist(PATH):
    whitelist = get_completewhitelist(PATH)
    with open(PATH+"/line_BBinfo.json") as f:
        line_BBinfo = json.load(f)
    whiteBBlist = []
    for line in whitelist:
        if line in line_BBinfo:
            whiteBBlist += line_BBinfo[line]
    return whiteBBlist

# get the BBs which dominate anyline in whitelist, and union them with previous whiteBBlist
def get_BB_whitelist_predoms(PATH):
    whiteBBlist = get_whiteBBlist(PATH)
    funclist = [BB.split(".bc-")[1].split("-")[0] for BB in whiteBBlist]
    funclist = list(set(funclist))

    BB_mustBBs = dot_analysis.get_func_BB_premustBBs(PATH, funclist)
    total_mustBBs = copy.deepcopy(whiteBBlist)
    for whiteBB in whiteBBlist:
        if whiteBB not in BB_mustBBs:
            continue
        total_mustBBs += BB_mustBBs[whiteBB]
    total_mustBBs = list(set(total_mustBBs))
    total_mustBBs.sort()
    return total_mustBBs

# get the lines which dominate anyline in whitelist, and union them with previous whitelist
def get_line_whitelist_predoms(PATH):
    with open(PATH+"/BB_lineinfo.json") as f:
        BB_lineinfo = json.load(f)
    
    BB_whitelist_doms = get_BB_whitelist_predoms(PATH)
    line_whitelist_doms = []
    for BB in BB_whitelist_doms:
        if BB not in BB_lineinfo:
            continue
        line_whitelist_doms += BB_lineinfo[BB]
    
    line_whitelist_doms = list(set(line_whitelist_doms))
    line_whitelist_doms.sort()
    with open(PATH+"/line_whitelist_predoms.json", 'w') as f:
        json.dump(line_whitelist_doms, f, indent=4, sort_keys=True)
    return line_whitelist_doms

# get the BBs which post dominate anyline in whitelist, and union them with previous whiteBBlist
# We don't need to generate the post dominate BBs for function in call trace (they are terminated due to bug in refkernel)
def get_BB_whitelist_postdoms(PATH, calltracefunclist):
    whiteBBlist = get_whiteBBlist(PATH)
    funclist = [BB.split(".bc-")[1].split("-")[0] for BB in whiteBBlist]
    funclist = list(set(funclist))
 
    if calltracefunclist:
        print("don't get_BB_whitelist_postdoms for calltrac function :", [func for func in calltracefunclist if func in funclist])
        funclist = [func for func in funclist if func not in calltracefunclist]

    BB_mustBBs = dot_analysis.get_func_BB_postmustBBs(PATH, funclist)
    total_mustBBs = whiteBBlist
    for whiteBB in whiteBBlist:
        if whiteBB not in BB_mustBBs:
            continue
        total_mustBBs += BB_mustBBs[whiteBB]

    total_mustBBs = list(set(total_mustBBs))
    total_mustBBs.sort()
    return total_mustBBs

# get the lines which post dominate anyline in whitelist, and union them with previous whitelist
def get_line_whitelist_postdoms(PATH, calltracefunclist = []):
    with open(PATH+"/BB_lineinfo.json") as f:
        BB_lineinfo = json.load(f)
    
    BB_whitelist_doms = get_BB_whitelist_postdoms(PATH, calltracefunclist)
    line_whitelist_doms = []
    for BB in BB_whitelist_doms:
        if BB not in BB_lineinfo:
            continue
        line_whitelist_doms += BB_lineinfo[BB]

    line_whitelist_doms = list(set(line_whitelist_doms))
    line_whitelist_doms.sort()
    with open(PATH+"/line_whitelist_postdoms.json", 'w') as f:
        json.dump(line_whitelist_doms, f, indent=4, sort_keys=True)
    return line_whitelist_doms

def get_line_blacklist_doms_postdoms_calltrace(PATH):
    with open(PATH +"/func_line_blacklist.json") as f:
        func_line_blacklist = json.load(f)
    line_func = {}
    for func in func_line_blacklist:
        for line in func_line_blacklist[func]:
            line_func[line] = func

    with open(PATH +"/line_blacklist_filterwithBB.json") as f:
        blacklist = json.load(f)
    
    if os.path.exists(PATH+"/calltracefunclist"):
        with open(PATH+"/calltracefunclist", "r") as f:
            calltracefunclist = f.readlines()
            calltracefunclist = [line[:-1] for line in calltracefunclist]
    else:
        print("no", PATH+" calltracefunclist")
    line_whitelist_predoms = get_line_whitelist_predoms(PATH)
    line_whitelist_postdoms = get_line_whitelist_postdoms(PATH, calltracefunclist)
    
    line_blacklist_doms_postdoms_calltrace = []
    for line in blacklist:
        func = line_func[line]
        if line in line_whitelist_predoms:
            print("filter ", func, line, " Predominate")
            continue
        if line in line_whitelist_postdoms:
            print("filter ", func, line, " Postdominate")
            continue
        line_blacklist_doms_postdoms_calltrace += [line]
    with open(PATH+"/line_blacklist_doms_postdoms_calltrace.json","w") as f:
        json.dump(line_blacklist_doms_postdoms_calltrace, f, indent=4, sort_keys=True)


def get_line_blacklist_filterwithfunctioncall_predoms(PATH):
    with open(PATH +"/line_blacklist_filterwithfunctioncall.json") as f:
        low_priority_line_list_func = json.load(f)
    low_priority_line_list_func_predom = []

    if not os.path.exists(PATH +"/line_whitelist_predoms.json"):
        get_line_whitelist_predoms(PATH)
    with open(PATH +"/line_whitelist_predoms.json") as f:
        line_whitelist_predoms = json.load(f)
    for line in low_priority_line_list_func:
        if line not in line_whitelist_predoms:
            low_priority_line_list_func_predom += [line]
        else:
            print("filter blacklist_func with predoms", line)
    with open(PATH+"/line_blacklist_func_predoms.json", 'w') as f:
        json.dump(low_priority_line_list_func_predom, f, indent=4, sort_keys=True)

if __name__ == "__main__":
    #link_bclist(filelist)
    
    option = sys.argv[1]
    #PATH = sys.argv[2]
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/c7a91bc7/e69ec487b2c7/O0result"
    PATH = "/home/zzhan173/Qemu/OOBW/pocs/c7a91bc7/e69ec487b2c7"
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/433f4ba1/63de3747"
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/eb73190f/dd52cb879063"
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/253a496d/b3c424eb6a1a"
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/813961de/e195ca6cb6f2"
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/3619dec5/7daf201d7fe8"
    #PATH = "/home/zzhan173/Qemu/OOBW/pocs/033724d6/04300d66f0a0"
    #1) get and store debuginfo from vmlinux (get dumpresult of vmlinux by the way)
    if option == "get_vmlinux_dbginfo":
        PATH = sys.argv[2]
        get_vmlinux_dbginfo(PATH)
    #2) get coverline info vmlinux
    elif option == "get_cover_lineinfo":
        cover = PATH+"/cover"
        output = PATH+"/coverlineinfo"
        get_cover_lineinfo(PATH, cover, output)
    #2.5) compile kernels to bcfiles in repos/linux
    #3) link the files included in coverlineinfo
    elif option == "link_bclist_fromcover":
        link_bclist_fromcover(PATH)
    #elif option == "link_allbc":
    #    link_allbc(PATH)
    #elif option == "get_allfunc_file":
    #    get_allfunc_file(PATH)
    ##get callees for each function in all bc files seprately
    #elif option == "get_func_callee_all":
    #    get_func_callee_all(PATH)
    ##get recursive callees and link them together
    #elif option == "get_recursivecallees":
    #    funcname = sys.argv[2]
    #    get_recursivecallees(PATH, funcname)
    #4) get the complete instruction addresses in coverage with the help of dumpresult
    elif option == "get_complete_coverage":
        get_complete_coverage(PATH)
        cover = PATH+"/completecover"
        output = PATH+"/completecoverlineinfo"
        get_cover_lineinfo(PATH, cover, output)
    #5) get list of source code lines from complete coverage instruction addresses
    elif option == "get_line_whitelist":
        get_line_whitelist(PATH)
    #6) get  list of all source code lines in the kernel from debug information
    elif option == "get_line_completelist":
        get_line_completelist(PATH)
    #7) get list of source code lines of entry BB of each function
    elif option == "get_line_entryBBlist":
        get_line_entryBBlist(PATH)
    #8) blacklist = completelist - whitelist - entryBBlist
    elif option == "get_line_blacklist":
        get_line_blacklist(PATH)
    #elif option == "get_dbginfo":
    #    get_dbginfo(sys.argv[2],sys.argv[3])
    #8.5) get built-in_tag.ll from built-in.ll
    #9) if any line in a BB is in whitelist, then all lines in BB shouldn't be in blacklist
    elif option == "get_line_blacklist_filterwithBB":
        #get debug symbol information from .ll file. Mapping between !num and file,lineNo
        get_dbginfo(PATH)
        #Mapping between BB name and line
        get_BB_lineinfo(PATH)
        #if a BB contains line in whitelist(from cover file), then all instructions in the BB shouldn't be in blacklist
        get_line_blacklist_filterwithBB(PATH)
    #10) only include the lines which calls a function in the blacklist
    elif option == "get_line_blacklist_filterwithfunctioncall":
        get_line_blacklist_filterwithfunctioncall(PATH)
        #PATH += "/O0result"
    #11) if any line in a BB is in whitelist, all BBs that dom/postdom the BB should not be in blacklist
    #(cd ~/repos/Linux_kernel_UC_KLEE;source environment.sh);cd PATH;mkdir doms;mkdir postdoms;cd doms;opt -dot-dom-only ../built-in_tag.bc;cd ../postdoms;opt -dot-postdom-only ../built-in_tag.bc
    elif option == "get_line_blacklist_filterwithdoms":
        get_line_blacklist_filterwithdoms(PATH)
    elif option == "get_line_blacklist_filterwithfunctioncall_predoms":
        get_line_blacklist_filterwithfunctioncall_predoms(PATH)
    elif option == "get_line_blacklist_doms_postdoms_calltrace":
        get_line_blacklist_doms_postdoms_calltrace(PATH)
    #12) get config file
    elif option == "generate_kleeconfig_filterwithfunctioncall":
        generate_kleeconfig(PATH, "functioncall")
    elif option == "generate_kleeconfig_filterwithfunctioncallordoms_concolic":
        parameterlist = ["", ("p","./file0\000"),("p","tmpfs\000"), "", ("p", "\x6d\x70\x6f\x6c\x3d\x3d\x93\x74\x61\x74\x69\x63\x3a\x36\x2d\x36\x3a")]
        generate_kleeconfig(PATH, "functioncall", parameterlist)
        generate_kleeconfig(PATH, "doms", parameterlist)
        #use the union blacklist of functioncall and doms
        generate_kleeconfig(PATH, "functioncall_doms", parameterlist)
    elif option == "generate_kleeconfig_filterwithBB":
        generate_kleeconfig(PATH, "BB")
    elif option == "generate_kleeconfig_filterwithdoms":
        generate_kleeconfig(PATH, "doms")
