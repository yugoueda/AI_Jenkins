#!/usr/bin/env python3
import os
import sys
import time


prompt = sys.stdin.read()
mode = os.getenv("FAKE_CLAUDE_MODE", "success")

if mode == "timeout":
    time.sleep(10)
elif mode == "failure":
    print("fake CLI failure", file=sys.stderr)
    raise SystemExit(7)
elif mode == "large":
    print("x" * 1024)
else:
    if os.getenv("FAKE_CLAUDE_CAPTURE"):
        with open(os.environ["FAKE_CLAUDE_CAPTURE"], "w", encoding="utf-8") as capture:
            capture.write(prompt)
            capture.write("\nARGS=")
            capture.write(" ".join(sys.argv[1:]))
    print('{"findings":[]}')
