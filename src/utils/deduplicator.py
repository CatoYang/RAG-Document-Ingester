import hashlib
from typing import List, Dict
from pathlib import Path
from rich.console import Console
from src.config.settings import DeduplicationSettings

console = Console()


class DocumentDeduplicator:
    def __init__(self, config: DeduplicationSettings):
        self.config = config

    def _hash_file(self, file_path: Path, chunk_size: int = 8192) -> str:
        """Calculates the SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()

    def filter_duplicates(self, files: List[Path]) -> List[Path]:
        """Filters out exact duplicate files using a two-stage size and hash check."""
        if not self.config.enabled:
            return files

        if self.config.method != "exact":
            console.print(
                f"[yellow]Warning: Deduplication method '{self.config.method}' is not fully implemented yet. Using 'exact'.[/yellow]")

        console.print("[dim]Running deduplication pass...[/dim]")

        # Stage 1: Group by file size
        size_map: Dict[int, List[Path]] = {}
        for file in files:
            try:
                size = file.stat().st_size
                size_map.setdefault(size, []).append(file)
            except OSError as e:
                console.print(f"[red]Error reading size for {file}: {e}[/red]")

        unique_files: List[Path] = []
        hash_map: Dict[str, Path] = {}
        duplicate_count = 0

        # Stage 2: Hash check for files with identical sizes
        for size, file_group in size_map.items():
            if len(file_group) == 1:
                # Unique size, no need to hash
                unique_files.append(file_group[0])
            else:
                # Potential duplicates, calculate hashes
                for file in file_group:
                    try:
                        file_hash = self._hash_file(file)
                        if file_hash in hash_map:
                            duplicate_count += 1
                            console.print(
                                f"[yellow]Skipping duplicate: '{file.name}' (identical to '{hash_map[file_hash].name}')[/yellow]")
                        else:
                            hash_map[file_hash] = file
                            unique_files.append(file)
                    except OSError as e:
                        console.print(f"[red]Error hashing {file}: {e}[/red]")
                        # Fail safe: process it anyway
                        unique_files.append(file)

        if duplicate_count > 0:
            console.print(
                f"[bold green]Deduplication complete. Filtered {duplicate_count} duplicate files.[/bold green]")
        else:
            console.print(
                f"[dim]Deduplication complete. No exact duplicates found.[/dim]")

        return unique_files
