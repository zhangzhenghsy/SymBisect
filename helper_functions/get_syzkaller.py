import sys, os
import subprocess

def command(string1):
    p=subprocess.Popen(string1, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result=p.stdout.readlines()
    return result

def get_go12_syzkaller(commit, i386=None):
    os.environ['GOPATH'] = "/home/zzhan173/syzkaller/GO12/gopath"
    os.environ['GOROOT'] = "/home/zzhan173/syzkaller/GO12/goroot"
    os.environ['PATH'] = os.environ['GOROOT'] + "/bin:" + os.environ['GOPATH'] + "/bin:" + os.environ['PATH']
    string1 = "cd /home/zzhan173/syzkaller/GO12/gopath/src/github.com/google/syzkaller; git checkout -f "+commit+";"
    #print(string1)
    command(string1)
    string1 = "cd /home/zzhan173/syzkaller/GO12/gopath/src/github.com/google/syzkaller; make"
    if i386:
        string1 += " TARGETVMARCH=amd64 TARGETARCH=386"
    command(string1)

def copy_go12_syzkaller(targetdir, i386=None):
    string1 = "cp /home/zzhan173/syzkaller/GO12/gopath/src/github.com/google/syzkaller/bin/linux_amd64/* "+targetdir
    command(string1)
    if i386:
        string1 = "cp /home/zzhan173/syzkaller/GO12/gopath/src/github.com/google/syzkaller/bin/linux_386/* "+targetdir
        command(string1)

def get_go14_syzkaller(commit, i386=None):
    os.environ['GOPATH'] = "/home/zzhan173/syzkaller/GO14/gopath"
    os.environ['GOROOT'] = "/home/zzhan173/syzkaller/GO14/goroot"
    os.environ['PATH'] = os.environ['GOROOT'] + "/bin:" + os.environ['GOPATH'] + "/bin:" + os.environ['PATH']
    string1 = "cd /home/zzhan173/syzkaller/GO14/gopath/src/github.com/google/syzkaller; git checkout -f "+commit+";make"
    if i386:
        string1 += " TARGETVMARCH=amd64 TARGETARCH=386"
    command(string1)

def copy_go14_syzkaller(targetdir, i386=None):
    string1 = "cp /home/zzhan173/syzkaller/GO14/gopath/src/github.com/google/syzkaller/bin/linux_amd64/* "+targetdir
    command(string1)
    if i386:
        string1 = "cp /home/zzhan173/syzkaller/GO14/gopath/src/github.com/google/syzkaller/bin/linux_386/* "+targetdir
        command(string1)

def get_go16_syzkaller(commit, i386=None):
    os.environ['GOPATH'] = "/home/zzhan173/syzkaller/GO16/gopath"
    os.environ['GOROOT'] = "/home/zzhan173/syzkaller/GO16/go"
    os.environ['PATH'] = os.environ['GOROOT'] + "/bin:" + os.environ['GOPATH'] + "/bin:" + os.environ['PATH']
    #print("os.environ['PATH']:", os.environ['PATH'])
    string1 = "cd /home/zzhan173/syzkaller/GO16; cd syzkaller; git checkout -f "+commit+";make"
    if i386:
        string1 += " TARGETVMARCH=amd64 TARGETARCH=386"
    print(string1)
    command(string1)

def copy_go16_syzkaller(targetdir, i386=None):
    string1 = "cp /home/zzhan173/syzkaller/GO16/syzkaller/bin/linux_amd64/* "+targetdir
    command(string1)
    if i386:
        string1 = "cp /home/zzhan173/syzkaller/GO16/syzkaller/bin/linux_386/* "+targetdir
        command(string1)

def get_goversion(commit):
    string1 = "cd /home/zzhan173/repos/syzkaller;git checkout -f "+commit
    result = command(string1)
    if ("error" in result):
        print(result)
        return None
    with open("/home/zzhan173/repos/syzkaller/docs/linux/setup.md", "r") as f:
        s_buf = f.readlines()
    if any("Go 1.11+" in line for line in s_buf):
        return "go12"
    elif any("Go 1.13+" in line for line in s_buf):
        return "go14"
    elif any("Go 1.16+" in line for line in s_buf):
        return "go16"
    else:
        print("dont find suitable go version from setup.md for", commit)
        return None

def compile_syzkaller(targetdir, commit, i386=None):
    print("compile_syzkaller()", targetdir, commit, i386)
    targetdir += "/syzkaller/"
    print("compile_syzkaller() ",commit, "for", targetdir)
    if not os.path.exists(targetdir):
        os.mkdir(targetdir)
    goversion = get_goversion(commit)
    print("goversion:", goversion)
    if goversion == "go12":
        get_go12_syzkaller(commit, i386)
        copy_go12_syzkaller(targetdir, i386)
    elif goversion == "go14":
        get_go14_syzkaller(commit, i386)
        copy_go14_syzkaller(targetdir, i386)
    elif goversion == "go16":
        get_go16_syzkaller(commit, i386)
        copy_go16_syzkaller(targetdir, i386)
    else:
        "compile_syzkaller Fail"
        return False
    return True

if __name__ == "__main__":
    #targetdir = "/home/zzhan173/OOBW2022/c993ee0f9f81/91265a6da44d"
    #commit = "e2d91b1d0dd8c8b4760986ec8114469246022bb8"
    #targetdir = "/home/zzhan173/OOBW2020-2021/b2b2dd71e085/b1aa9d834830"
    #commit = "da505f84d3e8fc3bb7c54fea76eb5574987ee01a"
    targetdir = sys.argv[1]
    commit = sys.argv[2]
    i386 = None
    if len(sys.argv) > 3:
        i386 = True
        print("i386")
    compile_syzkaller(targetdir, commit, i386)
