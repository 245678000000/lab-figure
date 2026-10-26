"""Cooperative job cancellation, including owned subprocess trees and HTTP requests."""
import asyncio
import contextlib
import os
import signal
import subprocess
import threading
import time

import httpx

local = threading.local()


class Cancelled(Exception):
    pass


@contextlib.contextmanager
def scope(event, emit=None):
    local.event, local.emit = event, emit
    try:
        check()
        yield
    finally:
        local.event = local.emit = None


def check():
    event = getattr(local, 'event', None)
    if event and event.is_set():
        raise Cancelled('任务已停止，上一张成功图片和编辑草稿已保留。')


def stage(message, name):
    check()
    emit = getattr(local, 'emit', None)
    if emit:
        emit(message, name)


def stop_tree(proc):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if proc.poll() is None:
        proc.kill()


def run(args, *, input=None, timeout=120, **kwargs):
    check()
    # Keep subprocess.run-compatible inputs, while retaining ownership for cancellation.
    kwargs.pop('capture_output', None)
    if os.name != 'nt':
        kwargs['start_new_session'] = True
    proc = subprocess.Popen(args, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    started = time.monotonic()
    first = True
    try:
        while True:
            check()
            if time.monotonic() - started >= timeout:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                out, err = proc.communicate(input=input if first else None, timeout=.2)
                check()
                return subprocess.CompletedProcess(args, proc.returncode, out, err)
            except subprocess.TimeoutExpired:
                first = False
    except BaseException:
        stop_tree(proc)
        proc.communicate(timeout=10)
        raise


def post(url, **kwargs):
    event = getattr(local, 'event', None)
    # Existing non-job connection tests keep their simple synchronous transport.
    if event is None:
        with httpx.Client(timeout=100, trust_env=False) as client:
            return client.post(url, **kwargs)

    async def request():
        async with httpx.AsyncClient(timeout=100, trust_env=False) as client:
            pending = asyncio.create_task(client.post(url, **kwargs))
            try:
                while not pending.done():
                    if event.is_set():
                        raise Cancelled('模型请求已停止，上一张图片已保留。')
                    await asyncio.wait({pending}, timeout=.15)
                check()
                return await pending
            finally:
                if not pending.done():
                    pending.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pending
    return asyncio.run(request())
