
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
        if "endif" in line and "KBUILD_CFLAGS += -Os" in s_buf[i-1]:
            insert = True
            s_buf2 += ["KBUILD_CFLAGS   += -fno-inline-small-functions\n"]

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
