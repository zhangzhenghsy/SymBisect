import os,sys
import subprocess
import json
from multiprocessing import Pool
import time
import compilebc,prioritylist
import ast
import shutil
import helper
import cfg_analysis
import dot_analysis

def trim_lines(buf):
    for i in range(len(buf)):
        if len(buf[i])==0:
            continue
        if buf[i][-1] == '\n':
            buf[i] = buf[i][:-1]

def trim_lines2(buf):
    for i in range(len(buf)):
        if len(buf[i])==0:
            continue
        buf[i] = buf[i].strip()

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

def get_filename_diff(p_buf,st,ed):
    fp = None
    fn = None
    for i in range(st,ed):
        if fp is not None and fn is not None:
            break
        if p_buf[i].startswith('---'):
            fn = p_buf[i][5:]
        elif p_buf[i].startswith('+++'):
            fp = p_buf[i][5:]
        elif p_buf[i].startswith('rename from'):
            fn = p_buf[i][12:]
        elif p_buf[i].startswith('rename to'):
            fp = p_buf[i][10:]

    if fp is None or fn is None:
        return None
    elif fp=='dev/null':
        return (fn, None)
    elif fn=='dev/null':
        return (None, fp)
    else:
        return (fn,fp)

def get_files(p_buf):
    print("get_files()")
    filenames=set()
    trim_lines(p_buf)
    diff_index = [i for i in range(len(p_buf)) if p_buf[i].startswith('diff')] + [len(p_buf)]
    for i in range(len(diff_index)-1):
        result=get_filename_diff(p_buf,diff_index[i],diff_index[i+1])
        if result:
            filenames.add(result)
    return filenames

def get_diff_buf(refkernel, targetkernel, PATH2):
    print("get_diff_buf()")
    #commit1 = get_commit_frompath(PATH1)
    #commit2 = get_commit_frompath(PATH2)
    #string1 = "cd "+ref_kernel+"; make mrproper; git checkout -f "+commit1
    #print(string1)
    #command(string1)
    #string1 = "cd "+target_kernel+"; make mrproper; git checkout -f "+commit2
    #print(string1)
    #command(string1)

    #if os.path.exists(PATH1+"/codeadaptation.json"):
    #    print("adapt code according to codeadaptation.json")
    #    compilebc.adapt_code(ref_kernel, PATH1+"/codeadaptation.json")
    #compilebc.format_linux(ref_kernel)
    #compilebc.format_linux(target_kernel)
    if os.path.exists(PATH2 +"/diffbuf"):
        os.remove(PATH2 +"/diffbuf")
    string1 = "git diff --no-index "+refkernel+" "+targetkernel+" >" + PATH2 +"/diffbuf"
    print(string1)
    result = command(string1)

def writelist(List, path):
    with open(path, "w") as f:
        for ele in List:
            f.write(str(ele)+"\n")

def get_matchfiles(refkernel, targetkernel, PATH1, PATH2):
    print("get_matchfiles() \nPATH1:",PATH1,"\nPATH2:",PATH2)
    print("refkernel:",refkernel,"\ntargetkernel:",targetkernel)
    #if not os.path.exists(PATH2+"/diffbuf"):
    get_diff_buf(refkernel, targetkernel, PATH2)

    with open(PATH2+"/diffbuf", "r", errors='replace') as f:
        s_buf = f.readlines()
    matchfiles = get_files(s_buf)
    writelist(matchfiles, PATH2+"/matchfiles")
    filter_matchedfiles = []
    filter_matchedfiles_dic = {}
    for (fn,fp) in matchfiles:
        #if fn == None or fp == None:
        if fn == None:
            continue
        if ".bc" in fn:
            continue
        if ".h" not in fn and ".c" not in fn:
            continue
        fn = fn.replace(refkernel+"/" , "")
        if fp:
            fp = fp.replace(targetkernel+"/" , "")
        filter_matchedfiles += [(fn,fp)]
        filter_matchedfiles_dic[fn] = fp
    print("no duplicate matching in filter_matchedfiles:",len(filter_matchedfiles) == len(filter_matchedfiles_dic))

    #writelist(filter_matchfiles, PATH2+"/filter_matchedfiles")
    with open(PATH2+"/filter_matchedfiles.json", "w") as f:
        json.dump(filter_matchedfiles_dic, f, indent=4, sort_keys=True)
    return filter_matchedfiles

