import click
import os
import sys
import pwd
import subprocess

class Sudo:
    def __init__(self, **kwargs):
        sudo = kwargs.get("sudo", True)
        if isinstance(sudo, bool):
            if sudo:
                if os.geteuid() != 0 or os.environ.get("SUDO_UID") is None:
                    print("Re-running with sudo... You may be prompted for your local user password.")
                    os.execvp('sudo', ['sudo', 'python3'] + sys.argv)

                self.original_uid = int(os.environ.get("SUDO_UID"))
                self.original_gid = int(os.environ.get("SUDO_GID"))
                self.home_dir = pwd.getpwuid(self.original_uid).pw_dir
                self.original_cwd = os.getcwd()
        else:
            raise TypeError("kwarg sudo must be a boolean")

    def get_original_uid(self) -> int:
        return self.original_uid

    def get_original_gid(self) -> int:
        return self.original_gid

    def get_home_dir(self) -> str:
        return self.home_dir

    def get_original_cwd(self) -> str:
        return self.original_cwd

    def chown_to_original(self, path):
        # recursively chown if it's a directory
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for d in dirs:
                    os.chown(os.path.join(root, d), self.original_uid, self.original_gid)
                for f in files:
                    os.chown(os.path.join(root, f), self.original_uid, self.original_gid)
        os.chown(path, self.original_uid, self.original_gid)

    def execute_step(self, step):
        click.echo(step["description"] + "... ", nl=False)
        result = None
        try:
            if isinstance(step["command"], str):
                result = subprocess.check_output(step["command"], shell=True, stderr=subprocess.STDOUT)
            elif callable(step["command"]):
                result = step["command"]()
        except Exception as e:
            click.echo(click.style("Error: ", fg="red", bold=True) + str(e))
            raise
        click.echo(click.style("done", fg="green"))
        return result

    def execute_steps(self, steps):
        results = []
        for step in steps:
            results.append(self.execute_step(step))
        return results
