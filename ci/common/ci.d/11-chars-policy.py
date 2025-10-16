#!/usr/bin/env python3
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set, Tuple


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
    logger = logging.getLogger("chars-policy")
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
                    t = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S.%f%z")[:-3]
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


def load_yaml_configuration(yaml_path: Path):
    try:
        import yaml  # type: ignore
    except ImportError:
        log.error("PyYAML not available; install with: pip install pyyaml")
        return None
    
    if not yaml_path.exists():
        log.error(f"Config file not found: {yaml_path}")
        return None
        
    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        allowed_pattern = re.compile(data.get(
            "allowed_pattern",
            r"(?u)[^\x00-\x7F\u2500-\u257F\u2580-\u259F\u2190-\u21FF\u25A0-\u25FF]",
        ))
        emoji_pattern = re.compile(data.get(
            "emoji_pattern",
            r"(?u)[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]",
        ))
        include_globs: List[str] = list(data.get("include_globs", []) or [])
        exclude_dirs: Set[str] = set(data.get("exclude_dirs", []) or [])
        return allowed_pattern, emoji_pattern, include_globs, exclude_dirs
    except Exception as e:
        log.error(f"Failed to load YAML config: {e}")
        return None


def should_skip(path: Path, include_globs: List[str], exclude_dirs: Set[str]) -> bool:
    if any(part in exclude_dirs for part in path.parts):
        return True
    if not include_globs:
        return False
    name = path.name
    for pat in include_globs:
        if Path(name).match(pat):
            return False
    return True


def scan_file(path: Path, allowed_pattern, emoji_pattern) -> Tuple[list, list]:
    discouraged_hits = []
    emoji_hits = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                if emoji_pattern.search(line):
                    emoji_hits.append((lineno, line.rstrip("\n")))
                if allowed_pattern.search(line):
                    discouraged_hits.append((lineno, line.rstrip("\n")))
    except Exception:
        return [], []
    return discouraged_hits, emoji_hits


def main() -> int:
    repo_root = Path.cwd()
    yaml_path = Path(__file__).with_suffix(".yaml")

    cfg = load_yaml_configuration(yaml_path)
    if cfg is None:
        log.error("Failed to load character policy configuration")
        return 2

    allowed_pattern, emoji_pattern, include_globs, exclude_dirs = cfg

    discouraged_total = 0
    emoji_total = 0

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            path = Path(root) / fname
            if should_skip(path, include_globs, exclude_dirs):
                continue
            discouraged, emojis = scan_file(path, allowed_pattern, emoji_pattern)
            if discouraged:
                log.warning(f"Discouraged characters in {path}")
                for lineno, line in discouraged:
                    log.info(f"{path}:{lineno}:{line}")
                discouraged_total += len(discouraged)
            if emojis:
                log.warning(f"Disallowed emojis in {path}")
                for lineno, line in emojis:
                    log.info(f"{path}:{lineno}:{line}")
                emoji_total += len(emojis)

    if discouraged_total:
        log.warning(f"Total lines flagged (discouraged): {discouraged_total}")
    else:
        log.info("No discouraged characters found")

    if emoji_total:
        log.warning(f"Total lines flagged (emojis): {emoji_total}")
    else:
        log.info("No emojis detected")

    return 0


if __name__ == "__main__":
    sys.exit(main())


