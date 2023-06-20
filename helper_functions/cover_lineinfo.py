import os,sys

# Cut the coverage after triggerring the vulnerability
def cut_cover_line(PATH, targetline):
    print("cut_cover_line()")
    coverlineinfo = PATH+ "/coverlineinfo"
    with open(coverlineinfo, "r") as f:
        s_buf = f.readlines()
    
    lastindex = 0;
    for i in range(len(s_buf)):
        if targetline in s_buf[i]:
            lastindex = i
    
    if lastindex == 0:
        print("dont find the targetline in coverline :", targetline)
        return False
    else:
        print(lastindex, s_buf[lastindex])
    
    coverlist = []
    prevaddr = ""
    for line in s_buf[:lastindex+1]:
        if not line.startswith("0x"):
            continue
        addr = line.split(" ")[0]
        if addr != prevaddr:
            coverlist += [addr]
        prevaddr = addr
    
    # sometimes cover file will miss some lines in target function, resulting in FP of blacklist. Make our algorithm more robust
    with open(PATH+"/cleancallstack_format", "r") as f:
        call_buf = f.readlines()
        targetfunc = call_buf[0].split(" ")[0]
    print("targetfunc:", targetfunc)
    for line in s_buf[lastindex+1:]:
        if not line.startswith("0x"):
            continue
        if targetfunc not in line:
            continue
        addr = line.split(" ")[0]
        if addr != prevaddr:
            coverlist += [addr]
        prevaddr = addr
    
    with open(PATH+"/cover", "w") as f:
        for addr in coverlist:
            f.write(addr+"\n")
    return True
    
if __name__ == "__main__":
    PATH = "/data/zzhan173/Qemu/OOBW/pocs/a770bf51/cbf3d60329c4"
    targetline = "/home/zzhan173/repos/linux/lib/bitmap.c:1278"
    cut_cover_line(PATH, targetline)
