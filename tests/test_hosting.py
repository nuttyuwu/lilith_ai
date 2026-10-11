import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from hosting import ManagedProcess
import hosting


class HostingTests(unittest.TestCase):
    def test_restarts_with_bounded_backoff_and_resets_when_stable(self):
        children = []
        def spawn(*args, **kwargs):
            child = Mock(stdout=None)
            child.poll.return_value = None
            children.append(child)
            return child
        worker = ManagedProcess('test', ['example'], logging.getLogger('test'), spawn=spawn)
        worker.tick(0)
        self.assertEqual(len(children), 1)
        children[-1].poll.return_value = 1
        worker.tick(1)
        worker.tick(2)
        self.assertEqual(len(children), 1)
        worker.tick(3)
        self.assertEqual(len(children), 2)
        worker.tick(64)
        self.assertEqual(worker.failures, 0)
        children[-1].poll.return_value = 1
        worker.tick(65)
        worker.tick(67)
        self.assertEqual(len(children), 3)

    def test_stop_prevents_restart(self):
        child = Mock(stdout=None)
        child.poll.return_value = None
        worker = ManagedProcess('test', ['example'], logging.getLogger('test'), spawn=Mock(return_value=child))
        worker.tick(0)
        worker.stop()
        worker.tick(100)
        child.terminate.assert_called_once()
        self.assertIsNone(worker.process)

    def test_start_failure_retries_and_delay_is_bounded(self):
        spawn = Mock(side_effect=OSError('test failure'))
        worker = ManagedProcess('test', ['example'], Mock(), spawn=spawn)
        for now in (0, 2, 6, 14, 30, 62, 122, 182):
            worker.tick(now)
        self.assertEqual(spawn.call_count, 8)
        self.assertEqual(worker.next_start, 242)

    def test_windows_server_uses_real_interpreter_and_venv_packages(self):
        env = {'PYTHONPATH': 'existing'}
        with patch.object(hosting.os, 'name', 'nt'), patch.object(hosting.sys, '_base_executable', 'real-python'):
            command = hosting.web_command(env)
        self.assertEqual(command[0], 'real-python')
        self.assertTrue(env['PYTHONPATH'].endswith(os.pathsep + 'existing'))
        self.assertIn('--production', command)

    def test_output_is_drained_and_closed(self):
        from io import StringIO
        output = StringIO('test line\n')
        logger = Mock()
        worker = ManagedProcess('test', [], logger)
        worker._read_output(Mock(stdout=output))
        logger.info.assert_called_once_with('%s: %s', 'test', 'test line')
        self.assertTrue(output.closed)

    def test_supervisor_cleanup_continues_after_worker_shutdown_failure(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tunnel = root / '.tunnel'
            tunnel.mkdir()
            (tunnel / 'web-password.txt').write_text('test-password-long-enough', encoding='utf-8')
            event = Mock()
            event.is_set.side_effect = [False, True]
            first, second = Mock(process=None, name='web'), Mock(process=None, name='tunnel')
            first.name, second.name = 'web', 'tunnel'
            first.stop.side_effect = subprocess.TimeoutExpired('test', 10)
            with patch.object(hosting, 'ROOT', root), patch.object(hosting, 'ManagedProcess', side_effect=[first, second]), patch.object(hosting.threading, 'Event', return_value=event):
                self.assertEqual(hosting.main([]), 0)
            second.stop.assert_called_once()
            self.assertFalse((tunnel / 'status.json').exists())
            self.assertTrue((tunnel / 'hosting.log').exists())

    def test_duplicate_supervisor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lock'
            with hosting.supervisor_lock(path):
                with self.assertRaises(OSError):
                    with hosting.supervisor_lock(path):
                        pass

    def test_production_mode_refuses_missing_waitress_and_debug(self):
        import web_lilith
        with patch.object(web_lilith, 'create_app') as create, patch.dict('os.environ', {'LILITH_PUBLIC_HOST': ''}), patch.dict('sys.modules', {'waitress': None}):
            self.assertEqual(web_lilith.main(['--production']), 2)
            create.assert_not_called()
        with patch.object(web_lilith, 'create_app') as create, patch.dict('os.environ', {'LILITH_PUBLIC_HOST': 'example.test'}):
            self.assertEqual(web_lilith.main(['--debug']), 2)
            create.assert_not_called()
