from __future__ import annotations

import os
import stat
from pathlib import Path


class NonRegularFileError(OSError):
    """Raised when a contract path resolves to a special file."""


class FileTooLargeError(OSError):
    """Raised when a regular file exceeds its configured byte budget."""


def read_regular_file(path: Path, *, max_bytes: int | None) -> bytes:
    """Read a regular file without allowing a special file to block first."""
    if max_bytes is not None and max_bytes < 1:
        raise ValueError("file byte budget must be positive")

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise NonRegularFileError("input must be a regular file")
        if max_bytes is not None and metadata.st_size > max_bytes:
            raise FileTooLargeError("input exceeds the maximum encoded size")

        source = os.fdopen(descriptor, "rb")
        descriptor = -1
        with source:
            encoded = source.read() if max_bytes is None else source.read(max_bytes + 1)
        if max_bytes is not None and len(encoded) > max_bytes:
            raise FileTooLargeError("input exceeds the maximum encoded size")
        return encoded
    finally:
        if descriptor >= 0:
            os.close(descriptor)
