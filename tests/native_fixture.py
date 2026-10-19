"""Mocked-native test support; production native paths stay unchanged."""
import contextlib
from pathlib import Path
import tempfile
from unittest import mock

NATIVE_TEMP = '/private/tmp'


@contextlib.contextmanager
def portable_native_temp():
    """Use the real macOS temp root when present; elsewhere redirect only that root for mocked runs."""
    if Path(NATIVE_TEMP).is_dir():
        yield
        return
    original = tempfile.TemporaryDirectory
    host = str(Path(tempfile.gettempdir()).resolve())

    def redirected(*args, dir=None, **kwargs):
        return original(*args, dir=host if str(dir) == NATIVE_TEMP else dir, **kwargs)

    with mock.patch('tempfile.TemporaryDirectory', redirected):
        yield
