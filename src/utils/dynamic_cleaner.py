import re
import json
import asyncio
from typing import List, Dict, Any, Tuple
from rich.console import Console

console = Console()


class DynamicLLMCleaner:
    """Uses an LLM to dynamically generate boilerplate removal regex patterns and safely applies them."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', False)
        self.provider = config.get('provider', 'ollama')
        self.params = config.get('params', {})

        self.gemini_model = None
        self.ollama_client = None

        if self.provider == 'gemini':
            import google.generativeai as genai
            api_key = self.params.get('api_key', '')
            if api_key:
                genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel(
                self.params.get('model', 'gemini-1.5-flash'))
        elif self.provider == 'ollama':
            from ollama import AsyncClient
            self.ollama_client = AsyncClient(
                host=self.params.get(
                    'url', 'http://localhost:11434'))
            self.model_name = self.params.get('model', 'llama3')

    def _sample_document(self, text: str) -> str:
        """Grabs the first 3000, middle 3000, and last 3000 characters."""
        if len(text) < 15000:
            return text

        mid_start = len(text) // 2 - 1500
        return (
            text[:3000] +
            "\n\n[...MIDDLE OF DOCUMENT...]\n\n" +
            text[mid_start:mid_start + 3000] +
            "\n\n[...END OF DOCUMENT...]\n\n" +
            text[-3000:]
        )

    async def _identify_patterns_with_llm(
            self, sample: str, filename: str) -> List[Dict[str, Any]]:
        prompt = f"""
You are a Regex specialist. Analyze this markdown document sample from '{filename}'.
Identify repetitive boilerplate text like headers, footers, page number formats, and copyright watermarks that should be stripped.

CRITICAL INSTRUCTIONS:
- You MUST NOT use unbound wildcards like `.*` or `[\\s\\S]+`. These cause catastrophic backtracking (ReDoS) on 50MB text files!
- Use exact string matches or strictly bounded wildcards only (e.g. `[^\\n]{0,50}`).
- Return ONLY valid JSON, no markdown blocks.

Return a JSON array of objects, where each object has:
- "pattern": The Python regex pattern to match the text (use properly escaped strings).
- "description": What this pattern removes.
- "confidence": An integer from 0 to 100 on how confident you are this is boilerplate and not core content.
Example:
[
    {{"pattern": "(?i)^Vampire: The Masquerade 5th Edition\\\\s*$", "description": "Header title", "confidence": 95}},
    {{"pattern": "^Page \\\\d+$\\\\n", "description": "Page numbers", "confidence": 99}}
]

Document Sample:
{sample}
"""
        try:
            if self.provider == 'gemini' and self.gemini_model:
                response = await asyncio.to_thread(self.gemini_model.generate_content, prompt)
                content = response.text
            elif self.provider == 'ollama' and self.ollama_client:
                response = await self.ollama_client.chat(
                    model=self.model_name,
                    messages=[{'role': 'user', 'content': prompt}],
                    format='json'
                )
                content = response['message']['content']
            else:
                return []

            # Cleanup markdown block if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            parsed = json.loads(content.strip())
            if isinstance(parsed, dict):
                # The LLM might have wrapped the array in an object like
                # {"patterns": [...]}
                for key in parsed:
                    if isinstance(parsed[key], list):
                        return parsed[key]
                return [parsed]  # Fallback
            elif isinstance(parsed, list):
                return parsed
            else:
                return []
        except Exception as e:
            console.print(
                f"[red]LLM Generation failed or invalid JSON: {e}[/red]")
            # console.print(f"[dim]Raw content was: {content}[/dim]")
            return []

    async def clean(self, text: str, filename: str) -> Tuple[str, List[Dict]]:
        if not self.enabled:
            return text, []

        sample = self._sample_document(text)
        console.print(
            f"[dim]Requesting dynamic LLM cleaner patterns for {filename}...[/dim]")

        patterns = await self._identify_patterns_with_llm(sample, filename)
        if not patterns or not isinstance(patterns, list):
            return text, []

        review_required = []
        cleaned_text = text

        for rule in patterns:
            if not isinstance(rule, dict):
                continue
            pattern_str = rule.get('pattern', '')
            confidence = rule.get('confidence', 0)

            if confidence < 80:
                rule['reason'] = "Low confidence"
                rule['filename'] = filename
                review_required.append(rule)
                continue

            try:
                # Dry run
                compiled = re.compile(pattern_str, re.MULTILINE)
                matches = compiled.findall(cleaned_text)
                if not matches:
                    continue

                # Calculate blast radius (characters removed)
                original_len = len(cleaned_text)
                temp_text = compiled.sub('', cleaned_text)
                removed_chars = original_len - len(temp_text)

                blast_percentage = (removed_chars / original_len) * 100

                if blast_percentage > 3.0:
                    rule['reason'] = f"Blast radius too large ({blast_percentage:.1f}%)"
                    rule['removed_chars'] = removed_chars
                    rule['filename'] = filename
                    review_required.append(rule)
                    continue

                # Apply safely
                cleaned_text = temp_text
                console.print(
                    f"[green]Stripped pattern: '{pattern_str}' ({blast_percentage:.3f}% removed)[/green]")

            except re.error as e:
                rule['reason'] = f"Regex compilation error: {e}"
                rule['filename'] = filename
                review_required.append(rule)

        return cleaned_text, review_required
