# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Tool catalogues offered to each pipeline stage.

Mirrors the real MCP request schemas closely enough for the model to produce
valid arguments, while hiding options a stage has no business setting.
"""

from __future__ import annotations

from typing import Any

ToolSpec = dict[str, Any]

LIST_DATASETS: ToolSpec = {
    "name": "list_datasets",
    "description": (
        "Search datasets the current user can read. Use 'search' with keywords "
        "drawn from the design's implied data. Returns id, table_name, schema. "
        "'search' and 'filters' are mutually exclusive."
    ),
    "arguments": {
        "request": {
            "search": "string | null - free-text search across dataset fields",
            "page": "int - 1-BASED page number, default 1. Must be > 0.",
            "page_size": "int - results per page, must be > 0, keep <= 25",
        }
    },
}

GET_DATASET_INFO: ToolSpec = {
    "name": "get_dataset_info",
    "description": (
        "Authoritative columns and metrics for one dataset. The ONLY source "
        "you may bind column or metric names from. Call it for your shortlist, "
        "never for every dataset."
    ),
    "arguments": {
        "request": {
            "identifier": "int | string - dataset id from list_datasets, or UUID",
        }
    },
}

EXECUTE_SQL: ToolSpec = {
    "name": "execute_sql",
    "description": (
        "Run a small SELECT to prove a derived expression works before you "
        "commit to it. Always use a tiny LIMIT. Read-only validation only - "
        "never mutate."
    ),
    "arguments": {
        "request": {
            "database_id": "int - from the dataset's database",
            "sql": "string - SELECT ... LIMIT 1",
            "limit": "int - keep <= 5",
        }
    },
}

LIST_CHARTS: ToolSpec = {
    "name": "list_charts",
    "description": (
        "Search existing saved charts to find ones worth reusing. Query per "
        "bound dataset and by keywords from region titles. An instance may "
        "hold thousands of charts - search, never enumerate. "
        "'search' and 'filters' are mutually exclusive."
    ),
    "arguments": {
        "request": {
            "search": "string | null - free-text across chart fields",
            "filters": (
                "list of {col, opr, value} - e.g. "
                "[{'col': 'datasource_id', 'opr': 'eq', 'value': 42}]"
            ),
            "page": "int - 1-BASED page number, default 1. Must be > 0.",
            "page_size": "int - results per page, must be > 0, keep <= 25",
        }
    },
}

GET_CHART_INFO: ToolSpec = {
    "name": "get_chart_info",
    "description": (
        "Confirm what a candidate chart actually renders: viz_type, datasource, "
        "and the columns and metrics it uses. A 'reuse' decision is only valid "
        "once this has confirmed the chart - a promising name is not evidence."
    ),
    "arguments": {
        "request": {"identifier": "int | string - chart id from list_charts, or UUID"}
    },
}

STAGE_B_TOOLS: list[ToolSpec] = [LIST_DATASETS, GET_DATASET_INFO, EXECUTE_SQL]
STAGE_C_TOOLS: list[ToolSpec] = [LIST_CHARTS, GET_CHART_INFO]


def render_catalog(tools: list[ToolSpec]) -> str:
    """Render a tool catalogue as prompt text."""
    lines = []
    for spec in tools:
        lines.append(f"### {spec['name']}")
        lines.append(spec["description"])
        lines.append("Arguments:")
        for arg, shape in spec["arguments"].items():
            if isinstance(shape, dict):
                lines.append(f"  {arg}:")
                for key, desc in shape.items():
                    lines.append(f"    {key}: {desc}")
            else:
                lines.append(f"  {arg}: {shape}")
        lines.append("")
    return "\n".join(lines)
