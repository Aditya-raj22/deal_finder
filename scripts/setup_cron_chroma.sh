#!/bin/bash
# Setup cron job for daily ChromaDB cache updates

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."

# Create daily update script
cat > "$SCRIPT_DIR/daily_chroma_update.sh" <<'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "========================================="
echo "Daily ChromaDB Cache Update (all-mpnet-base-v2)"
echo "Started: $(date)"
echo "========================================="

# Run ChromaDB cache builder (incremental)
python step1_build_cache_chroma.py --start-date 2021-01-01

echo "========================================="
echo "Cache update complete!"
echo "Finished: $(date)"
echo "========================================="
EOF

chmod +x "$SCRIPT_DIR/daily_chroma_update.sh"

# Add to crontab
CRON_JOB="0 2 * * * $SCRIPT_DIR/daily_chroma_update.sh >> $PROJECT_DIR/logs/chroma_update.log 2>&1"

if crontab -l 2>/dev/null | grep -q "daily_chroma_update.sh"; then
    echo "Cron job already exists!"
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✓ Cron job installed!"
    echo "  Schedule: Daily at 2:00 AM"
    echo "  Logs: $PROJECT_DIR/logs/chroma_update.log"
fi

echo ""
echo "Current crontab:"
crontab -l
