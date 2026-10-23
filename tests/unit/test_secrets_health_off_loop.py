#  Project:   scalo
#  File:      tests/unit/test_secrets_health_off_loop.py
#  Purpose:   Masking a health fault never runs the cold scrubber build on the event loop
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The first masked health fault builds the scrubber, which takes about half a second, and must not stall the loop.

Each case runs in a fresh interpreter, because the scrubber build is cached once per process and a test process
has usually built it already. A heartbeat task wakes every 10 ms and records the longest gap between wake-ups.
Built on the loop, the build is one gap as long as the health check itself. Built on a worker thread, the loop
still sees short gaps while the thread holds the GIL, but none close to the check's duration.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import scalo

# The subprocess must import the same scalo tree as this test process, not whichever copy is installed.
_SRC = Path(scalo.__file__).resolve().parents[1]

# Built at run time so no source-scanning tool sees a credential in the file.
_PASSWORD = "pw" + "-sentinel-" + "7f3a91"

_PROBE = """
import asyncio
import json
import logging
import socket
import sys
import time

from scalo.secrets.manager import SecretsManager
from scalo.secrets.providers.file import FileProvider
from scalo.secrets.providers.openbao import OpenBaoProvider
from scalo.secrets.types import CacheConfig, OpenBaoConfig

PASSWORD = "pw" + "-sentinel-" + "7f3a91"


class Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(f"{record.name} {record.levelname} {record.getMessage()}")


class Raises(FileProvider):
    async def health_check_async(self):
        raise ConnectionRefusedError(f"https://svc:{PASSWORD}@vault.internal:8200 refused")


def closed_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def main(scenario):
    collector = Collect()
    logging.getLogger().addHandler(collector)
    logging.getLogger().setLevel(logging.INFO)
    if scenario == "manager":
        provider = Raises()
    else:
        provider = OpenBaoProvider(OpenBaoConfig(address=f"http://127.0.0.1:{closed_port()}", token="t", timeout_secs=2))
    manager = SecretsManager(providers={"openbao": provider}, cache_config=CacheConfig(enabled=False))

    gaps = []

    async def beat():
        last = time.perf_counter()
        while True:
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    heartbeat = asyncio.create_task(beat())
    await asyncio.sleep(0.1)
    started = time.perf_counter()
    result = await manager.health_check()
    took = time.perf_counter() - started
    # A stall ends when the heartbeat next runs, so let it run before reading the gaps.
    await asyncio.sleep(0.05)
    heartbeat.cancel()
    await manager.close()
    print(json.dumps({"max_gap": max(gaps), "took": took, "result": result, "lines": collector.lines}))


asyncio.run(main(sys.argv[1]))
"""


def _run(scenario: str, tmp_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, scenario],
        capture_output=True,
        check=False,
        cwd=tmp_path,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        errors="replace",
        timeout=180,
    )
    assert result.returncode == 0, f"the probe failed:\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def _assert_loop_kept_running(reported: dict) -> None:
    # Below 0.2 s the whole check is too short to tell a stall from scheduling jitter.
    limit = max(0.6 * reported["took"], 0.2)
    assert reported["max_gap"] < limit, (
        f"the event loop stalled for {reported['max_gap']:.3f} s during a health check that took "
        f"{reported['took']:.3f} s, so the scrubber was built on it"
    )


class TestColdScrubberBuild:
    def test_a_fault_the_manager_catches_is_masked_off_the_loop(self, tmp_path):
        reported = _run("manager", tmp_path)

        assert reported["result"]["openbao"] is False
        warnings = [line for line in reported["lines"] if " WARNING " in line]
        assert len(warnings) == 1, warnings
        assert "scalo.secrets.manager" in warnings[0]
        assert "REDACTED" in warnings[0]
        assert _PASSWORD not in " ".join(reported["lines"])
        _assert_loop_kept_running(reported)

    def test_a_provider_logging_its_own_reason_masks_it_off_the_loop(self, tmp_path):
        reported = _run("provider", tmp_path)

        assert reported["result"]["openbao"] is False
        warnings = [line for line in reported["lines"] if " WARNING " in line]
        assert len(warnings) == 1, warnings
        assert "scalo.secrets.providers.openbao" in warnings[0]
        _assert_loop_kept_running(reported)
