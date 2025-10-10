#!/usr/bin/env python3
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    except Exception:
        return False


class SolarizedFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[38;5;33m",
        "INFO": "\033[38;5;64m",
        "OK": "\033[38;5;64m",
        "WARNING": "\033[38;5;136m",
        "ERROR": "\033[38;5;160m",
        "CRITICAL": "\033[38;5;160m",
    }
    CYAN = "\033[36m"
    TIME = "\033[38;5;64m"
    RESET = "\033[0m"

    def formatTime(self, record, datefmt=None):
        dt = datetime.now().astimezone()
        if "%f" in (datefmt or ""):
            return dt.strftime(datefmt)
        # milliseconds + tz
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")[:-3]

    def format(self, record: logging.LogRecord) -> str:
        t = self.formatTime(record)
        level = record.levelname
        name = record.name
        func = record.funcName
        line = record.lineno
        msg = record.getMessage()
        if _is_tty():
            lvl_color = self.COLORS.get(level, self.CYAN)
            return (
                f"{self.TIME}{t}{self.RESET} | "
                f"{lvl_color}{level:<8}{self.RESET} | "
                f"{self.CYAN}{name}{self.RESET}:{self.CYAN}{func}{self.RESET}:{self.CYAN}{line}{self.RESET} - "
                f"{lvl_color}{msg}{self.RESET}"
            )
        return f"{t} | {level:<8} | {name}:{func}:{line} - {msg}"


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("branch-name")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(SolarizedFormatter())
    logger.addHandler(sh)

    log_file = os.environ.get("CI_LOG_FILE")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        if os.environ.get("CI_LOG_STRUCTURED") == "1":
            class JSONFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    dt = datetime.now().astimezone()
                    t = dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")[:-3]
                    payload = {
                        "time": t,
                        "level": record.levelname,
                        "name": record.name,
                        "function": record.funcName,
                        "line": record.lineno,
                        "message": record.getMessage(),
                    }
                    return json.dumps(payload, ensure_ascii=True)
            fh = logging.FileHandler(log_file)
            fh.setFormatter(JSONFormatter())
            logger.addHandler(fh)
        else:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
                                             datefmt="%Y-%m-%dT%H:%M:%S.%f%z"))
            logger.addHandler(fh)
    return logger


log = setup_logger()


def get_current_branch() -> str:
    try:
        out = subprocess.check_output(["git", "symbolic-ref", "--short", "HEAD"], stderr=subprocess.STDOUT)
        return out.decode("utf-8").strip()
    except Exception as exc:
        log.error(f"Unable to determine current branch: {exc}")
        sys.exit(1)


def main() -> int:
    branch = get_current_branch()

    # Allow main/master branches (protected branches)
    if branch in ["main", "master"]:
        log.info(f"Branch '{branch}' is a protected branch (exempt from naming convention)")
        return 0

    pattern = re.compile(r"^(feat|fix|chore|docs|test|refactor|hotfix|release)/([A-Z]{2,5}-[0-9]+|no-ref)/[a-z0-9]+(-[a-z0-9]+)*$")

    if not pattern.match(branch):
        log.error(f"Branch name '{branch}' does not follow the required convention.")
        log.info("Expected format: <type>/<issue-ref>/<short-description>")
        log.info("Examples:")
        log.info("  feat/PROJ-123/add-oauth-login")
        log.info("  fix/SEC-456/sql-injection-filter")
        log.info("  feat/ENG-789/new-dashboard")
        log.info("  hotfix/no-ref/urgent-rollback")
        return 1

    log.info(f"Branch name '{branch}' is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

