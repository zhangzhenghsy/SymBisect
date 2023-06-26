import helper
import json
import os,sys
import match_targetlines
import shutil
import get_refkernel_results
from multiprocessing import Pool

def get_targetkernel_config(PATH1, PATH2, refkernel, targetkernel):
    print("\nget_targetkernel_config()")
    print("PATH1:",PATH1, "PATH2:",PATH2,"refkernel:",refkernel,"targetkernel:",targetkernel)
    match_targetlines.format_targetkernel(targetkernel)
    match_targetlines.get_all_matchedlines_git(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.generate_linelists_targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.compile_bcfiles_targetkernel(targetkernel, PATH1, PATH2)
    #match_targetlines.link_bclist_fromcover__targetkernel("/home/zzhan173/OOBW2022/c993ee0f9f81/91265a6da44d/linux_ref/", targetkernel, PATH1, PATH2)
    match_targetlines.link_bclist_fromcover__targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.get_callstack_targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.get_BBguidance_targetkernel(PATH2)
    match_targetlines.generate_kleeconfig_targetkernel(PATH2)

repo_PATH = {
  "linux":"/home/zzhan173/repos/linux/"
}
def get_targetkernel(PATH, repo, commit):
    string1 = "cd "+ repo + ";git archive -o " + PATH+"/"+commit+".tar " + commit
    print(string1)
    helper.command(string1)
    
    if not os.path.exists(PATH+"/kernel"):
        os.mkdir(PATH+"/kernel")
    string1 = "cd "+PATH+"; tar -xf "+commit+".tar -C " +PATH+"/kernel"
    print(string1)
    helper.command(string1)
    if not os.path.exists(PATH+"/kernel/Makefile"):
        print("generate target kernel fail")
        return False
        #exit()

def clean_refkernel(refkernel):
    string1 = "cd "+refkernel+";make mrproper"
    print(string1)
    helper.command(string1)
#Type: OOBR. We store different types in different directories
def prepare_inputs(Type, hashvalue, targetkernel):
    if Type == "OOBR":
        PATH1 = "/data3/zzhan173/OOBR/"+hashvalue+"/refkernel"
        refkernel = PATH1+ "/linux_ref"
    PATH2 = "/data/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
    if os.path.exists("/data3/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel):
        shutil.rmtree("/data3/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel)

    #if os.path.exists(PATH2+"/configs/config_cover_doms.json"):
    #    print("already generate", PATH2+"/configs/config_cover_doms.json  continue")
    #    return
    print("prepare_inputs:", Type, hashvalue, "targetkernel:",targetkernel)
    if not os.path.exists(PATH2):
        os.makedirs(PATH2)
    repo,commit = targetkernel.split("-")
    repopath = repo_PATH[repo]
    result = get_targetkernel(PATH2, repopath, commit)
    if result == False:
        return False
    targetkernel = PATH2+"/kernel"

    clean_refkernel(refkernel)
    return PATH1,PATH2,refkernel,targetkernel
def clean_files(PATH):
    if os.path.exists(PATH+"/kernel"):
        string1 = "cd "+PATH+"/kernel;make mrproper"
        print(string1)
        helper.command(string1)
    string1 = "cd "+PATH+"/kernel;rm -r source"
    print(string1)
    helper.command(string1)

    string1 = "cd "+PATH+"/kernel;rm -r *.tar"
    print(string1)
    helper.command(string1)


if __name__ == "__main__":
    #PATH = "/data/zzhan173/test"
    #repo = "/home/zzhan173/repos/linux"
    #tag = "v5.4"
    #get_targetkernel(PATH, repo, tag)
    Type = "OOBR"
    casePATH = "/home/zzhan173/Linux_kernel_UC_KLEE/cases/"+Type+"cases_complete"
    with open(casePATH, "r") as f:
        s_buf = f.readlines()
        hashlist = [line[:-1] for line in s_buf]
    with open("/home/zzhan173/Linux_kernel_UC_KLEE/cases/"+Type+"_targetkernels.json", "r") as f:
        OOBR_targetkernels = json.load(f)
    #for hashvalue in OOBR_targetkernels:
    for hashvalue in hashlist:
        #if hashvalue != "02617ac69815ae324053c954118c2dc7ba0e59b2":
        #    continue
        for targetkernel in OOBR_targetkernels[hashvalue]:
            inputpaths = prepare_inputs(Type, hashvalue, targetkernel)
            if not inputpaths:
                continue
            PATH1,PATH2,refkernel,targetkernel = inputpaths
            #get_targetkernel_config(PATH1,PATH2,refkernel,targetkernel)
            string1 = "cd /home/zzhan173/Linux_kernel_UC_KLEE/; python3 helper_functions/get_targetkernel_config.py "+PATH1+" "+PATH2+" "+refkernel+" "+targetkernel+" > "+PATH2+"/get_targetkernel_config_log"
            print(string1)
            helper.command(string1)
            # clean not useful file to save the storage
            clean_files(PATH2)
    klee_inputs = [] 
    for hashvalue in OOBR_targetkernels:
        for targetkernel in OOBR_targetkernels[hashvalue]:
            PATH2 = "/data/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
            config = PATH2+"/configs/config_cover_doms.json"
            output = PATH2+"/configs/output"
            if os.path.exists(config):
                klee_inputs += [(config, output)]
    with Pool(20) as p:
        p.map(get_refkernel_results.run_klee, klee_inputs)
