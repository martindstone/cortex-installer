import json
import io
import os
import platform
import requests
import shutil
import subprocess
import tarfile
import time

class Kubernetes:
    def __init__(self, sudo):
        self.os_type = platform.system().lower()
        arch = platform.machine()
        if arch in ["x86_64", "AMD64"]:
            self.arch = "amd64"
        elif arch in ["arm64", "aarch64"]:
            self.arch = "arm64"

        self.sudo = sudo
        self.kube_home = os.path.join(self.sudo.get_home_dir(), ".kube")
        self.kube_config_path = os.path.join(self.kube_home, "config")

    install_k0s_steps = [
        {
            "command": "curl -sSLf https://get.k0s.sh/ -o k0s-install.sh",
            "description": "Download k0s"
        },
        {
            "command": "chmod +x k0s-install.sh",
            "description": "Make k0s-install.sh executable"
        },
        {
            "command": "./k0s-install.sh",
            "description": "Run k0s-install.sh"
        },
        {
            "command": "k0s install controller --single",
            "description": "Install k0s"
        },
        {
            "command": "k0s start",
            "description": "Start k0s"
        }
    ]

    def install_kubectl(self):
        response = requests.get("https://dl.k8s.io/release/stable.txt")
        version = response.text.strip()
        url = f"https://dl.k8s.io/release/{version}/bin/{self.os_type}/{self.arch}/kubectl"
        response = requests.get(url)
        os.makedirs("/usr/local/bin", exist_ok=True, mode=0o755)
        with open("/usr/local/bin/kubectl", "wb") as f:
            f.write(response.content)
        os.chmod("/usr/local/bin/kubectl", 0o755)

    def configure_kubectl(self):
        admin_conf_path = "/var/lib/k0s/pki/admin.conf"

        # sometimes the admin.conf file is not immediately available
        tries = 0
        while not os.path.exists(admin_conf_path) and tries < 5:
            time.sleep(2)
            if not os.path.exists(admin_conf_path):
                raise FileNotFoundError("k0s admin.conf not found")
        if not os.path.exists(admin_conf_path):
            raise FileNotFoundError("k0s admin.conf not found")

        os.makedirs(self.kube_home, exist_ok=True)
        shutil.copy(admin_conf_path, self.kube_config_path)
        self.sudo.chown_to_original(self.kube_home)
        os.chmod(self.kube_config_path, 0o600)

    def check_kubectl_config(self):
        cmd = f"kubectl --kubeconfig={self.kube_config_path} get nodes"
        try:
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            raise Exception("kubectl config is not valid: " + e.output.decode("utf-8"))

    def install_helm(self):
        # get latest helm release
        response = requests.get("https://api.github.com/repos/helm/helm/releases/latest")
        version = response.json()["tag_name"]
        
        # download and open the helm tarball
        url = f"https://get.helm.sh/helm-{version}-{self.os_type}-{self.arch}.tar.gz"
        response = requests.get(url)
        file_like_object = io.BytesIO(response.content)
        contents = tarfile.open(fileobj=file_like_object, mode="r:gz")

        # find the helm binary in the tarball
        members = [m for m in contents.getmembers() if os.path.basename(m.name) == "helm"]
        if not members:
            raise FileNotFoundError("helm binary not found in tarball")
        extracted = contents.extractfile(members[0])
        os.makedirs("/usr/local/bin", exist_ok=True, mode=0o755)
        
        # write helm binary to /usr/local/bin
        with open("/usr/local/bin/helm", "wb") as f:
            f.write(extracted.read())
        os.chmod("/usr/local/bin/helm", 0o755)

    # def add_secrets(self, github_token, license):
    #     self.sudo.execute_steps([
    #         {
    #             "command": f"kubectl --kubeconfig {self.kube_config_path} create secret generic cortex-secret --from-literal ENTITLEMENTS_JWT='{license}'",
    #             "description": "Add Cortex license"
    #         },
    #         {
    #             "command": f"kubectl --kubeconfig {self.kube_config_path} create secret docker-registry cortex-docker-registry-secret --docker-server=ghcr.io --docker-username=martindstone --docker-password={github_token} --docker-email=martindstone@me.com",
    #             "description": "Add GitHub token"
    #         }
    #     ])

    def check_all_deployments_ready(self):
        cmd = f"kubectl --kubeconfig={self.kube_config_path} get deployments -o json"
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")
        ds = json.loads(output)
        for deployment in ds["items"]:
            if deployment.get("status", {}).get("readyReplicas", 0) != deployment.get("status", {}).get("replicas", -1):
                return False
        return True

    def install_k0s(self):
        self.sudo.execute_steps(self.install_k0s_steps)
