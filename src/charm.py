#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Mimir Writer Charm.

Mimir Writer ingests metrics and stores it into long term object storage.
This charm deploys the write pathway of Mimir.
"""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)


class MimirWriterCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(MimirWriterCharm)