# there will be limitation, what if a small block is reused for multiple times in a file
#[refkernel file] [targetkernel file]
def get_matchedlines(PATH1, PATH2):
    with open(PATH1, "r") as f:
        s_buf1 = f.readlines()
    with open(PATH2, "r") as f:
        s_buf2 = f.readlines()

    trim_lines(s_buf1)
    trim_lines(s_buf2)
    
    context_size = 2
    
    line_targetline = {}
    for i in range(2, len(s_buf1)-2):
        if len(s_buf1[i]) == 0:
            continue
        if not any(s_buf1[i]==line for line in  s_buf2):
            continue
        for j in range(2, len(s_buf2)-3):
            if s_buf1[i-2:i+3] == s_buf2[j-2:j+3]:
                if i+1 not in line_targetline:
                    line_targetline[i+1] = [j+1]
                else:
                    line_targetline[i+1] += [j+1]
    
    #multiplematchedlines = []
    filter_line_targetline = {}
    for i in line_targetline:
        if len(line_targetline[i]) > 1:
            #print("filter multiple matched lines:",i, line_targetline[i])
            continue
        filter_line_targetline[i] = line_targetline[i][0]
    #print(json.dumps(filter_line_targetline, sort_keys=True, indent=4)) 
    return filter_line_targetline

def get_matchedlines_git(PATH1, PATH2):
    string1 = "git diff --no-index "+PATH1+" "+PATH2
    print(string1)
    p_buf = command(string1)
    p_buf = [line.decode("utf-8") for line in p_buf]
    with open(PATH1, "r") as f:
        s_buf1 = f.readlines()
    with open(PATH2, "r") as f:
        s_buf2 = f.readlines()
    if len(p_buf) == 0:
        print("no difference between two files")
        filter_line_targetline = {}
        for i in range(len(s_buf1)):
            filter_line_targetline[i+1] = i+1
        return filter_line_targetline
    trim_lines(s_buf1)
    trim_lines(s_buf2)

    trim_lines(p_buf)
    line_targetline = {}

    st=0
    ed=len(p_buf)
    currentline_R = 0
    currentline_T = 0
    at_index = [i for i in range(st,ed) if p_buf[i].startswith('@@')]
    for i in range(at_index[0], len(p_buf)):
        #print(i+1, p_buf[i] )
        if p_buf[i].startswith('@@'):
            prevcurrentline_R = currentline_R
            prevcurrentline_T = currentline_T
            head = p_buf[i]
            headlist=head.split(",")
            currentline_R = int(headlist[0].split("-")[1])-1
            currentline_T = int(headlist[1].split("+")[1])-1
            if (currentline_T-currentline_R) != (prevcurrentline_T - prevcurrentline_R):
                print("(currentline_T-currentline_R) != (prevcurrentline_T - currentline_R)", head)
                print("prevcurrentline_R:",prevcurrentline_R, "prevcurrentline_T:",prevcurrentline_T)
            for j in range(1, currentline_R-prevcurrentline_R+1):
                line_targetline[prevcurrentline_R+j] = prevcurrentline_T+j
            continue

        if p_buf[i].startswith("-"):
            currentline_R += 1
        elif p_buf[i].startswith("+"):
            currentline_T += 1
        else:
            currentline_R += 1
            currentline_T += 1
            #print("currentline_R:",currentline_R, "line_targetline[currentline_R]:",currentline_T)
            line_targetline[currentline_R] = currentline_T
    
    # The final part after @@
    for j in range(len(s_buf1) - currentline_R):
        line_targetline[currentline_R+j] = currentline_T+j
    filter_line_targetline = {}
    for i in line_targetline:
        if i > len(s_buf1):
            print(PATH1, PATH2, "i:",i)
            continue
        if len(s_buf1[i-1]) == 0:
            continue
        if s_buf1[i-1] != s_buf2[line_targetline[i]-1]:
            print("matched line inaccuracy", i, line_targetline[i])
            continue
        filter_line_targetline[i] = line_targetline[i]

    #print(json.dumps(filter_line_targetline, sort_keys=True, indent=4))
    return filter_line_targetline

def get_ref_files(PATH):
    with open(PATH+"/lineguidance/line_whitelist_v1.json") as f:
        line_whitelist_v1 = json.load(f)
    file_list = []
    for line in line_whitelist_v1:
        if line.startswith("./"):
            line = line[2:]
        file_list += [line.split(":")[0]]
    return file_list

