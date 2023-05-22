import match_targetlines



if __name__ == "__main__":
    PATH1 = "/data4/zheng/OOBW2022/c993ee0f9f81/91265a6da44d/"
    PATH2 = "/data4/zheng/OOBW2022/c993ee0f9f81/v5.17"
    refkernel = "/data4/zheng/OOBW2022/c993ee0f9f81/91265a6da44d/linux_ref/"
    targetkernel = "/home/zzhan173/repos/linux/"
    #print("ref_files:", ref_files)
    #match_targetlines.format_targetkernel(targetkernel)
    #match_targetlines.get_all_matchedlines_git(refkernel, targetkernel, PATH1, PATH2)
    #match_targetlines.generate_linelists_targetkernel(refkernel, targetkernel, PATH1, PATH2)
    #match_targetlines.compile_bcfiles_targetkernel(targetkernel, PATH1, PATH2)
    #match_targetlines.link_bclist_fromcover__targetkernel("/home/zzhan173/OOBW2022/c993ee0f9f81/91265a6da44d/linux_ref/", targetkernel, PATH1, PATH2)
    match_targetlines.get_callstack_targetkernel(refkernel, targetkernel, PATH1, PATH2)
    match_targetlines.get_BBguidance_targetkernel(PATH2)
    match_targetlines.generate_kleeconfig_targetkernel(PATH2)
