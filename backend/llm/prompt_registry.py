"""
Prompt Registry.

Manages versioned prompts loaded from files for reproducibility and auditability.
Each prompt file contains metadata, system prompt, and user template.
"""

import hashlib
import re
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel


class PromptTemplate(BaseModel):
    """A loaded prompt template with metadata."""

    template_id: str  # e.g., "batch_score_v1.0.0"
    version: str
    mode: str
    max_output_tokens: int
    system_prompt: str
    user_template: str
    prompt_hash: str  # SHA256 of system + user content

    def render_user_prompt(self, **kwargs) -> str:
        """Render the user prompt template with variables."""
        result = self.user_template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


class PromptRegistry:
    """
    Registry for loading and managing prompt templates.

    Prompts are loaded from markdown files with the following structure:
    - Metadata section with version, mode, max tokens
    - System Prompt section
    - User Prompt Template section

    The registry ensures:
    1. Deterministic loading (same file = same hash)
    2. Version tracking for reproducibility
    3. Template rendering with variable substitution
    """

    PROMPTS_DIR = Path(__file__).parent / "prompts"

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize the registry.

        Args:
            prompts_dir: Directory containing prompt files (default: llm/prompts/)
        """
        self.prompts_dir = prompts_dir or self.PROMPTS_DIR
        self._cache: Dict[str, PromptTemplate] = {}

    def load(self, prompt_id: str) -> PromptTemplate:
        """
        Load a prompt template by ID.

        Args:
            prompt_id: Prompt identifier (e.g., "batch_score_v1" or "batch_score_v1.0.0")

        Returns:
            PromptTemplate with parsed content

        Raises:
            FileNotFoundError: If prompt file doesn't exist
            ValueError: If prompt file has invalid format
        """
        # Check cache first
        if prompt_id in self._cache:
            return self._cache[prompt_id]

        # Try to find the file
        prompt_file = self._find_prompt_file(prompt_id)
        if not prompt_file:
            raise FileNotFoundError(f"Prompt not found: {prompt_id}")

        # Parse the file
        template = self._parse_prompt_file(prompt_file)
        self._cache[prompt_id] = template
        return template

    def _find_prompt_file(self, prompt_id: str) -> Optional[Path]:
        """Find the prompt file for the given ID."""
        # Try exact match first
        candidates = [
            self.prompts_dir / f"{prompt_id}.md",
            self.prompts_dir / prompt_id / "prompt.md",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Try pattern matching (e.g., "batch_score_v1" matches "batch_score_v1.md")
        for file in self.prompts_dir.glob("*.md"):
            if file.stem.startswith(prompt_id.replace(".0.0", "")):
                return file

        return None

    def _parse_prompt_file(self, filepath: Path) -> PromptTemplate:
        """Parse a prompt markdown file into a PromptTemplate."""
        content = filepath.read_text()

        # Extract metadata
        metadata = self._extract_metadata(content)

        # Extract system prompt
        system_prompt = self._extract_section(content, "System Prompt")
        if not system_prompt:
            raise ValueError(f"Missing 'System Prompt' section in {filepath}")

        # Extract user template
        user_template = self._extract_section(content, "User Prompt Template")
        if not user_template:
            raise ValueError(f"Missing 'User Prompt Template' section in {filepath}")

        # Calculate hash of system + user content
        hash_content = f"{system_prompt}\n---\n{user_template}"
        prompt_hash = hashlib.sha256(hash_content.encode()).hexdigest()[:16]

        # Build template ID from filename or metadata
        template_id = filepath.stem
        version = metadata.get("version", "1.0.0")

        return PromptTemplate(
            template_id=template_id,
            version=version,
            mode=metadata.get("mode", "batch_score"),
            max_output_tokens=int(metadata.get("max_output_tokens", 400)),
            system_prompt=system_prompt,
            user_template=user_template,
            prompt_hash=prompt_hash,
        )

    def _extract_metadata(self, content: str) -> Dict[str, str]:
        """Extract metadata from the Metadata section."""
        metadata = {}
        metadata_section = self._extract_section(content, "Metadata")

        if metadata_section:
            for line in metadata_section.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    line = line[2:]
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower().replace(" ", "_")
                        metadata[key] = value.strip()

        return metadata

    def _extract_section(self, content: str, section_name: str) -> Optional[str]:
        """Extract content from a markdown section."""
        # Look for ## Section Name
        pattern = rf"## {re.escape(section_name)}\s*\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            section_content = match.group(1).strip()
            # Remove any leading/trailing markdown artifacts
            return section_content

        return None

    def list_prompts(self) -> list[str]:
        """List all available prompt IDs."""
        prompts = []
        for file in self.prompts_dir.glob("*.md"):
            prompts.append(file.stem)
        return sorted(prompts)


# Global registry instance
_registry: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """Get the global prompt registry."""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry


def load_prompt(prompt_id: str) -> PromptTemplate:
    """Convenience function to load a prompt."""
    return get_prompt_registry().load(prompt_id)
