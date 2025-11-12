#!/bin/bash
# EC2 User Data Script - Runs on instance startup

set -e

# Update system
apt-get update
apt-get upgrade -y

# Install Python 3.10
apt-get install -y python3.10 python3.10-venv python3-pip

# Install Chrome/Chromedriver for Selenium
apt-get install -y wget unzip
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list
apt-get update
apt-get install -y google-chrome-stable chromium-chromedriver

# Set up working directory
mkdir -p /home/ubuntu/deal_finder
chown ubuntu:ubuntu /home/ubuntu/deal_finder

# Install Python dependencies
cat > /home/ubuntu/requirements.txt <<EOF
selenium
beautifulsoup4
lxml
openai
python-dotenv
openpyxl
pandas
pydantic
sentence-transformers
scikit-learn
torch
EOF

pip3 install -r /home/ubuntu/requirements.txt

echo "✅ Setup complete! Ready to run pipeline."
