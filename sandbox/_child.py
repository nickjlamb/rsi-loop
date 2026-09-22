"""The process that actually runs a candidate. Invoked by runner.py as

    python -I _child.py <workdir>

and never imported by anything. Reads <workdir>/frames.json (landmarks only),
imports <workdir>/candidate.py, calls candidate.assess on every frame, and
writes <workdir>/results.json. All file handles the harness needs are opened
BEFORE the audit hook is installed; after that, every open/import/os/socket/
subprocess event raised by anything in this process is logged and denied.
"""

import json
import sys
import time
import traceback

# --- limits (set before anything else allocates) --------------------------
try:
    import resource
    _mb = int(sys.argv[2]) if len(sys.argv) > 2 else 512
    _bytes = _mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_bytes, _bytes))
    except (ValueError, OSError):
        pass  # macOS does not honour RLIMIT_AS; the wall-clock limit still applies
except ImportError:
    pass

workdir = sys.argv[1]
sys.path.insert(0, workdir)                       # -I removed it; we add exactly one directory
sys.dont_write_bytecode = True

# --- pre-load everything the whitelist permits, so lazy stdlib imports never trip the hook
import math  # noqa: E402,F401
import typing  # noqa: E402,F401
import dataclasses  # noqa: E402,F401
import statistics  # noqa: E402,F401
import policy.contract  # noqa: E402,F401  (a stub package the runner placed in workdir)
import contract  # noqa: E402,F401

with open(f"{workdir}/frames.json") as fh:
    frames = json.load(fh)
out = open(f"{workdir}/results.json", "w")        # kept open; written at the end

ALLOWED_ROOTS = {"math", "typing", "dataclasses", "statistics", "__future__", "policy", "contract", "candidate"}
CANDIDATE_PATH = f"{workdir}/candidate.py"
DENIED_EVENTS = {"open", "os.system", "os.exec", "os.spawn", "os.fork", "os.posix_spawn", "os.listdir",
                 "os.scandir", "os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.chdir", "os.chmod",
                 "os.putenv", "os.unsetenv", "os.kill", "os.truncate", "shutil.rmtree", "shutil.copyfile",
                 "shutil.move", "socket.__new__", "socket.connect", "socket.bind", "socket.gethostbyname",
                 "socket.getaddrinfo", "subprocess.Popen", "ctypes.dlopen", "ctypes.dlsym", "sys._getframe",
                 "sys.setprofile", "sys.settrace", "sys.addaudithook", "pickle.find_class", "marshal.loads",
                 "code.__new__", "function.__new__",
                 "builtins.input", "builtins.breakpoint", "gc.get_objects", "gc.get_referrers", "webbrowser.open"}
LOGGED_ONLY = {"exec", "compile", "object.__setattr__", "object.__delattr__"}
# exec/compile: dataclasses uses them legitimately and the AST guard forbids naming them.
# object.__setattr__: fired by any attribute set on a class, which dataclasses does; harmless in-process.

events = []
armed = {"on": True}


def _hook(event, args):
    if not armed["on"]:
        return
    if event == "import":
        name = str(args[0])
        if name.split(".")[0] not in ALLOWED_ROOTS or (name.startswith("policy.") and name != "policy.contract"):
            events.append({"kind": "denied", "event": "import", "detail": name, "t": time.time()})
            raise ImportError(f"sandbox: import of {name!r} denied")
        return
    # The import system itself must be able to find and read candidate.py in workdir.
    if event == "open" and args and args[1] in (None, "r", "rb"):
        path = str(args[0])
        if path == CANDIDATE_PATH or path.startswith(f"{workdir}/__pycache__/"):
            return          # the import system reading candidate.py or probing for its .pyc
    if event in ("os.listdir", "os.scandir") and args and str(args[0]) in (workdir, workdir + "/"):
        return
    if event in DENIED_EVENTS or event.startswith(("socket.", "subprocess.", "ctypes.", "os.")):
        detail = repr(args[0])[:200] if args else ""
        events.append({"kind": "denied", "event": event, "detail": detail, "t": time.time()})
        raise PermissionError(f"sandbox: {event} denied")
    if event in LOGGED_ONLY:
        events.append({"kind": "logged", "event": event, "detail": "", "t": time.time()})


sys.addaudithook(_hook)

result = {"loaded": False, "load_error": None, "predictions": [], "metrics": [], "errors": [],
          "events": events, "n_frames": len(frames), "elapsed_s": None}
t0 = time.time()
try:
    import candidate  # noqa: E402
    assess = candidate.assess
    result["loaded"] = True
except BaseException as e:  # noqa: BLE001  (denials arrive as ImportError/PermissionError)
    result["load_error"] = f"{type(e).__name__}: {e}"
    armed["on"] = False                   # traceback formatting opens source files
    result["traceback"] = traceback.format_exc()[-2000:]
    armed["on"] = True

if result["loaded"]:
    for i, lm in enumerate(frames):
        try:
            r = assess(lm)
            label = r["label"] if isinstance(r, dict) else r.label
            if label not in ("Safe", "High Strain"):
                raise ValueError(f"invalid label {label!r}")
            fh_m = r.get("forward_head_metric") if isinstance(r, dict) else getattr(r, "forward_head_metric", None)
            wr_m = r.get("wrist_deviation_metric") if isinstance(r, dict) else getattr(r, "wrist_deviation_metric", None)
            result["predictions"].append(label)
            result["metrics"].append([fh_m if isinstance(fh_m, (int, float)) else None,
                                      wr_m if isinstance(wr_m, (int, float)) else None])
        except BaseException as e:  # noqa: BLE001
            result["predictions"].append(None)
            result["metrics"].append([None, None])
            if len(result["errors"]) < 50:
                result["errors"].append({"i": i, "type": type(e).__name__, "msg": str(e)[:300]})
            else:
                result["errors_truncated"] = True

result["elapsed_s"] = round(time.time() - t0, 4)
armed["on"] = False
json.dump(result, out)
out.close()
