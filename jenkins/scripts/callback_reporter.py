#!/usr/bin/env python3
import argparse
import json
import os
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()
    base_url = os.environ.get("WEBHOOK_INTERNAL_URL", "http://webhook:8000").rstrip("/")
    token = os.environ["JENKINS_CALLBACK_TOKEN"]
    payload = json.loads(args.payload)
    request = urllib.request.Request(
        f"{base_url}/internal/jenkins/result",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Internal-Token": token,
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 202:
            raise RuntimeError(f"callback returned HTTP {response.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
