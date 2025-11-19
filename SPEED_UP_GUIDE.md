# Speed Up Embedding Guide

## Current Status
- **Speed**: 0.85 articles/sec (~3,044/hour)
- **Remaining**: 629,132 articles
- **ETA**: ~8.6 days 😱

## Quick Fixes (In Order of Impact)

### Option 1: Use Faster Model + Larger Batches ⚡ (5-8x faster)
**Easiest & Recommended**

```bash
./restart_embedding_fast.sh
```

This will:
- Kill current slow process
- Restart with `all-MiniLM-L6-v2` (3x faster model)
- Use batch_size=500 (instead of 100)
- **New ETA: ~1-2 days** instead of 8.6 days

**Quality impact**: Minimal - MiniLM is still very good for semantic search

---

### Option 2: Switch to GPU Instance 🚀 (20-50x faster)
**Most Expensive but Fastest**

Stop current VM and create GPU instance:

```bash
# Stop current VM
gcloud compute instances stop instance-20251117-165359 --zone=us-central1-f

# Create new GPU instance
gcloud compute instances create embedding-gpu \
    --zone=us-central1-a \
    --machine-type=n1-standard-8 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --image-family=pytorch-latest-gpu \
    --image-project=deeplearning-platform-release \
    --boot-disk-size=200GB \
    --maintenance-policy=TERMINATE

# Copy data
gcloud compute scp --recurse instance-20251117-165359:~/deal_finder/output embedding-gpu:~/deal_finder/ --zone=us-central1-f

# SSH and run with GPU
gcloud compute ssh embedding-gpu --zone=us-central1-a
cd deal_finder
pip install sentence-transformers chromadb
python3 scripts/embed_fast.py --batch-size 1000
```

**Cost**: ~$0.35/hour (T4 GPU) + ~$0.30/hour (n1-standard-8) = **~$0.65/hour**
**ETA**: ~6-12 hours total
**Total cost**: ~$4-8 for entire embedding job

---

### Option 3: Use Multiple VMs in Parallel 🔀 (10-15x faster)
**Complex but Effective**

Process different batches on different VMs:

1. Split pending articles into chunks
2. Spin up 4-8 VMs
3. Each processes their chunk
4. Merge results

**Cost**: 4-8x VM costs but finishes 4-8x faster
**Complexity**: High - requires custom splitting logic

---

## Recommendation

### If you want simple & fast:
```bash
./restart_embedding_fast.sh
```
Pick option 1 (MiniLM model). **5-8x speedup, done in 1-2 days.**

### If you want maximum speed and don't mind $5-10 cost:
Use **Option 2 (GPU)**. Done in 6-12 hours for ~$5-10 total.

---

## Model Comparison

| Model | Speed | Quality | Dimensions | Use Case |
|-------|-------|---------|------------|----------|
| all-MiniLM-L6-v2 | ⚡⚡⚡ Fast | ⭐⭐⭐ Good | 384 | **Recommended** - Fast, good quality |
| all-mpnet-base-v2 | 🐌 Slow | ⭐⭐⭐⭐ Better | 768 | Current (slow) - Slightly better quality |

For your use case (biotech deal finding), **MiniLM is plenty good** - the quality difference is marginal.

---

## Progress Monitoring

After restarting, monitor progress:

```bash
# SSH to VM
gcloud compute ssh instance-20251117-165359 --zone=us-central1-f

# Watch logs
tail -f deal_finder/logs/embed_fast.log

# Check status
cd deal_finder
python3 -c "
from deal_finder.storage.content_cache import ContentCache
c = ContentCache('output/content_cache.db')
s = c.get_stats()
print(f'Embedded: {s[\"by_status\"].get(\"embedded\", 0):,} / {s[\"total_articles\"]:,}')
print(f'Progress: {100*s[\"by_status\"].get(\"embedded\", 0)/s[\"total_articles\"]:.1f}%')
"
```

---

## Why So Slow?

The bottleneck is **embedding generation**:
- Sentence transformers use neural networks
- Your current model (mpnet) is large & slow
- Running on CPU only (no GPU)
- Small batch size (100)

ChromaDB itself is fast - the slowness is in computing embeddings for 700K articles.
