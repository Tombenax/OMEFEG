"""RAM tracker for OMEFEG chunk streaming.

Launches the game as a child process and samples its RAM usage while you
fly around, so you can verify that only square(RENDER_DISTANCE+1) chunks
stay in RAM and the rest spill to per-chunk save files.

Usage:
    python tst.py                    # launch OMEFEG.py, sample every 1s
    python tst.py --interval 0.5     # sample twice per second
    python tst.py --log my_log.csv   # custom CSV path
    python tst.py --cmd "python OMEFEG.py"   # custom launch command
    python tst.py --target other.py  # launch a different script instead

How to verify:
    1. Run: python tst.py
    2. Click through the menu to start (new) world.
    3. Press F to fly, hold W (CTRL = sprint, F = fly speed 30).
    4. Fly far in one direction for 1-2 minutes.
    5. Watch this console: RSS should plateau, "saved chunks" should grow.
    6. Close the game -> you get a START / PEAK / END summary + verdict.

No third-party deps required. Uses psutil if installed (more accurate,
includes child processes), otherwise falls back to Windows `tasklist`.
"""

import argparse
import csv
import os
import subprocess
import sys
import time

GAME_DIR = os.path.dirname(os.path.abspath(__file__))


def save_dir():
    """Mirror utils._save_dir() without importing the game (glfw!)."""
    if hasattr(sys, "getandroidapilevel"):
        base = os.environ.get("ANDROID_PRIVATE") or os.getcwd()
        d = os.path.abspath(os.path.join(base, os.pardir, "OMEFEG"))
    else:
        homedir = os.path.expanduser("~")
        d = os.path.join(homedir, "AppData", "Roaming", "OMEFEG")
    return d


def count_saved_chunks():
    """Number of per-chunk files on disk (proof of unload+save)."""
    chunk_dir = os.path.join(save_dir(), "chunks")
    try:
        return sum(
            1
            for name in os.listdir(chunk_dir)
            if name.startswith("chunk_") and name.endswith(".bin")
        )
    except OSError:
        return 0


