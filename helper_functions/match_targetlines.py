import os,sys
import subprocess
import json
from multiprocessing import Pool
import time
import compilebc,prioritylist
import ast
import shutil
import helper

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
    filenames=set()
    trim_lines(p_buf)
    diff_index = [i for i in range(len(p_buf)) if p_buf[i].startswith('diff')] + [len(p_buf)]
    for i in range(len(diff_index)-1):
        result=get_filename_diff(p_buf,diff_index[i],diff_index[i+1])
        if result:
            filenames.add(result)
    return filenames

ref_kernel = "/data/zzhan173/repos/linux"
target_kernel = "/data/zzhan173/repos/target_linux"

#for example, ~/Qemu/OOBW/pocs/c7a91bc7/e69ec487b2c7/
def get_commit_frompath(PATH):
    if PATH[-1] == "/":
        PATH = PATH[:-1]
    if PATH.split("/")[-1] in ["alloc","crash"]:
        return PATH.split("/")[-2]
    else:
        return PATH.split("/")[-1]

def get_diff_buf(PATH1, PATH2):
    commit1 = get_commit_frompath(PATH1)
    commit2 = get_commit_frompath(PATH2)
    string1 = "cd "+ref_kernel+"; make mrproper; git checkout -f "+commit1
    print(string1)
    command(string1)
    string1 = "cd "+target_kernel+"; make mrproper; git checkout -f "+commit2
    print(string1)
    command(string1)

    compilebc.format_linux(ref_kernel)
    compilebc.format_linux(target_kernel)
    string1 = "git diff --no-index "+ref_kernel+" "+target_kernel+" >"+PATH2+"/diffbuf"
    result = command(string1)

def writelist(List, path):
    with open(path, "w") as f:
        for ele in List:
            f.write(str(ele)+"\n")

def get_matchfiles(PATH1, PATH2):
    #if not os.path.exists(PATH2+"/diffbuf"):
    get_diff_buf(PATH1, PATH2)

    with open(PATH2+"/diffbuf", "r") as f:
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
        if len(s_buf1[i-1]) == 0:
            continue
        if s_buf1[i-1] != s_buf2[line_targetline[i]-1]:
            print("matched line inaccuracy", i, line_targetline[i])
            continue
        filter_line_targetline[i] = line_targetline[i]

    #print(json.dumps(filter_line_targetline, sort_keys=True, indent=4))
    return filter_line_targetline

def get_ref_files(PATH):
    with open(PATH+"/line_whitelist_v1.json") as f:
        line_whitelist_v1 = json.load(f)
    file_list = []
    for line in line_whitelist_v1:
        if line.startswith("./"):
            line = line[2:]
        file_list += [line.split(":")[0]]
    return file_list

def get_all_matchedlines_git(PATH1, PATH2):
    t0 = time.time()
    all_matchedlines = {}
    matchedfiles = get_matchfiles(PATH1, PATH2)

    ref_files = get_ref_files(PATH1)
    ref_files = [helper.simplify_path(line) for line in ref_files]
    filter_matchedfiles = []
    for (fn, fp) in matchedfiles:
        #fnpath = fn.split("source/")[1]
        #get the relative path of file
        fnpath = fn.split("repos/linux/")[1]
        if fnpath in ref_files:
            if fp == None:
                print(fnpath,"is deleted")
                continue
            filter_matchedfiles += [(fn, fp)]
    print("size of matchedfiles:", len(matchedfiles), "size of filter_matchedfiles:", len(filter_matchedfiles))
    #for ele in matchedfiles:
    #    print(ele)
    #print("cost time1:", time.time()-t0)
    with Pool(32) as p:
        p.map(store_matchedlines,   filter_matchedfiles)
    #print("cost time2:", time.time()-t0)

    for (fn, fp) in filter_matchedfiles:
        inputfile = fp.replace(".c", "_matchedlines.json")
        with open(inputfile, 'r') as f:
            matchedlines = json.load(f)
            all_matchedlines.update(matchedlines)
        dstfile = inputfile.replace(target_kernel, PATH2+"/source")
        dstfolder = os.path.dirname(dstfile)
        if not os.path.exists(dstfolder):
            os.makedirs(dstfolder)
        shutil.copy(inputfile, dstfile)
    with open(PATH2+"/all_matchedlines.json", 'w') as f:
        json.dump(all_matchedlines, f, indent=4, sort_keys=True)
    #print("cost time3:", time.time()-t0)
    #for refline in all_matchedlines:
    #    print(refline, all_matchedlines[refline])

def store_matchedlines(matchedfile):
    fn,fp = matchedfile
    matchedlines = get_matchedlines_git(fn, fp)
    fnpath = fn.split("repos/linux/")[1]
    fppath = fp.split("repos/target_linux/")[1]
    filematchedlines = {}
    for i in matchedlines:
        filematchedlines[fnpath+":"+str(i)] = fppath+":"+str(matchedlines[i])
    output = fp.replace(".c", "_matchedlines.json")
    with open(output, 'w') as f:
        json.dump(filematchedlines, f, indent=4, sort_keys=True)

def compare_twomatches(line_target_context, line_targetline_git):
    for line in line_target_context:
        if line not in line_targetline_git:
            print(line, "line_target_context[line]:", line_target_context[line],"no match in line_targetline_git")
            continue
        if line_target_context[line] != line_targetline_git[line]:
            print(line, "line_target_context[line]:", line_target_context[line], "line_targetline_git[line]:", line_targetline_git[line])
    for line in line_targetline_git:
        if line not in line_target_context:
            print(line, "no match in line_target_context line_targetline_git[line]:" , line_targetline_git[line])

