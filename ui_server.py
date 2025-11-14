"""
Deal Finder UI Server - FastAPI backend with WebSocket for real-time updates

Run: uvicorn ui_server:app --reload --port 8000
Then open: http://localhost:8000
"""

import asyncio
import json
import os
import subprocess
import gzip
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Deal Finder UI")

# State management
active_pipeline: Optional[subprocess.Popen] = None
pipeline_config: Dict[str, Any] = {}


class PipelineConfig(BaseModel):
    api_key: Optional[str] = None
    therapeutic_area: str
    sources: list[str] = ["FierceBiotech", "BioPharma Dive", "Endpoints", "BioSpace", "STAT", "BioCentury", "GEN"]
    stages: list[str] = ["preclinical", "phase 1", "first-in-human"]
    start_date: str = "2021-01-01"
    end_date: Optional[str] = None


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def read_checkpoint(filename: str) -> Optional[dict]:
    """Read checkpoint file (supports .json and .json.gz)."""
    checkpoint_path = Path("output") / filename

    if not checkpoint_path.exists():
        return None

    try:
        if filename.endswith('.gz'):
            with gzip.open(checkpoint_path, 'rt', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(checkpoint_path) as f:
                return json.load(f)
    except Exception as e:
        print(f"Error reading checkpoint {filename}: {e}")
        return None


def get_pipeline_status() -> dict:
    """Get current pipeline status by checking checkpoints."""
    status = {
        "step": "idle",
        "step_number": 0,
        "total_steps": 6,
        "progress": 0,
        "stats": {},
        "checkpoints": {},
        "is_running": active_pipeline is not None and active_pipeline.poll() is None
    }

    # If no pipeline is running and no active config, show idle
    if not status["is_running"] and not pipeline_config:
        return status

    # Check each checkpoint
    checkpoints = {
        "fetch": "fetch_checkpoint.json.gz",
        "quick_filter": "quick_filter_checkpoint.json",
        "dedup": "dedup_checkpoint.json",
        "extraction": "extraction_checkpoint.json.gz",
        "parsing": "parsing_checkpoint.json.gz"
    }

    for name, filename in checkpoints.items():
        data = read_checkpoint(filename)
        if data:
            status["checkpoints"][name] = data

    # Determine current step
    if status["checkpoints"].get("parsing"):
        status["step"] = "completed"
        status["step_number"] = 6
        status["progress"] = 100

        # Get final stats
        parsing = status["checkpoints"]["parsing"]
        status["stats"] = {
            "deals_extracted": len(parsing.get("extracted_deals", [])),
            "rejected": len(parsing.get("extraction_rejected", []))
        }

    elif status["checkpoints"].get("extraction"):
        status["step"] = "parsing"
        status["step_number"] = 4
        status["progress"] = 70

        extraction = status["checkpoints"]["extraction"]
        status["stats"] = {
            "extractions": len(extraction.get("extractions", [])),
            "articles": len(extraction.get("articles", []))
        }

    elif status["checkpoints"].get("dedup"):
        status["step"] = "extraction"
        status["step_number"] = 3
        status["progress"] = 50

        dedup = status["checkpoints"]["dedup"]
        status["stats"] = {
            "articles_after_dedup": dedup.get("post_dedup_count", 0),
            "duplicates_removed": dedup.get("pre_dedup_count", 0) - dedup.get("post_dedup_count", 0)
        }

    elif status["checkpoints"].get("quick_filter"):
        status["step"] = "deduplication"
        status["step_number"] = 3
        status["progress"] = 40

        qf = status["checkpoints"]["quick_filter"]
        status["stats"] = {
            "passed_quick_filter": qf.get("passed_count", 0),
            "total_articles": qf.get("total_input", 0)
        }

    elif status["checkpoints"].get("fetch"):
        status["step"] = "filtering"
        status["step_number"] = 2
        status["progress"] = 30

        fetch = status["checkpoints"]["fetch"]
        status["stats"] = {
            "articles_fetched": len(fetch.get("articles", [])),
            "urls_fetched": len(fetch.get("fetched_urls", []))
        }

    # Override to show starting if pipeline just started but no checkpoints yet
    if status["is_running"] and status["progress"] == 0:
        status["step"] = "starting"
        status["step_number"] = 1
        status["progress"] = 5
        status["stats"] = {"status": "Initializing pipeline..."}

    return status


@app.get("/")
async def root():
    """Serve the main UI."""
    return FileResponse("static/index.html")


@app.get("/api/status")
async def status():
    """Get current pipeline status."""
    return get_pipeline_status()


@app.get("/api/ta-vocabs")
async def list_ta_vocabs():
    """List available therapeutic area vocabularies."""
    from pathlib import Path

    ta_vocab_dir = Path("config/ta_vocab")
    if not ta_vocab_dir.exists():
        return {"vocabs": []}

    vocabs = []
    for vocab_file in ta_vocab_dir.glob("*.json"):
        # Convert filename back to display format
        ta_name = vocab_file.stem.replace("_", "/")
        vocabs.append({
            "name": ta_name,
            "file": vocab_file.name
        })

    return {"vocabs": sorted(vocabs, key=lambda x: x["name"])}


@app.post("/api/pipeline/start")
async def start_pipeline(config: PipelineConfig):
    """Start the pipeline with given config."""
    global active_pipeline, pipeline_config

    if active_pipeline and active_pipeline.poll() is None:
        return JSONResponse(
            {"error": "Pipeline already running"},
            status_code=400
        )

    # Validate API key
    api_key = config.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JSONResponse(
            {"error": "OpenAI API key required. Set OPENAI_API_KEY env var or provide in UI."},
            status_code=400
        )

    # Validate TA vocab exists
    import yaml
    from pathlib import Path

    ta_normalized = config.therapeutic_area.replace("/", "_").replace(" ", "_")
    ta_vocab_path = Path(f"config/ta_vocab/{ta_normalized}.json")

    if not ta_vocab_path.exists():
        return JSONResponse(
            {"error": f"TA vocab file not found: {ta_vocab_path}. Available files: {', '.join([f.stem for f in Path('config/ta_vocab').glob('*.json')])}"},
            status_code=400
        )

    pipeline_config = config.dict()

    # Load base config
    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        base_config = yaml.safe_load(f)

    # Override with UI settings
    base_config["THERAPEUTIC_AREA"] = ta_normalized
    base_config["EARLY_STAGE_ALLOWED"] = config.stages
    base_config["START_DATE"] = config.start_date
    if config.end_date:
        base_config["END_DATE"] = config.end_date

    # Note: Sources filtering would need to be implemented in the crawler
    # For now, this is just logged in the config

    # Write temporary config
    temp_config_path = Path("output/ui_config.yaml")
    temp_config_path.parent.mkdir(exist_ok=True)
    with open(temp_config_path, 'w') as f:
        yaml.dump(base_config, f)

    # Set environment with API key
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key

    # Build command - use temp config
    cmd = [
        "python", "step2_run_pipeline.py",
        "--config", str(temp_config_path)
    ]

    # Start pipeline
    try:
        active_pipeline = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1
        )

        # Broadcast start message
        await manager.broadcast({
            "type": "pipeline_started",
            "config": pipeline_config
        })

        return {"status": "started", "pid": active_pipeline.pid, "config_used": pipeline_config}

    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


