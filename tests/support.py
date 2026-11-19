import contextlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODEL_ENV = {"ADK_MODEL_NAME": "offline-model", "ADK_MODEL_LOCATION": "us"}


@contextlib.contextmanager
def offline():
    with patch.dict(os.environ, MODEL_ENV), patch(
        "socket.socket.connect", side_effect=AssertionError("Network access forbidden")
    ), patch("google.auth.default", side_effect=AssertionError("ADC lookup forbidden")):
        yield


def isolated_python(paths, script, cwd):
    # -I discards PYTHONPATH and the working directory. Only the staged paths
    # are added back; site-packages still supply the locked test dependencies.
    setup = f"import sys; sys.dont_write_bytecode = True; sys.path[:0] = {[str(p) for p in paths]!r}\n"
    setup += "from unittest.mock import patch\n"
    setup += "patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')).start()\n"
    setup += "patch('google.auth.default', side_effect=AssertionError('ADC forbidden')).start()\n"
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("GOOGLE_", "ADK_", "PYTHON"))}
    environment.update(MODEL_ENV)
    result = subprocess.run(
        [sys.executable, "-I", "-c", setup + script], cwd=cwd, env=environment,
        capture_output=True, text=True, timeout=45,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout
