import helper
import json
import os,sys
import match_targetlines
import shutil
import get_refkernel_results
from multiprocessing import Pool
import get_prioritylists

repo_PATH = {
  "linux":"/home/zzhan173/repos/linux/"
}
refdisk = "/data3/"
targetdisk = "/data4/"

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
    #if Type == "OOBR":
    PATH1 = refdisk + "zzhan173/"+Type+"/"+hashvalue+"/refkernel"
    refkernel = PATH1+ "/linux_ref"
    PATH2 = targetdisk + "zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
    if os.path.exists(PATH2+"/configs/config_cover_doms.json"):
        return PATH1,PATH2,refkernel,PATH2+"/kernel"
    #if os.path.exists("/data3/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel):
    #    shutil.rmtree("/data3/zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel)

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

def get_targetkernel_config(arguments):
    Type, hashvalue, targetkernel = arguments
    PATH2 = targetdisk + "zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
    #if os.path.exists(PATH2+"/configs/config_cover_doms.json"):
    #    print("already generated config_cover_doms.json, skip")
    #    return
    inputpaths = prepare_inputs(Type, hashvalue, targetkernel)
    if not inputpaths:
        print("inputpaths generated fail for", Type, hashvalue, targetkernel)
        return
    PATH1,PATH2,refkernel,targetkernel = inputpaths
    if not os.path.exists(PATH1):
        print(PATH1, "not exists")
        return
    string1 = "cd /home/zzhan173/Linux_kernel_UC_KLEE/; python3 helper_functions/get_targetkernel_config.py "+PATH1+" "+PATH2+" "+refkernel+" "+targetkernel+" > "+PATH2+"/get_targetkernel_config_log"
    print(string1)
    helper.command(string1)
    # clean not useful file to save the storage
    clean_files(PATH2)

def get_targetkernel_configs(Type, specific_hashvalue = None, specific_targetkernel=None):
    #casePATH = "/home/zzhan173/Linux_kernel_UC_KLEE/cases/"+Type+"cases_complete"
    #with open(casePATH, "r") as f:
    #    s_buf = f.readlines()
    #    hashlist = [line[:-1] for line in s_buf]
    with open(targetdisk + "zzhan173/"+Type+"_targetkernels.json", "r") as f:
        hash_targetkernels = json.load(f)
    #for hashvalue in OOBR_targetkernels:
    intputlist = []
    #for hashvalue in hashlist:
    for hashvalue in hash_targetkernels:
        if specific_hashvalue:
            if hashvalue != specific_hashvalue:
                continue
        if hashvalue in get_prioritylists.total_skipcases:
            print("skip", hashvalue)
            continue
        for targetkernel in hash_targetkernels[hashvalue]:
            if specific_targetkernel and targetkernel != specific_targetkernel:
                continue
            PATH2 = targetdisk + "zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
            config = PATH2+"/configs/config_cover_doms.json"

            if os.path.exists(config):
                print(config,"already generated\n")
                helper.set_config_option(config, "99_symsize", False)
                continue
            intputlist += [(Type, hashvalue, targetkernel)]
    print("length of inputlist:", len(intputlist))
    with Pool(25) as p:
        p.map(get_targetkernel_config, intputlist)

def run_klees(Type, specific_hashvalue = None, specific_targetkernel = None):
    with open(targetdisk + "zzhan173/"+Type+"_targetkernels.json", "r") as f:
        hash_targetkernels = json.load(f)
    klee_inputs = [] 
    for hashvalue in hash_targetkernels:
        if specific_hashvalue:
            if hashvalue != specific_hashvalue:
                continue
        for targetkernel in hash_targetkernels[hashvalue]:
            if specific_targetkernel and targetkernel!=specific_targetkernel:
                continue
            PATH2 = targetdisk + "zzhan173/"+Type+"/"+hashvalue+"/"+targetkernel
            config = PATH2+"/configs/config_cover_doms.json"
            output = PATH2+"/configs/output"

            if not os.path.exists(config):
                print(config, "not exist, skip")
                continue

            with open(config, "r") as f:
                klee_config = json.load(f)
            target_line_list = klee_config["4_target_line_list"]
            target_line_list = [line for line in target_line_list if line != "manualget"]
            if len(target_line_list) == 0:
                with open(output, "w") as f:
                    f.write("target line not exist")
                print(hashvalue, targetkernel, "target line not exist")
                continue


            #if os.path.exists(output):
            #    print("already generate the output, continue")
            #    continue

            PATH1 = refdisk + "zzhan173/"+Type+"/"+hashvalue+"/refkernel"
            helper.generate_kleeconfig_newentry(PATH1, PATH2)
            if os.path.exists(config):
                klee_inputs += [(config, output)]
            else:
                print(config, "not exist")
    print("size of klee_inputs:", len(klee_inputs))
    with Pool(50) as p:
        p.map(get_refkernel_results.run_klee, klee_inputs)

def clean_LTS_targetkernels():
    PATH = "/data4/zzhan173/OOBW/"
    for dir in os.listdir(PATH):
        for subdir in os.listdir(PATH+"/"+dir):
            if len(subdir.split(".")) >= 3:
                path = PATH + "/" + dir + "/" + subdir
                print(path)
                helper.command("rm -rf "+ path)

if __name__ == "__main__":
    #clean_LTS_targetkernels()
    #exit()
    #PATH = "/data/zzhan173/test"
    #repo = "/home/zzhan173/repos/linux"
    #tag = "v5.4"
    #get_targetkernel(PATH, repo, tag)
    specifichash = None
    specific_targetkernel = None
    if len(sys.argv) > 1:
        specifichash = sys.argv[1]
    if len(sys.argv) > 2:
        specific_targetkernel = sys.argv[2]
    Type = "OOBW"
    #refdisk = "/data3/"
    #Type = "OOBW"
    #Type = "UAF"
    
    get_targetkernel_configs(Type, specifichash, specific_targetkernel)
    run_klees(Type, specifichash, specific_targetkernel)

    
