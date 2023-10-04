import match_targetlines
import sys,os
import helper
def get_targetkernel_config(PATH1, PATH2, refkernel, targetkernel):
    print("\nget_targetkernel_config()")
    print("PATH1:",PATH1, "PATH2:",PATH2,"refkernel:",refkernel,"targetkernel:",targetkernel)
    match_targetlines.format_targetkernel(targetkernel)
    match_targetlines.get_all_matchedlines_git(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.generate_linelists_targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.compile_bcfiles_targetkernel(targetkernel, PATH1, PATH2)
    match_targetlines.link_bclist_fromcover__targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.get_callstack_targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.get_BBguidance_targetkernel(PATH2)
    match_targetlines.generate_kleeconfig_targetkernel(PATH2)
    #pick the symsize mode according to the option of refkernel config
    set_99_symsize(PATH1, PATH2)

def set_99_symsize(PATH1, PATH2):
    ref_configpath = PATH1 + "/configs/config_cover_doms.json"
    target_configpath = PATH2 + "/configs/config_cover_doms.json"
    value = helper.get_config_option(ref_configpath, "99_symsize")
    #if value:
    print("set_config_option", target_configpath, "99_symsize", value)
    helper.set_config_option(target_configpath, "99_symsize", value)

def format_path(PATH):
    PATH = PATH[:-1] if PATH[-1] == "/" else PATH
    return PATH
if __name__ == "__main__":
    PATH1 = format_path(sys.argv[1])
    PATH2 = format_path(sys.argv[2])
    refkernel = format_path(sys.argv[3])
    targetkernel = format_path(sys.argv[4])

    get_targetkernel_config(PATH1, PATH2, refkernel, targetkernel)
