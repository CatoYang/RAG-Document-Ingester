import os
import json
import asyncio
from pathlib import Path
from rich.console import Console

console = Console()

class BatchManager:
    """Manages the creation, polling, and downloading of Async Batch Jobs across providers."""

    # Normalizes each provider's own status vocabulary (Gemini's
    # `JobState.JOB_STATE_*` enum, OpenAI's `batch.status` strings, Anthropic's
    # `processing_status` strings) down to one of "pending"/"running"/
    # "succeeded"/"failed", so callers (src/vision/orchestrator.py) don't need
    # provider-specific branches.
    _GEMINI_STATE_MAP = {
        "JOB_STATE_QUEUED": "pending",
        "JOB_STATE_PENDING": "pending",
        "JOB_STATE_PAUSED": "pending",
        "JOB_STATE_RUNNING": "running",
        "JOB_STATE_UPDATING": "running",
        "JOB_STATE_SUCCEEDED": "succeeded",
        "JOB_STATE_PARTIALLY_SUCCEEDED": "succeeded",
        "JOB_STATE_FAILED": "failed",
        "JOB_STATE_CANCELLED": "failed",
        "JOB_STATE_CANCELLING": "failed",
        "JOB_STATE_EXPIRED": "failed",
    }
    _OPENAI_STATUS_MAP = {
        "validating": "pending",
        "in_progress": "running",
        "finalizing": "running",
        "completed": "succeeded",
        "failed": "failed",
        "expired": "failed",
        "cancelling": "failed",
        "cancelled": "failed",
    }
    _ANTHROPIC_STATUS_MAP = {
        "in_progress": "running",
        "canceling": "running",
        "ended": "succeeded",
    }

    def __init__(self, provider: str = "gemini"):
        self.provider = provider.lower()

    def submit_job(self, jsonl_path: str, model: str = "gemini-2.0-flash-001") -> str:
        """Uploads the JSONL and submits the batch job. Returns the Job ID."""
        path = Path(jsonl_path)
        if not path.exists():
            raise FileNotFoundError(f"JSONL file not found at {jsonl_path}")

        console.print(f"[cyan]Submitting Batch Job to {self.provider.upper()}...[/cyan]")

        if self.provider == "gemini":
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set.")
            client = genai.Client(api_key=api_key)

            # 1. Upload the file
            console.print("  [dim]- Uploading file to Gemini...[/dim]")
            file_obj = client.files.upload(file=str(path), config={'mime_type': 'application/jsonl'})

            # 2. Create the batch job
            console.print("  [dim]- Creating batch job...[/dim]")
            # `model=` is required by google-genai's Batches.create - omitting
            # it (the original bug here) raises a TypeError before any
            # request is even sent.
            job = client.batches.create(
                model=model,
                src=file_obj.name
            )
            job_id = job.name
            console.print(f"[bold green]Gemini Batch Job Created: {job_id}[/bold green]")
            return job_id
            
        elif self.provider == "openai":
            import openai
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set.")
            client = openai.OpenAI(api_key=api_key)
            
            console.print("  [dim]- Uploading file to OpenAI...[/dim]")
            with open(path, "rb") as f:
                file_obj = client.files.create(file=f, purpose="batch")
                
            console.print("  [dim]- Creating batch job...[/dim]")
            job = client.batches.create(
                input_file_id=file_obj.id,
                endpoint="/v1/chat/completions",
                completion_window="24h"
            )
            job_id = job.id
            console.print(f"[bold green]OpenAI Batch Job Created: {job_id}[/bold green]")
            return job_id
            
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
            client = Anthropic(api_key=api_key)
            
            console.print("  [dim]- Creating Message Batch job in Anthropic...[/dim]")
            with open(path, "rb") as f:
                message_batch = client.beta.messages.batches.create(
                    requests=[json.loads(line) for line in f]
                )
            job_id = message_batch.id
            console.print(f"[bold green]Anthropic Batch Job Created: {job_id}[/bold green]")
            return job_id
            
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def check_status(self, job_id: str) -> str:
        """Checks the status of the batch job, normalized to one of
        "pending"/"running"/"succeeded"/"failed"/"unknown"."""
        if self.provider == "gemini":
            from google import genai
            client = genai.Client()
            job = client.batches.get(name=job_id)
            # job.state is a google.genai.types.JobState enum member, not a
            # plain string - comparing it directly against lowercase string
            # literals (the original bug) never matches. `.name` gives the
            # "JOB_STATE_*" string the map below keys off.
            state_name = getattr(job.state, "name", str(job.state))
            return self._GEMINI_STATE_MAP.get(state_name, "unknown")

        elif self.provider == "openai":
            import openai
            client = openai.OpenAI()
            job = client.batches.retrieve(job_id)
            return self._OPENAI_STATUS_MAP.get(job.status, "unknown")

        elif self.provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic()
            job = client.beta.messages.batches.retrieve(job_id)
            return self._ANTHROPIC_STATUS_MAP.get(job.processing_status, "unknown")

        return "unknown"

    def download_results(self, job_id: str, output_path: str):
        """Downloads the results JSONL file once the job is complete."""
        console.print(f"[cyan]Downloading results for {job_id}...[/cyan]")
        path = Path(output_path)
        
        if self.provider == "gemini":
            from google import genai
            client = genai.Client()
            job = client.batches.get(name=job_id)

            # BatchJob has no `output_uri` field (the original bug) - for a
            # file-based (non-GCS) batch submitted via the Gemini Developer
            # API, the result file name is `job.dest.file_name`, downloaded
            # through the Files API rather than a plain URL fetch.
            if not job.dest or not job.dest.file_name:
                raise ValueError(f"Job {job_id} does not have results available yet.")

            client.files.download(file=job.dest.file_name, destination=str(path))
            
        elif self.provider == "openai":
            import openai
            client = openai.OpenAI()
            job = client.batches.retrieve(job_id)
            
            if not job.output_file_id:
                raise ValueError(f"Job {job_id} does not have an output_file_id yet.")
                
            file_response = client.files.content(job.output_file_id)
            with open(path, "wb") as f:
                f.write(file_response.read())
                
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic()
            
            results = client.beta.messages.batches.results(job_id)
            with open(path, "w", encoding="utf-8") as f:
                for result in results:
                    f.write(json.dumps(result.model_dump()) + "\n")
                    
        console.print(f"[bold green]Results successfully saved to {path}[/bold green]")
