#!/usr/bin/env python3
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
"""Make one real Bedrock call and report what the account will accept.

Answers the questions that cannot be settled by reading code: whether the
credentials in this shell reach the model, and whether the newer top-level
request fields are allowed for it. Bedrock gates ``output_config`` and adaptive
``thinking`` per model, and a rejection is a 400 rather than something the SDK
can negotiate, so each is probed separately and reported as a config line to
paste into ``DESIGN_TO_DASHBOARD_LLM``.

Credentials come from the environment, never from an argument: a bearer token in
AWS_BEARER_TOKEN_BEDROCK, or the standard AWS chain (env keys, --aws-profile, an
instance role). Nothing secret is printed.

Usage:
    .venv/bin/python design-to-dashboard/scripts/check_bedrock.py \
        --model arn:aws:bedrock:us-east-1:...:application-inference-profile/xxx
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from superset.design_to_dashboard.llm.api_provider import (  # noqa: E402
    BedrockProvider,
    is_inference_profile,
)
from superset.design_to_dashboard.llm.base import LLMError  # noqa: E402

PROMPT = "Reply with the single word: ok"

# The last failure, kept so the summary can diagnose rather than guess.
_LAST_ERROR: list[str] = []


def _describe_credentials(profile: str | None) -> str:
    """Which credential source will be used, without revealing any of it."""
    if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        return "bearer token (AWS_BEARER_TOKEN_BEDROCK)"
    if profile:
        return f"AWS profile {profile!r}"
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        session = " + session token" if os.environ.get("AWS_SESSION_TOKEN") else ""
        return f"env access key{session}"
    return "default AWS chain (no env keys found -- may fail)"


def _diagnose(error: str) -> str:
    """Turn the failure into the thing to change, where it is recognisable."""
    if "CallWithBearerToken" in error:
        return (
            "The credential itself is valid -- the principal in the message is "
            "who AWS resolved you to. What is denied is the bearer-token "
            "mechanism: a Bedrock API key needs bedrock:CallWithBearerToken, "
            "which is separate from any InvokeModel permission. Use SigV4 "
            "credentials for the same role (access key + secret + session "
            "token, or an SSO profile) instead of AWS_BEARER_TOKEN_BEDROCK."
        )
    if "security token" in error and "invalid" in error:
        return (
            "The credentials did not resolve to any principal: expired, or "
            "from a different account than the model's."
        )
    if "AccessDenied" in error or "not authorized" in error:
        return (
            "Credentials resolved but the policy refused the call. On an "
            "application inference profile this is usually a Resource list "
            "naming the profile ARN without the underlying foundation model "
            "ARN, or a missing bedrock:InvokeModelWithResponseStream -- the "
            "pipeline always streams, so plain InvokeModel is not enough."
        )
    return (
        "Not a recognised failure. The request shape is not the suspect here, "
        "since narrowing it changed nothing."
    )


def _attempt(
    label: str,
    model: str,
    region: str,
    profile: str | None,
    overrides: dict[str, Any],
) -> bool:
    provider = BedrockProvider(
        model=model,
        aws_region=region,
        aws_profile=profile,
        max_tokens=1024,
        timeout=60,
        request_overrides=overrides,
    )
    try:
        response = provider.complete("You are a connectivity check.", PROMPT)
    except LLMError as ex:
        print(f"  {label}: FAILED\n    {ex}")
        _LAST_ERROR.append(str(ex))
        return False
    usage = response.usage or {}
    print(
        f"  {label}: ok -- {response.text.strip()[:40]!r} "
        f"(in={usage.get('input_tokens')} out={usage.get('output_tokens')})"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="model id, profile id or ARN")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--aws-profile", default=None)
    args = parser.parse_args()

    print(f"model:       {args.model}")
    print(f"             inference profile: {is_inference_profile(args.model)}")
    print(f"region:      {args.region}")
    print(f"credentials: {_describe_credentials(args.aws_profile)}")
    print("\nprobing:")

    common = (args.model, args.region, args.aws_profile)
    # Full request first. If it works nothing needs configuring; if it does not,
    # the narrowed attempts below isolate which field the model refused.
    if _attempt("full request (effort + adaptive thinking)", *common, {}):
        print("\nNo request_overrides needed.")
        return 0

    no_effort = _attempt("without output_config", *common, {"output_config": None})
    if no_effort:
        print('\nAdd:  "request_overrides": {"output_config": None}')
        print("Note: `effort` is then ignored for this model.")
        return 0

    minimal = _attempt(
        "without output_config or thinking",
        *common,
        {"output_config": None, "thinking": None},
    )
    if minimal:
        print(
            '\nAdd:  "request_overrides": '
            '{"output_config": None, "thinking": None}\n'
            "Note: no reasoning will stream to the UI for this model."
        )
        return 0

    print(f"\nEvery variant failed the same way.\n{_diagnose(_LAST_ERROR[-1])}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
