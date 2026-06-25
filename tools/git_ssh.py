#!/usr/bin/env python
"""SSH wrapper for git: accepts password from env var BB_SSH_PASS.

Usage:
    GIT_SSH_COMMAND="python tools/git_ssh.py" git push pi master
"""
import os
import sys

try:
    import paramiko
except ImportError:
    sys.stderr.write("git_ssh.py: paramiko not installed\n")
    sys.exit(1)

host = sys.argv[1] if len(sys.argv) > 1 else ""
# Git passes: <user>@<host> <cmd...>
if "@" in host:
    user, host = host.split("@", 1)
else:
    user = "youko"

passwd = os.environ.get("BB_SSH_PASS", "")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, username=user, password=passwd, timeout=15)
cmd = " ".join(sys.argv[2:])
stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
sys.stdout.buffer.write(stdout.read())
sys.stderr.buffer.write(stderr.read())
client.close()
PYEOF