def store_matchedlines(matchedfile):
    fn,fp,refkernel,targetkernel = matchedfile
    matchedlines = get_matchedlines_git(refkernel + "/" +fn, targetkernel+"/"+fp)
    filematchedlines = {}
    for i in matchedlines:
        filematchedlines[fn+":"+str(i)] = fp+":"+str(matchedlines[i])
    output = targetkernel+"/"+fp.replace(".c", "_c_matchedlines.json")
    output = output.replace(".h", "_h_matchedlines.json")
    print("store_matchedlines in", output)
    with open(output, 'w') as f:
        json.dump(filematchedlines, f, indent=4, sort_keys=True)

# format target kernel
def format_targetkernel(targetkernel):
    print("\nformat_targetkernel()\n")
    compilebc.format_linux(targetkernel)

#PATH1: the directory where refkernel info are stored
#PATH2: the directory where targetkernel info are stored
#refkernel
#targetkernel
def get_all_matchedlines_git(refkernel, targetkernel, PATH1, PATH2):
    print("\nget_all_matchedlines_git()\n")
    #refkernel = refkernel + "/" if refkernel[-1] != "/" else refkernel
    #targetkernel = targetkernel + "/" if targetkernel[-1] != "/" else targetkernel
    t0 = time.time()
    all_matchedlines = {}
    matchedfiles = get_matchfiles(refkernel, targetkernel, PATH1, PATH2)
    ref_files = get_ref_files(PATH1)
    ref_files = [helper.simplify_path(line) for line in ref_files]
    print("ref_files:", ref_files)
    filter_matchedfiles = []
    for (fn, fp) in matchedfiles:
        #fnpath: relative path
        #fnpath = fn.split(refkernel)[1]
        #fnpath = fn
        #fp = fp.split(targetkernel)[1]
        #fp = fp[:-1] if fp[-1] == "/" else fp
        #print("fn:", fn)
        if fn in ref_files:
            if fp == None:
                print(fn,"is deleted")
                continue
            filter_matchedfiles += [(fn, fp, refkernel, targetkernel)]
    print("size of matchedfiles:", len(matchedfiles), "size of filter_matchedfiles:", len(filter_matchedfiles))
    #for ele in matchedfiles:
    #    print(ele)
    #print("cost time1:", time.time()-t0)
    with Pool(32) as p:
        p.map(store_matchedlines,   filter_matchedfiles)
    #print("cost time2:", time.time()-t0)

    for (fn, fp, refkernel, targetkernel) in filter_matchedfiles:
        inputfile = targetkernel + "/" +fp
        dstfile = inputfile.replace(targetkernel, PATH2+"/source/")
        dstfolder = os.path.dirname(dstfile)
        if not os.path.exists(dstfolder):
            os.makedirs(dstfolder)
        shutil.copy(inputfile, dstfile)

        inputfile = fp.replace(".c", "_c_matchedlines.json")
        inputfile = inputfile.replace(".h", "_h_matchedlines.json")
        inputfile = targetkernel + "/" + inputfile
        with open(inputfile, 'r') as f:
            matchedlines = json.load(f)
            all_matchedlines.update(matchedlines)
        dstfile = inputfile.replace(targetkernel, PATH2+"/source/")
        shutil.copy(inputfile, dstfile)
    with open(PATH2+"/all_matchedlines.json", 'w') as f:
        json.dump(all_matchedlines, f, indent=4, sort_keys=True)
    #print("cost time3:", time.time()-t0)
    #for refline in all_matchedlines:
    #    print(refline, all_matchedlines[refline])