def generate_target_list(PATH1, PATH2):
    print("\n\ngenerate_target_list\n")
    # question: should we use the original blacklist or blacklist filter with refkernel bc dom tree?
    # question： should we check if the function is renamed?
    with open(PATH1+"/func_line_blacklist_doms.json") as f:
        func_line_blacklist = json.load(f)
    with open(PATH1+"/func_line_whitelist_doms.json") as f:
        func_line_whitelist = json.load(f)

    #if not os.path.exists(PATH2+"/all_matchedlines.json"):
    get_all_matchedlines_git(PATH1, PATH2)
    with open(PATH2+"/all_matchedlines.json") as f:
        all_matchedlines = json.load(f)
    with open(PATH2+"/filter_matchedfiles.json", "r") as f:
        filter_matchedfiles = json.load(f)

    func_line_blacklist2 = {}
    line_blacklist2 = []
    notchangedfiles = []
    for func in func_line_blacklist:
        func_line_blacklist2[func] = []
        for line in func_line_blacklist[func]:
            #print(line)
            line = helper.simplify_path(line)
            #print(line)
            filename = line.split(":")[0]
            if "/data/zzhan173/repos/linux/"+filename not in filter_matchedfiles:
                if filename not in notchangedfiles:
                    notchangedfiles += [filename]
                    print(filename, "is not changed in target kernel")
                func_line_blacklist2[func]  += [line]
                line_blacklist2 += [line]
            if line in all_matchedlines:
                func_line_blacklist2[func]  += [all_matchedlines[line]]
                line_blacklist2 += [all_matchedlines[line]]
    line_blacklist2 = list(set(line_blacklist2))
    line_blacklist2.sort()

    func_line_whitelist2 = {}
    line_whitelist2 = []
    for func in func_line_whitelist:
        func_line_whitelist2[func] = []
        for line in func_line_whitelist[func]:
            line = helper.simplify_path(line)
            filename = line.split(":")[0]
            if "/data/zzhan173/repos/linux/"+filename not in filter_matchedfiles:
                func_line_whitelist2[func]   += [line]
                line_whitelist2 += [line]
            if line in all_matchedlines:
                func_line_whitelist2[func]  += [all_matchedlines[line]]
                line_whitelist2 += [all_matchedlines[line]]
    line_whitelist2 = list(set(line_whitelist2))
    line_whitelist2.sort()

    with open(PATH2+"/func_line_blacklist_refdoms.json", 'w') as f:
        json.dump(func_line_blacklist2, f, indent=4, sort_keys=True)
    with open(PATH2+"/line_blacklist_refdoms.json", 'w') as f:
        json.dump(line_blacklist2, f, indent=4, sort_keys=True)

    with open(PATH2+"/func_line_whitelist_refdoms.json", 'w') as f:
        json.dump(func_line_whitelist2, f, indent=4, sort_keys=True)
    with open(PATH2+"/line_whitelist_refdoms.json", 'w') as f:
        json.dump(line_whitelist2, f, indent=4, sort_keys=True)

def compile_targetbc(PATH1, PATH2):
    print("\n\ncompile_targetbc\n")
    #if not os.path.exists(PATH2+"/config"):
    #    shutil.copy(PATH1+"/config", PATH2+"/config")
    if not os.path.exists(PATH2+"/config_withoutkasan"):
        shutil.copy(PATH1+"/config_withoutkasan", PATH2+"/config_withoutkasan")
    compilebc.compile_gcc(PATH2)
    compilebc.get_dryruncommands()
    compilebc.format_linux()
    compilebc.compile_bc_extra("compile")
    compilebc.compile_bc_extra("copy", PATH2)
    compilebc.compile_bc_extra("check", PATH2)

def link_bclist_from_refcover(PATH1, PATH2):
    print("\n\nlink_bclist_from_refcover\n")
    coverlineinfo = PATH1+"/coverlineinfo"
    with open (coverlineinfo,"r") as f:
        s_buf =f.readlines()
    if 'number of c files' in s_buf[-4]:
        filelist =  ast.literal_eval(s_buf[-3][:-1])
        print("num of reffiles:", len(filelist))
    filelist = [line.replace("/home/zzhan173/repos/linux", ref_kernel) for line in filelist]
    target_filelist = []
    with open(PATH2+"/filter_matchedfiles.json", "r") as f:
        filter_matchedfiles = json.load(f)
    for line in filelist:
        if line not in filter_matchedfiles:
            #print(line,"not in filter_matchedfiles")
            target_filelist += [line.replace(ref_kernel+"/", "")]
        elif filter_matchedfiles[line] == None:
            print(line,"is deleted in target kernel")
            continue
        else:
            target_filelist += [filter_matchedfiles[line].replace(target_kernel+"/", "")]
    #target_filelist = [filter_matchedfiles[line] for line in filelist if line in filter_matchedfiles]
    #target_filelist = [line.replace(target_kernel+"/", "") for line in target_filelist]
    print("num of targetfiles:", len(target_filelist))
    print(target_filelist)
    prioritylist.link_bclist(target_filelist, PATH2, "built-in.bc")
    prioritylist.get_tagbcfile(PATH2)

def generate_target_config(PATH, MustBBs):
    print("\n\ngenerate_target_config\n")
    # todo: do dom analysis for target kernel again (consider that we need to do source analysis to correct the func name in func_line_blacklist_refdoms.json/func_line_whitelist_refdoms.json)
    #if not os.path.exists(PATH+"/line_blacklist_doms.json"):
    shutil.copy(PATH+"/line_blacklist_refdoms.json", PATH+"/line_blacklist_doms.json")
    prioritylist.generate_kleeconfig(PATH, [], MustBBs)
    os.mkdirs(PATH+"/configs")
    shutil.copy(PATH+"/config_cover_doms.json", PATH+"/configs/config_cover_doms.json")
