import re
from src.config.settings import CleanupSettings

class DocumentCleaner:
    def __init__(self, config: CleanupSettings):
        self.config = config

    def _deduplicate_consecutive_paragraphs(self, text: str) -> str:
        """Removes consecutive identical (or highly similar) paragraph sequences (up to length 5)."""
        paragraphs = re.split(r'\n{2,}', text)
        if not paragraphs:
            return text
            
        deduplicated = []
        for p in paragraphs:
            current = p.strip()
            if not current:
                continue
                
            deduplicated.append(current)
            
            # Check if the end of `deduplicated` forms a repeating sequence
            # We check all possible sequence lengths up to half the document
            for seq_len in range(1, len(deduplicated) // 2 + 1):
                seq1 = [x.lower() for x in deduplicated[-seq_len:]]
                seq2 = [x.lower() for x in deduplicated[-2*seq_len:-seq_len]]
                
                if seq1 == seq2:
                    # We found a repeating sequence, pop it off
                    for _ in range(seq_len):
                        deduplicated.pop()
                    break # Only collapse once per new paragraph
            
        return '\n\n'.join(deduplicated)

    def clean(self, text: str) -> str:
        """Applies configured cleanup rules to the text."""
        if not text:
            return text

        cleaned_text = text

        # 1. Remove zero-width spaces and other invisible formatting characters
        if self.config.remove_zero_width_spaces:
            cleaned_text = cleaned_text.replace('\u200b', '')
            cleaned_text = cleaned_text.replace('\ufeff', '')
            cleaned_text = cleaned_text.replace('\u200c', '')
            cleaned_text = cleaned_text.replace('\u200d', '')

        # 2. Trim trailing whitespace on every line
        if self.config.trim_trailing_whitespace:
            lines = cleaned_text.split('\n')
            cleaned_text = '\n'.join([line.rstrip() for line in lines])

        # 3. Apply custom regex removals
        if self.config.regex_removals:
            for pattern in self.config.regex_removals:
                try:
                    # Use re.IGNORECASE by default for user convenience, unless specified otherwise
                    cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.MULTILINE)
                except re.error as e:
                    print(f"Warning: Invalid regex pattern '{pattern}' - {e}")

        # 4. Collapse consecutive newlines (more than 2 into exactly 2)
        if self.config.collapse_newlines:
            # Replaces 3 or more newlines with exactly 2 newlines (a standard paragraph break)
            cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
            
            # Replaces multiple empty spaces on a line with a single space, but leaves indentation alone
            # Actually, let's just stick to newline collapsing to avoid ruining markdown tables.

        # 5. Deduplicate consecutive paragraphs
        if self.config.deduplicate_paragraphs:
            cleaned_text = self._deduplicate_consecutive_paragraphs(cleaned_text)

        return cleaned_text.strip()
