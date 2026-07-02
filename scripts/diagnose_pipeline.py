"""
RAWRS pipeline crash diagnostic.

Runs the Phase 1 pipeline on a supplied PDF with comprehensive
instrumentation: per-stage timing, memory tracking (psutil), C-level
crash interception (faulthandler), and BaseException propagation logging.

Usage:
    python -u scripts/diagnose_pipeline.py [pdf_path]

The -u flag forces unbuffered stdout so no lines are lost if the process
is killed by the OS before Python's I/O buffers are flushed.

Instrumentation layers:
  1. faulthandler.enable() — intercepts SIGSEGV / Windows access violations
     and prints the Python + C traceback to stderr before the process dies.
     Does NOT fire on Windows TerminateProcess (OOM kill), but the absence
     of a faulthandler traceback combined with abrupt process death is itself
     evidence of an OOM kill.
  2. atexit handler — fires on sys.exit() and normal script return, but NOT
     on segfault or OOM kill.  If you see the atexit log, the process exited
     cleanly.  If you don't, it was killed externally.
  3. psutil — rss (process private bytes) + system free bytes logged at every
     stage boundary and at every fitz.open() call.
  4. Stage monkey-patches — wrap each named stage function so we know exactly
     which stage was the last to RETURN vs. the last to ENTER before death.
  5. fitz.open() monkey-patch — log every PDF open with a sequence number so
     we can correlate a crash with the Nth PDF open, not just "somewhere in
     the pipeline".
  6. BaseException catch — catches MemoryError, SystemExit, KeyboardInterrupt,
     and everything else that escapes except Exception.
"""

import atexit
import faulthandler
import importlib
import os
import sys
import time
import traceback
from pathlib import Path

# Add the project root (parent of this script's directory) to sys.path so
# that 'src.*' imports resolve whether the script is invoked as
# 'python scripts/diagnose_pipeline.py' or 'python -m scripts.diagnose_pipeline'.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── 1. Enable C-level crash interception BEFORE any other import ─────────────
# Must be before any import that could load a C extension, so the fault
# handler is in place before the extension's code runs.
faulthandler.enable(file=sys.stderr, all_threads=True)

# ── 2. Timestamped, always-flushed print ─────────────────────────────────────
_T0 = time.perf_counter()
_PID = os.getpid()


def _log(*args) -> None:
    elapsed = time.perf_counter() - _T0
    line = " ".join(str(a) for a in args)
    print(f"[DIAG +{elapsed:07.3f}s pid={_PID}] {line}", flush=True)


# ── 3. atexit: distinguish clean exit from abrupt kill ───────────────────────
_clean_exit = False


@atexit.register
def _on_atexit() -> None:
    label = "CLEAN EXIT" if _clean_exit else (
        "ABNORMAL EXIT — atexit fired without _clean_exit flag "
        "(unexpected sys.exit / unhandled exception reaching top level)"
    )
    _log(label)
    # If neither this nor the faulthandler fires, the process was OOM-killed
    # by Windows TerminateProcess (uncatchable from Python).


# ── 4. Memory helper ──────────────────────────────────────────────────────────
try:
    import psutil as _psutil
    _proc = _psutil.Process(_PID)

    def _mem() -> str:
        rss = _proc.memory_info().rss / 1_048_576
        avail = _psutil.virtual_memory().available / 1_048_576
        return f"rss={rss:.0f}MB  sys_avail={avail:.0f}MB"
except ImportError:
    def _mem() -> str:  # type: ignore[misc]
        return "(psutil unavailable)"


# ── 5. Per-stage monkey-patch ─────────────────────────────────────────────────
# Wrap every named stage so we log ENTER and RETURN separately.
# If the process dies between ENTER and RETURN for stage X, X is the last
# stage that started but did not finish.
_STAGE_PATCHES = [
    ("parse_pdf",            "src.parser.pdf_parser",              "parse_pdf"),
    ("extract_text",         "src.ocr.extractor",                  "extract_text"),
    ("route_pages",          "src.ocr.router",                     "route_pages"),
    ("detect_structure",     "src.structure.structure_detector",   "detect_structure"),
    ("detect_footnotes",     "src.footnotes.footnote_detector",    "detect_footnotes"),
    ("extract_front_matter", "src.frontmatter.front_matter_extractor", "extract_front_matter"),
    ("extract_tables",       "src.tables.table_extractor",         "extract_tables"),
    ("extract_images",       "src.images.image_extractor",         "extract_images"),
    ("detect_headings",      "src.headings.heading_detector",      "detect_headings"),
    ("build_markdown",       "src.markdown.markdown_builder",      "build_markdown"),
    ("generate_docx",        "src.docx.docx_generator",            "generate_docx"),
    ("validate_document",    "src.validation.validator",           "validate_document"),
]


