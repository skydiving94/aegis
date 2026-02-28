"""Edge model for skill DAGs."""

from pydantic import BaseModel

from models.enums import DataPolicy


class Edge(BaseModel):
    """Connects two nodes in a skill DAG with output-to-input mapping."""

    source_node_id: str
    target_node_id: str
    output_mapping: dict[str, str]  # source_output_name -> target_input_name
    data_policy: DataPolicy = DataPolicy.PASS_THROUGH
    max_chars: int | None = None  # character budget for TRUNCATE/SUMMARIZE
