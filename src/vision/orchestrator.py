import os
import re
import json
import base64
from pathlib import Path
from datetime import datetime
from rich.console import Console

from src.core.interfaces import Document
from src.vision.batch_manager import BatchManager

console = Console()

def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

async def process_ocr(document: Document, config) -> bool:
    """
    Scans the document for images and processes them based on config mode.
    Returns True if the document is SUSPENDED (waiting for async batch).
    Returns False if processing is complete (sync/local/passthrough) and pipeline can continue.
    """
    mode = config.pipeline.steps.ocr.mode
    provider = config.pipeline.steps.ocr.provider
    model = config.pipeline.steps.ocr.model
    
    if mode == "passthrough":
        return False
        
    batch_dir = Path(config.io.directories.batch_jobs)
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    # -------------------------------------------------------------
    # 1. IDEMPOTENT STATE CHECK
    # -------------------------------------------------------------
    if mode == "async_batch":
        # Check if there is an active jobstate for this document
        doc_stem = Path(document.source_file).stem
        existing_jobstates = list(batch_dir.glob(f"{doc_stem}_*.jobstate"))
        
        if existing_jobstates:
            jobstate_path = existing_jobstates[0] # Assume one active job per doc
            with open(jobstate_path, "r") as f:
                state = json.load(f)
                
            api_job_id = state.get("api_job_id")
            console.print(f"[cyan]Found existing pending batch job for {document.source_file} (Job ID: {api_job_id}). Polling status...[/cyan]")
            
            bm = BatchManager(provider)
            status = bm.check_status(api_job_id)
            
            if status in ["pending", "running", "processing"]:
                console.print(f"[yellow]Batch job {api_job_id} is still {status}. Suspending pipeline.[/yellow]")
                return True # STILL SUSPENDED
            
            elif status in ["succeeded", "completed", "finished"]:
                console.print(f"[bold green]Batch job {api_job_id} is COMPLETE! Downloading results...[/bold green]")
                output_path = batch_dir / f"{jobstate_path.stem}_results.jsonl"
                bm.download_results(api_job_id, str(output_path))
                
                # Apply the text to the document
                with open(output_path, "r", encoding="utf-8") as rf:
                    for line in rf:
                        if not line.strip(): continue
                        res = json.loads(line)
                        # Gemini specific parsing
                        if provider == "gemini":
                            request_id = res.get("request", {}).get("name", "")
                            # Find the text in the response
                            try:
                                transcribed_text = res["response"]["candidates"][0]["content"]["parts"][0]["text"]
                            except (KeyError, IndexError):
                                transcribed_text = "[OCR Failed]"
                        
                        # Match the request_id back to the markdown image link
                        for img_meta in state.get("images", []):
                            if img_meta["request_id"] == request_id:
                                match_text = img_meta["match"]
                                # Replace the markdown link with the transcribed text!
                                document.content = document.content.replace(match_text, f"{match_text}\\n\\n{transcribed_text}\\n\\n")
                                break
                                
                # Delete the jobstate to formally mark it as COMPLETED
                os.remove(jobstate_path)
                return False # FINISHED! Pipeline can move to Clean Phase!
                
            else:
                console.print(f"[bold red]Batch job {api_job_id} FAILED or CANCELLED (Status: {status}).[/bold red]")
                os.remove(jobstate_path) # Delete it so we can try again next time
                return False # Let it fail gracefully or proceed without OCR

    # -------------------------------------------------------------
    # 2. NEW JOB CREATION
    # -------------------------------------------------------------
    # If we reached here, no active jobstate exists. Let's find images to OCR.
    img_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
    matches = list(img_pattern.finditer(document.content))
    
    if not matches:
        return False
        
    staging_dir = Path(config.io.directories.staging)
    images_to_process = []
    
    for match in matches:
        rel_path_str = match.group(1)
        full_path = staging_dir / rel_path_str
        if full_path.exists():
            images_to_process.append({
                "match": match.group(0),
                "full_path": str(full_path.absolute())
            })
            
    if not images_to_process:
        return False
        
    console.print(f"[cyan]Found {len(images_to_process)} images to transcribe for {document.source_file}.[/cyan]")
    
    if mode == "async_batch":
        job_id_local = f"{Path(document.source_file).stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        jsonl_path = batch_dir / f"{job_id_local}.jsonl"
        
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for i, img_data in enumerate(images_to_process):
                request_id = f"{document.source_file}---{i}"
                b64_data = _encode_image(img_data["full_path"])
                
                if provider == "gemini":
                    payload = {
                        "request": {
                            "name": request_id,
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [
                                        {"text": "Extract all text exactly as written. Output only the transcription."},
                                        {"inline_data": {"mime_type": "image/png", "data": b64_data}}
                                    ]
                                }
                            ]
                        }
                    }
                    f.write(json.dumps(payload) + "\\n")
                else:
                    console.print("[red]Only Gemini batch payloads are currently structured.[/red]")
                    return False
                    
        bm = BatchManager(provider)
        try:
            api_job_id = bm.submit_job(str(jsonl_path))
            jobstate_path = batch_dir / f"{job_id_local}.jobstate"
            state = {
                "document": document.source_file,
                "api_job_id": api_job_id,
                "status": "pending",
                "images": [{"request_id": f"{document.source_file}---{i}", "match": img["match"]} for i, img in enumerate(images_to_process)]
            }
            with open(jobstate_path, "w") as jsf:
                json.dump(state, jsf, indent=2)
                
            return True # SUSPENDED
            
        except Exception as e:
            console.print(f"[red]Failed to submit batch job: {e}[/red]")
            return False

    elif mode == "sync_live":
        console.print("[yellow]Sync Live transcription not fully implemented yet. Skipping.[/yellow]")
        return False
        
    elif mode == "local_vlm":
        import requests
        console.print(f"[cyan]Dispatching {len(images_to_process)} images to local Ollama model '{model}'...[/cyan]")
        
        for idx, img_data in enumerate(images_to_process):
            console.print(f"  [dim]- Processing image {idx+1}/{len(images_to_process)}...[/dim]")
            b64_data = _encode_image(img_data["full_path"])
            
            payload = {
                "model": model,
                "prompt": "Extract all text exactly as written. Output only the transcription.",
                "images": [b64_data],
                "stream": False
            }
            
            try:
                response = requests.post("http://localhost:11434/api/generate", json=payload)
                response.raise_for_status()
                res_data = response.json()
                transcribed_text = res_data.get("response", "[OCR Failed - Empty Response]")
            except Exception as e:
                console.print(f"  [red]- Failed to process image {idx+1}: {e}[/red]")
                transcribed_text = f"[OCR Failed - Error: {e}]"
                
            # Inject transcription into document
            match_text = img_data["match"]
            document.content = document.content.replace(match_text, f"{match_text}\\n\\n{transcribed_text.strip()}\\n\\n")
            
        return False
        
    return False
