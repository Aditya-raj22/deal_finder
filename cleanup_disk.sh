#!/bin/bash
# Clean up disk space on cloud instance

echo "======================================"
echo "DISK CLEANUP"
echo "======================================"
echo ""

# Clean apt cache
echo "1. Cleaning apt cache..."
sudo apt-get clean
sudo apt-get autoclean
sudo apt-get autoremove -y

# Clean old log files
echo ""
echo "2. Cleaning old log files..."
find ~/deal_finder/logs -name "*.log" -mtime +7 -delete 2>/dev/null || echo "No old logs to delete"

# Clean Python cache
echo ""
echo "3. Cleaning Python cache..."
find ~/deal_finder -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || echo "No pycache to clean"
find ~/deal_finder -type f -name "*.pyc" -delete 2>/dev/null || echo "No .pyc files"

# Clean pip cache
echo ""
echo "4. Cleaning pip cache..."
pip cache purge 2>/dev/null || echo "No pip cache"

# Clean temporary files
echo ""
echo "5. Cleaning temporary files..."
rm -rf /tmp/* 2>/dev/null || echo "Cannot clean /tmp (permission denied - normal)"

# Show final disk space
echo ""
echo "======================================"
echo "DISK SPACE AFTER CLEANUP:"
df -h

echo ""
echo "Run 'check_disk_space.sh' if you need more space"
echo "Consider:"
echo "  - Deleting old model checkpoints in ~/.cache/huggingface"
echo "  - Compacting the SQLite database: VACUUM"
echo "  - Moving large files to cloud storage"
