"""
Run deal finder pipeline on Modal.

Setup:
    pip install modal
    modal token new
    modal run modal_pipeline.py

Cost: ~$0.30-1.00/hour, pay-per-second billing
"""

import modal

# Define container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("chromium", "chromium-driver")  # For Selenium
    .pip_install(
        "selenium",
        "beautifulsoup4",
        "lxml",
        "openai",
        "python-dotenv",
        "openpyxl",
        "pandas",
        "pydantic",
        "sentence-transformers",
        "scikit-learn",
        "torch",
    )
)

app = modal.App("deal-finder")

# Create persistent volume for checkpoints
volume = modal.Volume.from_name("deal-finder-checkpoints", create_if_missing=True)


@app.function(
    image=image,
    volumes={"/root/deal_finder/output": volume},
    secrets=[modal.Secret.from_name("openai-secret")],  # Set via Modal dashboard
    timeout=86400,  # 24 hour timeout
    cpu=4,  # 4 CPUs
    memory=16384,  # 16GB RAM for embeddings
)
def run_pipeline():
    """Run the deal finder pipeline."""
    import subprocess
    import sys

    # Run the pipeline
    result = subprocess.run(
        [sys.executable, "step2_run_pipeline.py", "--config", "config/config.yaml"],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Sync volume to persist checkpoints
    volume.commit()

    return result.returncode


@app.local_entrypoint()
def main():
    """Entry point when running locally."""
    exit_code = run_pipeline.remote()
    print(f"Pipeline finished with exit code: {exit_code}")


# To resume from checkpoint:
@app.function(
    image=image,
    volumes={"/root/deal_finder/output": volume},
    secrets=[modal.Secret.from_name("openai-secret")],
    timeout=86400,
    cpu=4,
    memory=16384,
)
def resume_pipeline():
    """Resume from last checkpoint."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "step2_run_pipeline.py",
            "--config", "config/config.yaml",
            "--skip-fetch",  # Resume from checkpoint
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    volume.commit()
    return result.returncode
