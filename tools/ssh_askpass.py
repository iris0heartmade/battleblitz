#!/usr/bin/env python
"""SSH_ASKPASS helper: prints the password from BB_SSH_PASS env var."""
import os, sys
sys.stdout.write(os.environ.get("BB_SSH_PASS", ""))
sys.stdout.flush()