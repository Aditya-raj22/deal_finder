#!/bin/bash
# Check disk space and identify large files/directories

echo "======================================"
echo "DISK SPACE ANALYSIS"
echo "======================================"
echo ""

echo "Current disk usage:"
df -h

echo ""
echo "======================================"
echo "Largest directories in home:"
du -h ~ --max-depth=2 2>/dev/null | sort -hr | head -20

echo ""
echo "======================================"
echo "Largest files in project:"
find ~/deal_finder -type f -size +100M 2>/dev/null -exec ls -lh {} \; | awk '{print $5, $9}'

echo ""
echo "======================================"
echo "Log files:"
du -h ~/deal_finder/logs 2>/dev/null || echo "No logs directory"

echo ""
echo "======================================"
echo "Cache sizes:"
du -sh ~/deal_finder/output/*.db 2>/dev/null || echo "No DB files"
du -sh ~/deal_finder/output/chroma_db 2>/dev/null || echo "No chroma_db"

echo ""
echo "======================================"
echo "Python cache:"
du -sh ~/.cache/huggingface 2>/dev/null || echo "No HuggingFace cache"

echo ""
echo "======================================"
echo "Docker (if any):"
docker system df 2>/dev/null || echo "Docker not running or not installed"
