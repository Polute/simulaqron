import sys
import threading
from time import perf_counter_ns
# ---------------------------------------
# 0. AUXILIAR TIMESTAMP FUNCTION
# ---------------------------------------
def timestamp_precise():
    """
    Returns a timestamp in MM:SS.xxxxxx format
    with real microsecond precision using perf_counter().
    """
    ns = perf_counter_ns()
    total_sec = ns // 1_000_000_000
    mm = (total_sec // 60) % 60
    ss = total_sec % 60
    usec = (ns % 1_000_000_000) // 1000
    return f"{mm:02d}:{ss:02d}.{usec:06d}"

def timestamp_to_seconds(ts):
    mm, rest = ts.split(":")
    ss, us = rest.split(".")
    return int(mm)*60 + int(ss) + int(us)/1_000_000

def diff_precise(t1, t2):
    """
    Compute difference between two precise timestamps.
    """
    return abs(timestamp_to_seconds(t2) - timestamp_to_seconds(t1))

# ---------------------------------------
# 1. OPEN OUTPUT FILE
# ---------------------------------------
log_file = open("trace_epr.txt", "w")
def timestamp_precise():
    """
    Returns a timestamp in MM:SS.xxxxxx format
    with real microsecond precision using perf_counter().
    """
    ns = perf_counter_ns()
    total_sec = ns // 1_000_000_000
    mm = (total_sec // 60) % 60
    ss = total_sec % 60
    usec = (ns % 1_000_000_000) // 1000
    return f"{mm:02d}:{ss:02d}.{usec:06d}"

def trace_calls(frame, event, arg):
    if event != "call":
        return trace_calls

    filename = frame.f_code.co_filename
    lineno = frame.f_lineno
    funcname = frame.f_code.co_name

    if (
        ("cqc" in filename or "simulaqron" in filename or "virt" in filename or "backend" in filename)
        and "_distutils_hack" not in filename
        and "zope" not in filename
        and "attr" not in filename
        and "twisted" not in filename
        and "anytree" not in filename
    ):
        log_file.write(f"{timestamp_precise()} [CALL] {filename}:{lineno} # {funcname}\n")

    return trace_calls


# ---------------------------------------
# 2. ENABLE TRACING
# ---------------------------------------
sys.settrace(trace_calls)
threading.settrace(trace_calls)


# ---------------------------------------
# 3. IMPORT YOUR CQC CODE
# ---------------------------------------
from cqc.pythonLib import CQCConnection

# ---------------------------------------
# 4. RUN A REAL EPR CREATION TEST
# ---------------------------------------
ts1 = timestamp_precise()
def run():
    with CQCConnection("node_rectorado_upm") as node_rectorado_upm:
        q = node_rectorado_upm.createEPR("node_cedint_upm")

        log_file.write(f"EPR1 created: {q}\n")
        ts2 = timestamp_precise()
        


        log_file.write(f"Time needed:  {diff_precise(ts1,ts2)}\n")

        q = node_rectorado_upm.createEPR("node_cedint_upm")

        log_file.write(f"EPR2 created: {q}\n")
        ts2 = timestamp_precise()
        


        log_file.write(f"Time needed:  {diff_precise(ts1,ts2)}")
    with CQCConnection("node_cedint_upm") as node_cedint_upm:
        q = node_cedint_upm.recvEPR()

        log_file.write(f"EPR1 receive: {q}\n")
        ts2 = timestamp_precise()
        


        log_file.write(f"Time needed:  {diff_precise(ts1,ts2)}\n")

        q = node_cedint_upm.recvEPR()

        log_file.write(f"EPR2 receive: {q}\n")
        ts2 = timestamp_precise()
        


        log_file.write(f"Time needed:  {diff_precise(ts1,ts2)}")

# Run inside a thread (required for settrace)
t = threading.Thread(target=run)
t.start()
t.join()

# ---------------------------------------
# 5. CLOSE LOG FILE
# ---------------------------------------
log_file.close()
