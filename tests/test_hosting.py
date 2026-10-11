import logging
import unittest
from unittest.mock import Mock

from hosting import ManagedProcess


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