@app.post("/api/pipeline/stop")
async def stop_pipeline():
    """Stop the running pipeline."""
    global active_pipeline

    if not active_pipeline or active_pipeline.poll() is not None:
        return JSONResponse(
            {"error": "No pipeline running"},
            status_code=400
        )

    active_pipeline.terminate()
    active_pipeline.wait(timeout=5)
    active_pipeline = None

    await manager.broadcast({
        "type": "pipeline_stopped"
    })

    return {"status": "stopped"}


@app.get("/api/outputs")
async def list_outputs():
    """List all output files."""
    output_dir = Path("output")
    if not output_dir.exists():
        return {"files": []}

    files = []
    for f in output_dir.glob("hybrid_deals_*.xlsx"):
        stat = f.stat()
        files.append({
            "name": f.name,
            "path": str(f),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files}


@app.get("/api/outputs/{filename}")
async def download_output(filename: str):
    """Download an output file."""
    file_path = Path("output") / filename
    if not file_path.exists():
        return JSONResponse(
            {"error": "File not found"},
            status_code=404
        )

    return FileResponse(
        file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.delete("/api/checkpoints")
async def clear_checkpoints():
    """Clear all checkpoints to start fresh."""
    output_dir = Path("output")
    if not output_dir.exists():
        return {"cleared": 0}

    count = 0
    patterns = ["*_checkpoint.json*", "quick_filter_checkpoint.json", "dedup_checkpoint.json"]

    for pattern in patterns:
        for f in output_dir.glob(pattern):
            f.unlink()
            count += 1

    return {"cleared": count}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)

    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "data": get_pipeline_status()
        })

        # Keep connection alive and send updates
        while True:
            await asyncio.sleep(2)  # Update every 2 seconds

            status = get_pipeline_status()
            await websocket.send_json({
                "type": "status",
                "data": status
            })

            # If pipeline is running, send log updates
            if active_pipeline and active_pipeline.poll() is None:
                # Read any available output (non-blocking, cross-platform)
                try:
                    import sys
                    # Use select on Unix, simple non-blocking read attempt on Windows
                    if sys.platform != 'win32':
                        import select
                        if active_pipeline.stdout and select.select([active_pipeline.stdout], [], [], 0)[0]:
                            line = active_pipeline.stdout.readline()
                            if line:
                                await websocket.send_json({
                                    "type": "log",
                                    "text": line.strip(),
                                    "level": "info"
                                })
                    else:
                        # Windows: Try to read without blocking (may miss some logs)
                        # In production, use threading or asyncio subprocess for Windows
                        pass
                except Exception:
                    pass  # Ignore read errors
            elif active_pipeline and active_pipeline.poll() is not None:
                # Pipeline finished
                exit_code = active_pipeline.poll()
                await websocket.send_json({
                    "type": "pipeline_completed",
                    "exit_code": exit_code
                })
                # Clear the active pipeline ref
                active_pipeline = None

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