def _patch_stage(label: str, module_name: str, fn_name: str) -> None:
    mod = importlib.import_module(module_name)
    original = getattr(mod, fn_name)

    def _wrapped(*args, **kwargs):
        _log(f"ENTER  [{label}]  {_mem()}")
        t0 = time.perf_counter()
        try:
            result = original(*args, **kwargs)
            _log(f"RETURN [{label}]  {time.perf_counter() - t0:.3f}s  {_mem()}")
            return result
        except BaseException as exc:
            _log(f"RAISED [{label}]  {type(exc).__name__}: {exc}")
            _log(traceback.format_exc())
            raise

    setattr(mod, fn_name, _wrapped)


# ── 6. fitz.open() intercept ─────────────────────────────────────────────────
# Track every PDF open call with a sequence number and memory snapshot.
# A crash between "fitz.open #N ENTER" and "fitz.open #N RETURN" means the
# crash is inside libmupdf's document-open path for that specific open.
_fitz_open_seq = 0

try:
    import fitz as _fitz
    _original_fitz_open = _fitz.open

    def _patched_open(filename=None, *args, **kwargs):
        global _fitz_open_seq
        _fitz_open_seq += 1
        seq = _fitz_open_seq
        _log(f"  fitz.open #{seq} ENTER  '{filename}'  {_mem()}")
        t0 = time.perf_counter()
        try:
            doc = _original_fitz_open(filename, *args, **kwargs)
            _log(f"  fitz.open #{seq} RETURN  {time.perf_counter() - t0:.3f}s"
                 f"  pages={doc.page_count}  {_mem()}")
            return doc
        except BaseException as exc:
            _log(f"  fitz.open #{seq} RAISED  {type(exc).__name__}: {exc}")
            raise

    _fitz.open = _patched_open
    _fitz.Document = _patched_open  # fitz.Document() is an alias for fitz.open()
except Exception as e:
    _log(f"WARNING: could not patch fitz.open: {e}")


# ── 7. Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    global _clean_exit

    pdf_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1
        else Path("outputs/uploads/e8cdf30ca8e940ac8b4c96393f7297ed.pdf")
    )

    _log("=" * 72)
    _log("RAWRS PIPELINE CRASH DIAGNOSTIC")
    _log(f"PDF  : {pdf_path}")
    _log(f"Size : {pdf_path.stat().st_size / 1_048_576:.2f} MB" if pdf_path.exists() else "SIZE : FILE NOT FOUND")
    _log(f"PID  : {_PID}")
    _log(f"Python : {sys.version.split()[0]}  {sys.platform}")
    _log(f"Memory at start: {_mem()}")
    _log("faulthandler : ENABLED  (C crash -> stderr traceback)")
    _log("atexit       : REGISTERED  (fires on clean exit only)")
    _log("=" * 72)

    if not pdf_path.exists():
        _log("ERROR: PDF file not found. Pass a valid path as argv[1].")
        sys.exit(1)

    # Apply stage patches
    _log("")
    _log("Patching pipeline stage functions...")
    for label, mod_name, fn_name in _STAGE_PATCHES:
        try:
            _patch_stage(label, mod_name, fn_name)
            _log(f"  OK  {label}  ({mod_name}.{fn_name})")
        except Exception as e:
            _log(f"  WARN  could not patch {label}: {e}")

    _log("")
    _log("Starting run_pipeline(enable_ocr=False) ...")
    _log(f"Memory before run_pipeline: {_mem()}")
    t_total = time.perf_counter()

    try:
        from src.pipeline.phase1_pipeline import run_pipeline
        result = run_pipeline(str(pdf_path), enable_ocr=False)
        elapsed = time.perf_counter() - t_total

        _log("")
        _log(f"run_pipeline() RETURNED after {elapsed:.2f}s")
        _log(f"  result.success       = {result.success}")
        _log(f"  result.status        = {result.status}")
        _log(f"  result.failed_stage  = {result.failed_stage}")
        _log(f"  result.error_message = {result.error_message}")
        _log(f"  result.markdown_path = {result.markdown_path}")
        _log(f"  result.docx_path     = {result.docx_path}")
        _log(f"  fitz.open calls      = {_fitz_open_seq}")
        _log(f"Memory after run_pipeline: {_mem()}")

    except SystemExit as exc:
        _log(f"run_pipeline() triggered SystemExit({exc.code}) after "
             f"{time.perf_counter() - t_total:.2f}s")
    except BaseException as exc:
        _log(f"run_pipeline() raised {type(exc).__name__} after "
             f"{time.perf_counter() - t_total:.2f}s")
        _log(traceback.format_exc())

    _log("")
    _log("Diagnostic complete.")
    _clean_exit = True


if __name__ == "__main__":
    main()