def generate_linelist_targetkernel(refkernel, targetkernel, PATH1, PATH2, func_linelist_jsonfile):
    with open(PATH2+"/all_matchedlines.json") as f:
        all_matchedlines = json.load(f)
    with open(PATH2+"/filter_matchedfiles.json", "r") as f:
        filter_matchedfiles = json.load(f)

    if not os.path.exists(PATH2+"/lineguidance"):
        os.mkdir(PATH2+"/lineguidance")

    with open(PATH1+"/lineguidance/"+func_linelist_jsonfile) as f:
        func_linelist = json.load(f)

    func_linelist_targetkernel = {}
    linelist_targetkernel = []
    notchangedfiles = []
    for func in func_linelist:
        func_linelist_targetkernel[func] = []
        for line in func_linelist[func]:
            line = helper.simplify_path(line)
            filename = line.split(":")[0]
            # The file is not changed, thus keep the original line
            if filename not in filter_matchedfiles:
                if filename not in notchangedfiles:
                    notchangedfiles += [filename]
                    print(filename, "is not changed in target kernel")
                func_linelist_targetkernel[func]  += [line]
                linelist_targetkernel += [line]
            # The file is changed. And we find the corresponding line
            if line in all_matchedlines:
                func_linelist_targetkernel[func]  += [all_matchedlines[line]]
                linelist_targetkernel += [all_matchedlines[line]]
    linelist_targetkernel = list(set(linelist_targetkernel))
    linelist_targetkernel.sort()

    with open(PATH2 + "/lineguidance/" + func_linelist_jsonfile, 'w') as f:
        json.dump(func_linelist_targetkernel, f, indent=4, sort_keys=True)
    with open(PATH2 + "/lineguidance/" + func_linelist_jsonfile.replace("func_", ""), 'w') as f:
        json.dump(linelist_targetkernel, f, indent=4, sort_keys=True)

def generate_linelists_targetkernel(refkernel, targetkernel, PATH1, PATH2):
    print("\ngenerate_linelist_targetkernel()\n")
    
    # question: should we use the original blacklist or blacklist filter with refkernel bc dom tree?
    # question： should we check if the function is renamed?
    generate_linelist_targetkernel(refkernel, targetkernel,PATH1, PATH2, "func_line_blacklist.json")
    generate_linelist_targetkernel(refkernel, targetkernel,PATH1, PATH2, "func_line_blacklist_doms.json")
    generate_linelist_targetkernel(refkernel, targetkernel,PATH1, PATH2, "func_line_whitelist_doms.json")
    #generate_linelist_targetkernel(refkernel, targetkernel,PATH1, PATH2, "func_line_whitelist_v0.json")
    generate_linelist_targetkernel(refkernel, targetkernel,PATH1, PATH2, "func_line_whitelist_v1.json")

# compile target kernel into bc files
def compile_bcfiles_targetkernel(targetkernel, PATH1, PATH2):
    print("\ncompile_bcfiles_targetkernel\n")
    #if not os.path.exists(PATH2+"/config"):
    #    shutil.copy(PATH1+"/config", PATH2+"/config")
    if not os.path.exists(PATH2+"/config_withoutkasan"):
        shutil.copy(PATH1+"/config", PATH2+"/config")
        shutil.copy(PATH1+"/config_withoutkasan", PATH2+"/config_withoutkasan")
    #compilebc.format_linux(targetkernel)
    compilebc.compile_gcc(PATH2, targetkernel)
    compilebc.get_dryruncommands(targetkernel)
    compilebc.compile_bc_extra("compile", PATH2, targetkernel)
    compilebc.compile_bc_extra("copy", PATH2, targetkernel)
    compilebc.compile_bc_extra("check", PATH2, targetkernel)

def link_bclist_fromcover__targetkernel(refkernel, targetkernel, PATH1, PATH2):
    print("\nlink_bclist_fromcover__targetkernel()\n")
    coverlineinfo = PATH1+"/coverlineinfo"
    with open (coverlineinfo,"r") as f:
        s_buf =f.readlines()
    if 'number of c files' in s_buf[-4]:
        # This line only includes c files (without .h files)
        filelist =  ast.literal_eval(s_buf[-3][:-1])
        print("num of reffiles:", len(filelist))
    
    #filelist = [line.replace("/home/zzhan173/repos/linux", refkernel) for line in filelist]
    target_filelist = []
    with open(PATH2+"/filter_matchedfiles.json", "r") as f:
        filter_matchedfiles = json.load(f)
    for ref_file in filelist:
        # The file is same in ref_kernel/target_kernel
        if ref_file not in filter_matchedfiles:
            target_filelist += [ref_file.replace(refkernel, targetkernel)]
        # The file is deleted in target kernel (dont find corresponding file in target kernel)
        elif filter_matchedfiles[ref_file] == None:
            print(line,"is deleted in target kernel")
            continue
        else:
            target_filelist += [filter_matchedfiles[ref_file]]
    bcfilelist = [filename.replace(".c",".bc") for filename in target_filelist]
    print("num of targetfiles:", len(bcfilelist))
    print(bcfilelist)
    prioritylist.link_bclist(bcfilelist, PATH2 + "/built-in.bc")
    prioritylist.get_tagbcfile(PATH2)

    if not os.path.exists(PATH2+"/lineguidance/"):
        os.mkdir(PATH2+"/lineguidance/")
    #get debug symbol information from .ll file. Mapping between !num and file,lineNo
    prioritylist.get_dbginfo(PATH2)
    #Mapping between BB name and line
    prioritylist.get_BB_lineinfo(PATH2)

