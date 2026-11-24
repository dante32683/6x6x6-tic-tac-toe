"""Atomic JSON writes: a reader (or a crash mid-write) sees the old complete
file or the new complete file, never a truncated one. Also the data file the
gen/ tools read and write: data6.json, or data5.json with CUBE_N=5."""
import json, os, tempfile

N = int(os.environ.get("CUBE_N", "6"))
DATA = f"data{N}.json"

def dump(obj, path):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
