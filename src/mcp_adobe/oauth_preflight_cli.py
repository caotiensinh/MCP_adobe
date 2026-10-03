from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .auth import OAuthResourceConfig
from .oauth_preflight import preflight_summary, run_provider_preflight


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate MCP Adobe OAuth provider compatibility before remote ChatGPT/Codex deployment."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = OAuthResourceConfig.from_env()
    except ValueError as exc:
        print(f"FAIL oauth_config: {exc}", file=sys.stderr)
        return 2
    if config is None:
        print(
            "FAIL oauth_config: OAuth environment is not configured. Set MCP_ADOBE_OAUTH_ISSUER_URL, "
            "MCP_ADOBE_OAUTH_RESOURCE_URL, and MCP_ADOBE_OAUTH_INTROSPECTION_ENDPOINT.",
            file=sys.stderr,
        )
        return 2

    findings = asyncio.run(run_provider_preflight(config))
    summary = preflight_summary(findings)
    if args.json:
        print(
            json.dumps(
                {
                    "resource_url": config.resource_url,
                    "issuer_url": config.issuer_url,
                    "required_scopes": list(config.required_scopes),
                    "summary": summary,
                    "findings": [item.as_dict() for item in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for item in findings:
            print(f"[{item.status}] {item.check}: {item.detail}")
        print(f"SUMMARY pass={summary['pass']} warn={summary['warn']} fail={summary['fail']}")

    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