# Now ignore the function rename, will it result in problem? maybe not, we only use the line num to get the target BB
def get_callstack_targetkernel(refkernel, targetkernel, PATH1, PATH2):
    print("\nget_callstack_targetkernel()\n")
    with open(PATH2+"/filter_matchedfiles.json", "r") as f:
        filter_matchedfiles = json.load(f)
    with open(PATH2+"/all_matchedlines.json") as f:
        all_matchedlines = json.load(f)

    cleancallstack_format = []
    calltracefunclist = []
    require_manualcheck = False
    with open(PATH1+"/cleancallstack_format", "r") as f:
        s_buf = f.readlines()
    for line in s_buf:
        funcname, refline = line[:-1].split(" ")
        filename = refline.split(":")[0]
        # The file is not changed, thus keep the original line
        if filename not in filter_matchedfiles:
            print(line[:-1], "is not changed")
            cleancallstack_format += [line[:-1]]
            calltracefunclist += [line.split(" ")[0]]
            continue
        if refline not in all_matchedlines:
            print("\nNo corresponding line in target kernel for", line)
            if not os.path.exists(PATH2+"/cleancallstack_format_correct"):
                print("\nRequire manual get cleancallstack_format and calltracefunclist for target kernel\n")
                require_manualcheck = True
                cleancallstack_format += [funcname+" manualget"]
                calltracefunclist += [funcname]
                continue
            else:
                shutil.copy(PATH2+"/cleancallstack_format_correct", PATH2+"/cleancallstack_format")
                print("Use the manual get cleancallstack_format and calltracefunclist")
                return
        targetline = all_matchedlines[refline]
        print(line[:-1], "is changed to", funcname+" "+targetline)
        cleancallstack_format += [funcname+" "+targetline]
        calltracefunclist += [funcname]
    with open(PATH2+"/cleancallstack_format", "w") as f:
        for line in cleancallstack_format:
            f.write(line + "\n")
    with open(PATH2+"/calltracefunclist", "w") as f:
        for line in calltracefunclist:
            f.write(line+"\n")
    helper.get_targetline_format(PATH2)
    #if require_manualcheck:
    #    print("exit in advance")
    #    exit()

def get_targetline_format_targetkernel(PATH2):
    print("\nget_targetline_format_targetkernel()\n")
    helper.get_targetline_format(PATH2)

def get_BBguidance_targetkernel(PATH2):
    print("get_BBguidance_targetkernel")
    # Just used for getting CFG png for debug
    prioritylist.get_BB_whitelist(PATH2)
    dot_analysis.get_dom_files(PATH2)
    prioritylist.get_BB_whitelist_predoms(PATH2)

    cfg_analysis.get_cfg_files(PATH2)
    # used for generate low-priority BB list (the BB which cannot reach mustBB)
    helper.get_mustBBs(PATH2)
    # Make use of mustBBs to get the BB_targetBBs
    # Also require the low-priority line list: PATH + "/lineguidance/line_blacklist_doms.json"
    cfg_analysis.get_func_BB_targetBBs(PATH2)

def generate_kleeconfig_targetkernel(PATH2):
    print("\ngenerate_kleeconfig_targetkernel\n")
    # todo: do dom analysis for target kernel again (consider that we need to do source analysis to correct the func name in func_line_blacklist_refdoms.json/func_line_whitelist_refdoms.json)
    prioritylist.generate_kleeconfig(PATH2, [])
    if not os.path.exists(PATH2+"/configs"):
        os.mkdir(PATH2+"/configs")
    shutil.copy(PATH2+"/config_cover_doms.json", PATH2+"/configs/config_cover_doms.json")

if __name__ == "__main__":
    PATH2 = sys.argv[1]
    helper.get_mustBBs(PATH2)