import subprocess

def runcmd(cmd):
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    return output.decode("utf-8").strip()
