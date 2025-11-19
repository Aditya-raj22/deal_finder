#!/bin/bash
# Restart embedding process with faster settings on GCP VM

set -e

VM_NAME="instance-20251117-165359"
ZONE="us-central1-f"

echo "🔄 Restarting embedding with faster settings..."
echo ""

# Kill current slow process
echo "1️⃣ Killing current embedding process..."
gcloud compute ssh $VM_NAME --zone=$ZONE --command="
    pkill -f 'EmbeddingService' || true
    echo '✓ Stopped old process'
"

# Show current status
echo ""
echo "2️⃣ Current embedding status:"
gcloud compute ssh $VM_NAME --zone=$ZONE --command="
    cd deal_finder && python3 -c \"
from deal_finder.storage.content_cache import ContentCache
c = ContentCache('output/content_cache.db')
s = c.get_stats()
print(f'Total: {s[\"total_articles\"]:,}')
print(f'Pending: {s[\"by_status\"].get(\"pending\", 0):,}')
print(f'Embedded: {s[\"by_status\"].get(\"embedded\", 0):,}')
print(f'Failed: {s[\"by_status\"].get(\"failed\", 0):,}')
\"
"

echo ""
echo "3️⃣ Starting fast embedding (batch_size=500, faster model)..."
echo ""
echo "Choose embedding model:"
echo "  1) all-MiniLM-L6-v2 (FAST - 3x faster, good quality) ← RECOMMENDED"
echo "  2) all-mpnet-base-v2 (SLOW - better quality, slower)"
read -p "Enter choice [1]: " choice
choice=${choice:-1}

if [ "$choice" = "1" ]; then
    MODEL="all-MiniLM-L6-v2"
else
    MODEL="all-mpnet-base-v2"
fi

echo ""
echo "Starting with model: $MODEL"
echo ""

# Start new fast process in background with nohup
gcloud compute ssh $VM_NAME --zone=$ZONE --command="
    cd deal_finder && \
    nohup python3 scripts/embed_fast.py \
        --batch-size 500 \
        --embedding-model $MODEL \
        > logs/embed_fast.log 2>&1 &
    echo '✓ Started fast embedding process'
    echo ''
    echo 'To monitor progress:'
    echo '  gcloud compute ssh $VM_NAME --zone=$ZONE'
    echo '  tail -f deal_finder/logs/embed_fast.log'
"

echo ""
echo "✅ Done! Fast embedding is now running on VM."
echo ""
echo "Expected improvements:"
if [ "$MODEL" = "all-MiniLM-L6-v2" ]; then
    echo "  • Model: 3-4x faster"
fi
echo "  • Batch size: 1.5-2x faster"
echo "  • Total speedup: 5-8x faster 🚀"
echo ""
echo "New estimated time: ~1-2 days (down from 8.6 days)"
