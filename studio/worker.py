"""Runs one Shri Tools task from library\\queue.json (started by server.py with ComfyUI's python).
  python_embeded\\python.exe studio\\worker.py <task_id>
Exit code 0 = done, 1 = failed (the error is in the project's status.json and log.txt), 2 = cancelled."""
import os, sys, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402
from produce import Cancelled, Producer  # noqa: E402


def main(tid):
    task = next((t for t in store.queue() if t["id"] == tid), None)
    if not task:
        print("no such task", tid)
        return 1
    prod = Producer(task)
    try:
        prod.run()
        return 0
    except Cancelled:
        if task.get("project"):
            prod.status(state="cancelled", label="Stopped")
            prod.log("stopped")
        return 2
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, flush=True)
        if task.get("project"):
            prod.log(f"FAILED: {e}")
            prod.status(state="failed", label="Failed", error=str(e)[:800])
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
