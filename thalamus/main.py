#!/usr/bin/env python3

import click
import jwt
import os
import re
import requests
import socket
import sys
import time

from thalamus.sudo import Sudo
from thalamus.kubernetes import Kubernetes
from thalamus.values import Values
from thalamus.nginx import make_nginx_config
from thalamus.utils import runcmd

click.clear()
sudo = Sudo()

click.echo(click.style("--- WARNING ---", fg="red", bold=True))
click.echo("This script is meant to run on a fresh Linux machine. It will install software and delete files.")
click.echo("Don't run this on a machine that you care about!")
user_accepts_the_risk = click.prompt(click.style("To continue, type 'I do not care about this machine'", fg="red"), type=str)
if user_accepts_the_risk != "I do not care about this machine":
    click.echo("You might care about this machine. Exiting.")
    sys.exit(1)

click.echo("Getting external IP address... ", nl=False)
try:
    external_ip = requests.get("https://api.ipify.org").text
    if not external_ip:
        raise Exception("Failed to get external IP address")
except:
    click.echo(click.style("Error: ", fg="red", bold=True) + "Failed to get external IP address. Do you have an internet connection?")
    click.get_current_context().exit(1)
click.echo(click.style(external_ip, fg="green"))

def validate_hostname(ctx, param, value):
    if not ctx.obj:
        ctx.obj = {}
    if not ctx.obj.get(param.name):
        ctx.obj[param.name] = {}

    if not value:
        raise click.BadParameter(f"{param.name} cannot be empty")

    label_regex = re.compile(r'^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$')
    
    # Split the name by dot to check each label
    labels = value.split('.')
    
    # Check if each label is valid
    for label in labels:
        if not label_regex.match(label):
            raise click.BadParameter(f"Invalid hostname for {param.name}")
    
    # Ensure overall length is valid for FQDNs
    if len(value) > 253:
        raise click.BadParameter(f"Invalid hostname for {param.name}")

    try:
        lookup = socket.gethostbyname(value)
    except:
        lookup = None
    
    if not lookup:
        ctx.obj['no_lookup'] = True
        if not ctx.obj[param.name].get('confirmed_dns_warning', False):  # Check if we've already confirmed
            if click.confirm(f"Hostname {value} doesn't resolve to an IP. You'll need to add it to DNS or /etc/hosts later. Continue?", default=False):
                ctx.obj[param.name]['confirmed_dns_warning'] = True
                return value
            else:
                raise click.Abort()

    # If lookup succeeds but doesn't match external IP, ask for confirmation to continue
    if lookup and lookup != external_ip:
        ctx.obj['no_lookup'] = True
        if not ctx.obj[param.name].get('confirmed_ip_mismatch', False):  # Check if we've already confirmed
            if click.confirm(f"Hostname {value} resolves to {lookup}, not {external_ip}. You'll need to update DNS or /etc/hosts later. Continue?", default=False):
                ctx.obj[param.name]['confirmed_ip_mismatch'] = True  # Set flag to skip future confirmation
                return value
            else:
                raise click.Abort()
    return value

def validate_github_pat(ctx, param, value):
    url = "https://api.github.com/orgs/cortexapps/packages/docker/cortex-onprem-backend"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {value}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200 or response.json().get("package_type") != "container":
            raise click.BadParameter("Invalid GitHub PAT")
    except:
        raise click.BadParameter("Invalid GitHub PAT")
    return value

def validate_license(ctx, param, value):
    try:
        headers = jwt.get_unverified_header(value)
        if headers.get("typ") != "JWT":
            raise click.BadParameter("Invalid license key")
        payload = jwt.decode(value, options={"verify_signature": False})
        if not payload.get("entitlements"):
            raise click.BadParameter("Invalid license key")
    except:
        raise click.BadParameter("Invalid license key")
    return value

