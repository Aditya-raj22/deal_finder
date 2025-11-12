#!/bin/bash
# AWS Spot Instance Setup Script
#
# Usage:
#   1. Install AWS CLI: pip install awscli
#   2. Configure: aws configure
#   3. Run: bash aws_spot_setup.sh

set -e

# Configuration
INSTANCE_TYPE="t3.xlarge"  # 4 vCPU, 16GB RAM
AMI_ID="ami-0c55b159cbfafe1f0"  # Ubuntu 22.04 (update for your region)
KEY_NAME="deal-finder-key"  # Your EC2 key pair name
SECURITY_GROUP="deal-finder-sg"

echo "🚀 Setting up AWS Spot Instance..."

# 1. Create security group (if doesn't exist)
aws ec2 create-security-group \
    --group-name $SECURITY_GROUP \
    --description "Deal Finder Pipeline" 2>/dev/null || echo "Security group exists"

# 2. Allow SSH
aws ec2 authorize-security-group-ingress \
    --group-name $SECURITY_GROUP \
    --protocol tcp \
    --port 22 \
    --cidr 0.0.0.0/0 2>/dev/null || echo "SSH rule exists"

# 3. Create spot instance request
cat > spot-config.json <<EOF
{
  "ImageId": "$AMI_ID",
  "InstanceType": "$INSTANCE_TYPE",
  "KeyName": "$KEY_NAME",
  "SecurityGroups": ["$SECURITY_GROUP"],
  "UserData": "$(base64 -w 0 user-data.sh)",
  "BlockDeviceMappings": [
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {
        "VolumeSize": 50,
        "VolumeType": "gp3"
      }
    }
  ]
}
EOF

# 4. Request spot instance
REQUEST_ID=$(aws ec2 request-spot-instances \
    --spot-price "0.15" \
    --instance-count 1 \
    --type "one-time" \
    --launch-specification file://spot-config.json \
    --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
    --output text)

echo "✓ Spot instance requested: $REQUEST_ID"
echo "⏳ Waiting for instance to start..."

# 5. Wait for fulfillment
aws ec2 wait spot-instance-request-fulfilled --spot-instance-request-ids $REQUEST_ID

# 6. Get instance ID
INSTANCE_ID=$(aws ec2 describe-spot-instance-requests \
    --spot-instance-request-ids $REQUEST_ID \
    --query 'SpotInstanceRequests[0].InstanceId' \
    --output text)

echo "✓ Instance started: $INSTANCE_ID"

# 7. Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "✅ Setup complete!"
echo "Public IP: $PUBLIC_IP"
echo ""
echo "To connect:"
echo "  ssh -i ~/.ssh/$KEY_NAME.pem ubuntu@$PUBLIC_IP"
echo ""
echo "To copy code:"
echo "  scp -r -i ~/.ssh/$KEY_NAME.pem . ubuntu@$PUBLIC_IP:~/deal_finder"
echo ""
echo "To run pipeline:"
echo "  ssh -i ~/.ssh/$KEY_NAME.pem ubuntu@$PUBLIC_IP"
echo "  cd deal_finder && python step2_run_pipeline.py"

# Cleanup
rm spot-config.json