def rss_tasklist(pid):
    """RSS in MB via Windows tasklist (fallback when psutil missing)."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    # Row looks like: "python.exe","1234","Console","1","12,345 K"
    for line in out.splitlines():
        line = line.strip()
        if not line or "No tasks" in line or "INFO:" in line:
            continue
        parts = [p.strip('" ') for p in line.split('","')]
        if not parts:
            continue
        mem = parts[-1].replace('"', "").strip()  # e.g. '12,345 K' / '10.788 K'
        try:
            import re as _re
            # Tasklist prints integer KB with locale thousands separators
            # (',' on EN, '.' on e.g. DE, space elsewhere): keep digits only.
            digits = _re.sub(r"[^\d]", "", mem)
            if not digits:
                continue
            return float(digits) / 1024.0
        except ValueError:
            continue
    return None


def make_sampler(pid):
    """Return a rss_mb() sampler, preferring psutil, else tasklist."""
    try:
        import psutil  # type: ignore

        proc = psutil.Process(pid)

        def _sample():
            try:
                total = proc.memory_info().rss
                try:
                    for child in proc.children(recursive=True):
                        try:
                            total += child.memory_info().rss
                        except Exception:
                            pass
                except Exception:
                    pass
                return total / (1024.0 * 1024.0)
            except Exception:
                return None

        _sample.backend = "psutil"
        return _sample
    except ImportError:
        pass

    def _sample():
        return rss_tasklist(pid)

    _sample.backend = "tasklist"
    return _sample


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between RAM samples (default 1.0)")
    p.add_argument("--log", default="ram_log.csv",
                   help="CSV log path (default ram_log.csv, '' to disable)")
    p.add_argument("--target", default="OMEFEG.py",
                   help="game script to launch (default OMEFEG.py)")
    p.add_argument("--cmd", default=None,
                   help='full shell command to launch instead, e.g. --cmd "python OMEFEG.py"')
    p.add_argument("--peak-warn-mb", type=float, default=400.0,
                   help="warn if peak exceeds start by more than this (default 400 MB)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    interval = max(0.2, args.interval)

    if args.cmd:
        cmd = args.cmd
        shell = True
    else:
        target = args.target
        if not os.path.isabs(target):
            target = os.path.join(GAME_DIR, target)
        if not os.path.isfile(target):
            print("Target not found: %s" % target)
            return 2
        cmd = [sys.executable, target]
        shell = False

    print("=" * 64)
    print("OMEFEG RAM tracker")
    print("=" * 64)
    print("Launching : %s" % (cmd if isinstance(cmd, str) else " ".join(cmd)))
    print("Sample    : every %.1fs (%s backend, see below)" % (interval, "psutil/tasklist"))
    print()
    print("In the game:")
    print("  1. Click through the menu to start a world.")
    print("  2. Press F to fly, hold W to fly forward (CTRL = sprint).")
    print("  3. Fly far in ONE direction for 1-2 minutes.")
    print("  4. Watch RAM below: it should PLATEAU, saved-chunks grow.")
    print("Close the game window (or Ctrl+C here) to see the verdict.")
    print("-" * 64)

    try:
        proc = subprocess.Popen(cmd, cwd=GAME_DIR, shell=shell)
    except OSError as e:
        print("Failed to launch game: %s" % e)
        return 2

    sampler = make_sampler(proc.pid)
    print("RAM backend: %s (game pid %d)" % (sampler.backend, proc.pid))
    if sampler.backend == "tasklist":
        print("Tip: pip install psutil for more accurate readings.")
    print("-" * 64)

    log_path = args.log.strip() if args.log else ""
    if log_path and not os.path.isabs(log_path):
        log_path = os.path.join(GAME_DIR, log_path)
    csv_file = None
    csv_writer = None
    if log_path:
        try:
            csv_file = open(log_path, "w", newline="")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["t_s", "rss_mb", "peak_mb", "saved_chunks"])
            print("Logging to: %s" % log_path)
        except OSError as e:
            print("Cannot open log file (%s), continuing without it." % e)
            csv_file, csv_writer = None, None

    t0 = time.time()
    start_mb = None
    peak_mb = 0.0
    last_mb = None
    samples = 0

    try:
        while proc.poll() is None:
            time.sleep(interval)
            rss = sampler()
            if rss is None:
                # Process likely exiting; break out to summary.
                if proc.poll() is not None:
                    break
                continue
            if start_mb is None:
                start_mb = rss
            peak_mb = max(peak_mb, rss)
            last_mb = rss
            samples += 1
            elapsed = time.time() - t0
            chunks = count_saved_chunks()
            print("[%6.1fs] RAM: %8.1f MB  (peak %8.1f MB, start %8.1f MB)  saved chunks: %d"
                  % (elapsed, rss, peak_mb, start_mb, chunks))
            if csv_writer is not None:
                csv_writer.writerow(["%.1f" % elapsed, "%.1f" % rss,
                                     "%.1f" % peak_mb, chunks])
                csv_file.flush()
    except KeyboardInterrupt:
        print("\nCtrl+C: stopping tracker, terminating game...")
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # Game closed on its own (or we killed it): final sample if possible.
    rc = proc.poll()
    if last_mb is None:
        last_mb = sampler() or 0.0
    if start_mb is None:
        start_mb = last_mb
    peak_mb = max(peak_mb, last_mb)
    total_t = time.time() - t0

    print("-" * 64)
    print("Game exited (return code %s) after %.1fs, %d samples."
          % (rc, total_t, samples))
    print("START: %.1f MB   PEAK: %.1f MB   END: %.1f MB   GROWTH: %+.1f MB"
          % (start_mb, peak_mb, last_mb, last_mb - start_mb))
    print("Saved chunk files on disk: %d" % count_saved_chunks())
    if log_path and csv_file is not None:
        print("Full log: %s" % log_path)
    if peak_mb - start_mb <= args.peak_warn_mb:
        print("OK: RAM stayed bounded while flying "
              "(peak-start %.1f MB <= %.0f MB). Chunk streaming works."
              % (peak_mb - start_mb, args.peak_warn_mb))
    else:
        print("WARNING: RAM grew %.1f MB (> %.0f MB). "
              "Chunks may be leaking into RAM instead of spilling to disk."
              % (peak_mb - start_mb, args.peak_warn_mb))
    print("=" * 64)

    if csv_file is not None:
        try:
            csv_file.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
