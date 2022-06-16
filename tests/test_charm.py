# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from charm import MimirWriterCharm
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MimirWriterCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

