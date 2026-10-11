"""Supervise the local production server and Cloudflare connector.

Secrets stay in a local file and the child environment, never command-line
arguments. Run one supervisor per project; Ctrl+C or stop-request shuts down
both owned process trees. Child output is drained into bounded rotating logs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from importlib import import_module
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import sysconfig
import threading
import time

ROOT = Path(__file__).resolve().parent


def web_command(env):
    # Windows venv's python.exe is a launcher. Use the underlying interpreter
    # directly with this environment's package directory so the monitored PID
    # is the actual server, rather than a parent that can orphan the server.
    executable = sys.executable
    if os.name == 'nt':
        executable = getattr(sys, '_base_executable', sys.executable)
        packages = sysconfig.get_path('purelib')
        env['PYTHONPATH'] = os.pathsep.join(filter(None, [packages, env.get('PYTHONPATH')]))
    return [executable, '-u', str(ROOT / 'web_lilith.py'), '--production']


class ManagedProcess:
    def __init__(self, name, command, logger, *, spawn=subprocess.Popen, env=None):
        self.name, self.command, self.logger = name, command, logger
        self.spawn, self.env = spawn, env
        self.process = None
        self.failures = 0
        self.next_start = 0.0
        self.started = 0.0
        self.stopped = False
        self.reader = None

    def _read_output(self, process):
        try:
            for line in process.stdout:
                self.logger.info('%s: %s', self.name, line.rstrip())
        except (OSError, ValueError):
            self.logger.exception('%s output reader failed', self.name)
        finally:
            process.stdout.close()

    def _retry(self, now):
        self.failures += 1
        self.next_start = now + min(60, 2 ** min(self.failures, 6))

    def tick(self, now):
        if self.stopped:
            return
        if self.process is not None:
            code = self.process.poll()
            if code is None:
                if now - self.started >= 60:
                    self.failures = 0
                return
            self.logger.warning('%s exited with code %s; scheduling restart', self.name, code)
            self.process = None
            self._retry(now)
        if now < self.next_start:
            return
        try:
            self.process = self.spawn(self.command, cwd=ROOT, env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace',
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.started = now
            self.logger.info('%s started, pid=%s', self.name, self.process.pid)
            if self.process.stdout is not None:
                self.reader = threading.Thread(target=self._read_output, args=(self.process,), daemon=True)
                self.reader.start()
        except OSError:
            self.logger.exception('%s could not start', self.name)
            self._retry(now)

    def stop(self):
        self.stopped = True
        if self.process is None:
            return
        if self.process.poll() is None:
            # Windows venv python.exe launches another python process. Stop the
            # complete owned tree so it cannot keep holding the listening port.
            if os.name == 'nt' and isinstance(self.process.pid, int):
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.reader is not None:
            self.reader.join(timeout=2)
        self.process = None


@contextmanager
def supervisor_lock(path):
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'\0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl = import_module('fcntl')
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-host', default='lilith.lil4kh.uk')
    parser.add_argument('--tunnel-name', default='lilith-mira-pc')
    args = parser.parse_args(argv)
    directory = ROOT / '.tunnel'
    directory.mkdir(exist_ok=True)
    logger = logging.getLogger('hosting')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(directory / 'hosting.log', maxBytes=2_000_000, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    env = dict(os.environ, LILITH_PUBLIC_HOST=args.public_host,
               LILITH_WEB_PASSWORD=(directory / 'web-password.txt').read_text(encoding='utf-8').strip())
    if len(env['LILITH_WEB_PASSWORD']) < 20:
        raise ValueError('Hosting password must contain at least 20 characters')
    workers = [ManagedProcess('web', web_command(env), logger, env=env),
               ManagedProcess('tunnel', [str(directory / 'cloudflared.exe'), 'tunnel', '--config',
                                         str(directory / 'config.yml'), 'run', args.tunnel_name], logger)]
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop_file = directory / 'stop-request'
    status_file = directory / 'status.json'
    try:
        with supervisor_lock(directory / 'supervisor.lock'):
            stop_file.unlink(missing_ok=True)
            previous = None
            try:
                while not stop.is_set() and not stop_file.exists():
                    for worker in workers:
                        worker.tick(time.monotonic())
                    status = {'supervisor': os.getpid(), 'workers': {
                        w.name: w.process.pid if w.process is not None else None for w in workers}}
                    if status != previous:
                        temporary = status_file.with_suffix('.tmp')
                        temporary.write_text(json.dumps(status), encoding='utf-8')
                        os.replace(temporary, status_file)
                        previous = status
                    stop.wait(1)
            finally:
                for worker in workers:
                    try:
                        worker.stop()
                    except (OSError, subprocess.TimeoutExpired):
                        logger.exception('%s did not stop cleanly', worker.name)
                status_file.unlink(missing_ok=True)
                stop_file.unlink(missing_ok=True)
    except OSError:
        logger.exception('Supervisor unavailable or already running')
        return 1
    finally:
        logger.removeHandler(handler)
        handler.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
