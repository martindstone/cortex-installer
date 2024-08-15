#!/bin/bash

# If not running as root, re-execute the script with sudo and pass the heredoc content
if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs to be run as root. Attempting to use sudo..."
    sudo bash << 'EOF'
#!/bin/bash

# Detect the Linux distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Cannot detect the Linux distribution."
    exit 1
fi

# Install Python 3 and pip based on the detected distribution
case "$OS" in
    ubuntu|debian)
        echo -n "Detected $OS. Installing Python 3 and pip... "
        apt-get update > /dev/null 2>&1
        apt-get install -y python3 python3-pip > /dev/null 2>&1
        ;;
    fedora)
        echo -n "Detected Fedora. Installing Python 3 and pip... "
        dnf install -y python3 python3-pip > /dev/null 2>&1
        ;;
    centos|rhel)
        echo -n "Detected CentOS/RHEL. Installing Python 3 and pip... "
        yum install -y python3 python3-pip > /dev/null 2>&1
        ;;
    arch)
        echo -n "Detected Arch Linux. Installing Python 3 and pip... "
        pacman -Syu --noconfirm python python-pip > /dev/null 2>&1
        ;;
    opensuse)
        echo -n "Detected openSUSE. Installing Python 3 and pip... "
        zypper install -y python3 python3-pip > /dev/null 2>&1
        ;;
    alpine)
        echo -n "Detected Alpine Linux. Installing Python 3 and pip... "
        apk add --no-cache python3 py3-pip > /dev/null 2>&1
        ;;
    *)
        echo "Unsupported or unrecognized Linux distribution: $OS"
        exit 1
        ;;
esac

# Verify installation
python3 --version  > /dev/null 2>&1 && pip3 --version > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "\e[32mdone\e[0m"
else
    echo "Failed to install Python 3 or pip."
    exit 1
fi

echo -n "Installing Cortex installer... "
pip install https://martins-public-bucket.s3.us-east-2.amazonaws.com/thalamus-0.1.0-py3-none-any.whl --break-system-packages > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "\e[32mdone\e[0m"
else
    echo "Failed to install the Cortex installer."
    exit 1
fi
echo -e "All set. Run \e[1minstall-cortex\e[0m to install Cortex."
EOF
    exit
fi
