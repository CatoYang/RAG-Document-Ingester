import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.extractors.batch_manager import BatchManager
from rich.console import Console
import yaml

console = Console()

def resolve_batches():
    batch_jobs_dir = Path("data/staging/batch_jobs")
    if not batch_jobs_dir.exists():
        console.print("[yellow]No batch_jobs directory found.[/yellow]")
        return

    jobstate_files = list(batch_jobs_dir.glob("*.jobstate"))
    if not jobstate_files:
        console.print("[yellow]No pending batch jobs found.[/yellow]")
        return

    for jobstate_file in jobstate_files:
        console.print(f"\\n[cyan]Checking jobstate: {jobstate_file.name}[/cyan]")
        
        with open(jobstate_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            
        job_id = state.get("job_id")
        provider = state.get("provider")
        output_dir = Path(state.get("output_dir"))
        pdf_path = Path(state.get("pdf_path"))
        md_text_chunks = state.get("md_text_chunks", [])
        images_info = state.get("images", [])

        if not job_id or job_id == "FAILED_TO_SUBMIT":
            console.print("[red]Invalid job ID. Skipping.[/red]")
            continue

        manager = BatchManager(provider=provider)
        
        try:
            status = manager.check_status(job_id)
            console.print(f"Status: [bold]{status}[/bold]")
            
            # OpenAI complete is 'completed', Anthropic is 'ended', Gemini is 'SUCCEEDED'
            if status.lower() in ["completed", "ended", "succeeded"]:
                results_path = batch_jobs_dir / f"{job_id}_results.jsonl"
                manager.download_results(job_id, str(results_path))
                
                # Parse results and create description map
                descriptions = {}
                with open(results_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip(): continue
                        res = json.loads(line)
                        
                        if provider in ["openai", "gemini"]:
                            # Format: {"custom_id": "...", "response": {"body": {"choices": [{"message": {"content": "..."}}]}}}
                            custom_id = res.get("custom_id")
                            try:
                                desc = res["response"]["body"]["choices"][0]["message"]["content"]
                                descriptions[custom_id] = desc
                            except KeyError:
                                descriptions[custom_id] = "[API Error parsing response]"
                        elif provider == "anthropic":
                            # Format: {"custom_id": "...", "result": {"message": {"content": [{"text": "..."}]}}}
                            custom_id = res.get("custom_id")
                            try:
                                desc = res["result"]["message"]["content"][0]["text"]
                                descriptions[custom_id] = desc
                            except KeyError:
                                descriptions[custom_id] = "[API Error parsing response]"

                # Inject into chunks
                for i in range(len(md_text_chunks)):
                    for img_info in images_info:
                        if img_info['match_str'] in md_text_chunks[i]:
                            desc = descriptions.get(img_info['filename'], "[OCR PENDING/FAILED]")
                            
                            # Replace newlines with quote markers
                            vlm_quoted = desc.replace('\\n', '\\n> ')
                            
                            # Calculate relative path
                            img_path = Path(img_info['path'])
                            try:
                                rel_to_md = os.path.relpath(img_path, output_dir).replace("\\\\", "/")
                            except ValueError:
                                rel_to_md = str(img_path.resolve()).replace("\\\\", "/")

                            replacement = f"![Diagram]({rel_to_md})\\n\\n> **Image Analysis (via {provider} Batch API):**\\n> {vlm_quoted}\\n"
                            md_text_chunks[i] = md_text_chunks[i].replace(img_info['match_str'], replacement)

                # Save final markdown
                final_md = "\\n\\n".join(md_text_chunks)
                
                metadata = {
                    "source": pdf_path.name,
                    "extractor": {
                        "program": "EnterpriseBatchExtractor",
                        "provider": provider,
                        "job_id": job_id
                    }
                }
                
                frontmatter = f"---\\n{yaml.dump(metadata, sort_keys=False)}---\\n\\n"
                
                output_file = output_dir / f"{pdf_path.stem}.md"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(frontmatter + final_md)
                    
                console.print(f"[bold green]Successfully stitched document: {output_file}[/bold green]")
                
                # Cleanup jobstate
                jobstate_file.unlink()
                console.print(f"[dim]Removed jobstate {jobstate_file.name}[/dim]")
                
            elif status.lower() in ["failed", "expired", "cancelled"]:
                console.print(f"[bold red]Job failed or expired. Please resubmit.[/bold red]")
            else:
                console.print("[yellow]Job is still processing. Try again later.[/yellow]")
                
        except Exception as e:
            console.print(f"[bold red]Error checking/resolving job: {e}[/bold red]")

if __name__ == "__main__":
    resolve_batches()
