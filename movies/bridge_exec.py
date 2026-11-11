"""Replace this helper with an already verified, sealed bridge descriptor."""
import os
import sys

if len(sys.argv) != 2 or not sys.argv[1].isdigit() or os.execve not in os.supports_fd:
    sys.exit(126)
try:
    os.execve(int(sys.argv[1]), ['ani-luffy-bridge'], os.environ.copy())
except OSError:
    sys.exit(126)