@click.command()
@click.option("--frontend", help="Hostname for the web UI", prompt="Frontend hostname", envvar="CORTEX_FRONTEND_HOSTNAME", callback=validate_hostname)
@click.option("--backend", help="Hostname for the backend API", prompt="Backend hostname", envvar="CORTEX_BACKEND_HOSTNAME", callback=validate_hostname)
@click.option("--cortex-license", help="Cortex license", prompt="Cortex license", envvar="ENTITLEMENTS_JWT", callback=validate_license)
@click.option("--github-pat", help="GitHub Personal Access Token", prompt="GitHub PAT", envvar="CORTEX_GITHUB_PAT", callback=validate_github_pat)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def main(ctx, frontend, backend, cortex_license, github_pat, dry_run):
    if frontend == backend:
        click.echo(click.style("Error: ", fg="red", bold=True) + "Frontend and backend hostnames cannot be the same")
        click.get_current_context().exit(1)

    if dry_run:
        click.echo(click.style("Dry run: ", fg="yellow", bold=True) + "No changes will be made")
        click.get_current_context().exit(0)

    hostname_values_update = {
        "app": {
            "hostnames": {
                "backend": backend,
                "frontend": frontend,
            }
        }
    }

    values = Values()
    kubernetes = Kubernetes(sudo)

    click.echo(click.style("Starting installation...", fg="green", bold=True))
    try:
        kubernetes.install_k0s()
        sudo.execute_steps([
            {
                "command": lambda: kubernetes.install_kubectl(),
                "description": "Install kubectl"
            },
            {
                "command": lambda: kubernetes.configure_kubectl(),
                "description": "Configure kubectl"
            }
        ])
        click.echo("Wait for kubectl to be ready... ", nl=False)
        time.sleep(5)
        kubectl_ready = False
        tries = 0
        while not kubectl_ready and tries < 5:
            try:
                kubernetes.check_kubectl_config()
                kubectl_ready = True
            except Exception as e:
                click.echo(".", nl=False)
                tries += 1
                time.sleep(5)
        if not kubectl_ready:
            raise Exception("kubectl never became ready")
        click.echo(click.style("done", fg="green"))
        sudo.execute_steps([
            {
                "command": f"kubectl --kubeconfig {kubernetes.kube_config_path} create secret generic cortex-secret --from-literal ENTITLEMENTS_JWT='{cortex_license}'",
                "description": "Add Cortex license"
            },
            {
                "command": f"kubectl --kubeconfig {kubernetes.kube_config_path} create secret docker-registry cortex-docker-registry-secret --docker-server=ghcr.io --docker-username=martindstone --docker-password={github_pat} --docker-email=martindstone@me.com",
                "description": "Add GitHub token"
            },
            {
                "command": lambda: kubernetes.install_helm(),
                "description": "Install Helm"
            },
            {
                "command": f"helm --kubeconfig {kubernetes.kube_config_path} repo add cortex https://helm-charts.cortex.io",
                "description": "Add Cortex Helm repository"
            },
            {
                "command": f"helm --kubeconfig {kubernetes.kube_config_path} pull cortex/cortex",
                "description": "Download Cortex Helm chart"
            },
            {
                "command": "tar -xvf cortex-*.tgz",
                "description": "Extract Cortex Helm chart"
            },
            {
                "command": lambda: values.edit_values_yaml(
                    os.path.join(sudo.home_dir, "cortex", "values.yaml"), values.get_values_template("demo"), hostname_values_update
                ),
                "description": "Edit values.yaml"
            },
            {
                "command": f"helm --kubeconfig {kubernetes.kube_config_path} install cortex ./cortex",
                "description": "Install Cortex"
            },
            {
                "command": lambda: time.sleep(5),
                "description": "Wait for services to be created"
            }
        ])
        click.echo("Get frontend IP address... ", nl=False)
        frontend_ip = runcmd(f"kubectl --kubeconfig {kubernetes.kube_config_path} get svc cortex-frontend-service -o jsonpath='{{.spec.clusterIP}}'")
        click.echo(click.style(frontend_ip, fg="green"))
        click.echo("Get backend IP address... ", nl=False)
        backend_ip = runcmd(f"kubectl --kubeconfig {kubernetes.kube_config_path} get svc cortex-backend-service -o jsonpath='{{.spec.clusterIP}}'")
        click.echo(click.style(backend_ip, fg="green"))
        sudo.execute_steps([
            {
                "command": "apt install -y nginx",
                "description": "Install nginx"
            },
            {
                "command": lambda: make_nginx_config("/etc/nginx/sites-available/default", frontend, frontend_ip, backend, backend_ip),
                "description": "Create nginx config"
            },
            {
                "command": "systemctl restart nginx",
                "description": "Restart nginx"
            }
        ])
        click.echo(click.style("Installation complete! ", fg="green", bold=True))
        if isinstance(ctx, click.Context) and isinstance(ctx.obj, dict) and ctx.obj.get("no_lookup"):
            click.echo(
                click.style(
                    f"Don't forget to set up name lookup for hosts {frontend} and {backend} to {external_ip} in your DNS server or /etc/hosts file.", bold=True
                )
            )
        click.echo("Waiting for services to be available (this could take a few minutes)...", nl=False)
        while not kubernetes.check_all_deployments_ready():
            time.sleep(5)
            click.echo(".", nl=False)
        click.echo(click.style(" done", fg="green"))
        click.echo(click.style("🎉 Cortex is ready! 🎉", bold=True))
    except Exception as e:
        click.echo(click.style("Installation halted: ", fg="red", bold=True) + str(e))
