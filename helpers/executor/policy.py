"""Strategy pattern for applying data policies to flowing edge values."""

import json
import tempfile
from typing import Any

from models.edge import Edge
from models.enums import DataPolicy
from models.task import ExecutionContext


class DataPolicyStrategy:
    """Applies DataPolicy rules on a value flowing through an edge."""

    @staticmethod
    def apply(value: Any, edge: Edge, context: ExecutionContext) -> Any:
        """Enforce DataPolicy on a value flowing through an edge.

        PASS_THROUGH: return as-is.
        SUMMARIZE: LLM summarizes to max_chars.
        REFERENCE: store to temp file, return metadata.
        TRUNCATE: hard-truncate to max_chars.
        """
        policy = edge.data_policy
        max_chars = edge.max_chars or 4000

        if policy == DataPolicy.PASS_THROUGH:
            return value

        serialized = json.dumps(value) if not isinstance(value, str) else value

        if policy == DataPolicy.TRUNCATE:
            if len(serialized) > max_chars:
                return serialized[:max_chars] + "\\n[...TRUNCATED]"
            return value

        if policy == DataPolicy.SUMMARIZE:
            if len(serialized) <= max_chars:
                return value  # small enough, no summarization needed
            summary_prompt = (
                f"Summarize the following data concisely in under {max_chars} characters. "
                f"Preserve all key facts, numbers, and field names:\\n\\n{serialized}"
            )
            response = context.llm_client.send(
                prompt=summary_prompt,
                usage_type="summarize",
                max_output_tokens=max_chars // 3,  # rough char-to-token ratio
            )
            return response.content

        if policy == DataPolicy.REFERENCE:
            # Store to temp file and return a reference
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="agent_ref_", delete=False
            ) as f:
                json.dump(value, f)
                ref_path = f.name
            summary = f"Data reference ({len(serialized)} chars)"
            return {"__ref": ref_path, "summary": summary}

        return value  # fallback
