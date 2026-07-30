from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from gradio_client import Client

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import render_legadia_hf as pipeline

WORK = pipeline.WORK


def iter_values(value: Any):
    if isinstance(value, dict):
        for nested in value.values():
            yield from iter_values(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from iter_values(nested)
    else:
        yield value


def materialize_video(value: Any, target: Path) -> Path | None:
    for item in iter_values(value):
        if not isinstance(item, str):
            continue
        local = Path(item)
        if local.exists() and local.suffix.lower() == ".mp4":
            shutil.copy2(local, target)
            return target
        if item.startswith("http") and ".mp4" in item.lower():
            request = Request(item, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=180) as response, target.open("wb") as output:
                shutil.copyfileobj(response, output)
            if target.exists() and target.stat().st_size > 10000:
                return target
    return None


def call_wan(prompt: str) -> Path:
    client = Client("Wan-AI/Wan2.1")
    start_errors: list[str] = []
    task_id = None

    for route in ("/t2v_generation_async", "/predict"):
        try:
            print("Wan2.1 start route:", route, flush=True)
            result = client.predict(prompt, "1280*720", False, 246801, api_name=route)
            if isinstance(result, (list, tuple)) and result:
                task_id = result[0]
            elif isinstance(result, str):
                task_id = result
            if task_id:
                break
            start_errors.append(f"No task id using {route}: {result!r}")
        except Exception as exc:
            start_errors.append(f"{route}: {type(exc).__name__}: {exc}")

    if not task_id:
        raise RuntimeError("Wan2.1 could not start:\n" + "\n".join(start_errors))

    print("Wan2.1 task:", task_id, flush=True)
    target = WORK / "wan21_base.mp4"
    deadline = time.time() + 2700
    status_flag = False
    poll_errors: list[str] = []

    while time.time() < deadline:
        for route in ("/status_refresh",):
            try:
                result = client.predict(task_id, "t2v", status_flag, api_name=route)
                video = materialize_video(result, target)
                if video:
                    print("Wan2.1 video downloaded:", video, video.stat().st_size, flush=True)
                    return video
                print("Wan2.1 pending...", str(result)[:500], flush=True)
            except Exception as exc:
                poll_errors.append(f"{route}: {type(exc).__name__}: {exc}")
                print("Wan2.1 poll error:", poll_errors[-1], flush=True)
        time.sleep(25)

    raise RuntimeError(
        "Wan2.1 task timed out. task_id=" + str(task_id) + "\n" + "\n".join(poll_errors[-10:])
    )


pipeline.call_cogvideox = call_wan

if __name__ == "__main__":
    sys.exit(pipeline.main())
