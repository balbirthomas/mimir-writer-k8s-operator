#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Mimir Writer Charm.

Mimir Writer ingests metrics and stores it into long term object storage.
This charm deploys the write pathway of Mimir.
"""

import logging
import socket
import yaml

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus

from mimir_writer.config import (
    MIMIR_CONFIG_FILE,
    MIMIR_DIRS,
    block_storage_config,
    compactor_config,
    distributor_config,
    ingester_config,
    memberlist_config,
    server_config,
    store_gateway_config,
)

logger = logging.getLogger(__name__)


class MimirWriterCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self._name = "mimir-writer"
        self._peername = "mimir-writer-peers"

        # charm lifecycle event handlers
        self.framework.observe(self.on.mimir_writer_pebble_ready, self._on_mimir_writer_pebble_ready)

    def _on_mimir_writer_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        When a new Mimir writer workload container starts the,
        all required Mimir directories are created, a new Mimir
        config file is created and then the Mimir workload is
        started.
        """
        self._create_mimir_dirs()
        self._set_mimir_config()

        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        targets = "distributor,ingester,compactor,store-gateway,purger"
        pebble_layer = {
            "summary": "mimir layer",
            "description": "pebble config layer for mimir",
            "services": {
                self._name: {
                    "override": "replace",
                    "summary": self._name,
                    "command": f"mimir -target={targets} --config.file {MIMIR_CONFIG_FILE}",
                    "startup": "enabled",
                }
            },
        }
        # Add initial Pebble config layer using the Pebble API
        container.add_layer(self._name, pebble_layer, combine=True)
        container.start(self._name)
        self.unit.status = ActiveStatus()

    def _restart_mimir(self):
        """Restart Mimir workload."""
        container = self.unit.get_container(self._name)

        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return False

        container.stop(self._name)
        container.start(self._name)
        self.unit.status = ActiveStatus()

        return True

    def _set_mimir_config(self):
        """Generate and set a Mimir workload configuration."""
        container = self.unit.get_container(self._name)

        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return False

        # push mimr config file to workload
        mimir_config = self._mimir_config()
        container.push(MIMIR_CONFIG_FILE, mimir_config, make_dirs=True)
        logger.info("Set new Mimir configuration")

        return True

    def _create_mimir_dirs(self):
        """Create Mimir directories.

        The Mimir writer workload requires many directories to be
        present before it is started. These directories are
        used for storing Mimir configuration and metrics blocks
        locally.
        """
        container = self.unit.get_container(self._name)

        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return False

        for _, path in MIMIR_DIRS.items():
            if not container.exists(path):
                container.make_dir(path, make_parents=True)

        return True

    def _mimir_config(self) -> str:
        """Generate a Mimir workload configuration."""
        s3_config = yaml.safe_load(self.config.get("s3", "{}"))
        retention_period = self.config.get("tsdb_block_retention_period", "24h")

        config = {
            "multitenancy_enabled": False,
            "blocks_storage": block_storage_config(s3_config, retention_period),
            "compactor": compactor_config(),
            "distributor": distributor_config(),
            "ingester": ingester_config(),
            "server": server_config(),
            "store_gateway": store_gateway_config(),
            "memberlist": memberlist_config(self.unit.name, self.peers),
        }

        return yaml.dump(config)

    @property
    def hostname(self):
        """Fully qualified hostname of this unit.

        Returns:
            A string given fully qualified hostname of this unit.
        """
        return socket.getfqdn()

    @property
    def peer_relation(self):
        """Fetch the peer relation.

        Returns:
             A :class:`ops.model.Relation` object representing
             the peer relation.
        """
        return self.model.get_relation(self._peername)

    @property
    def peers(self):
        """Fetch all peer names and hostnames.

        Returns:
            A mapping from peer unit names to peer hostnames.
        """
        peers = {}
        peers[self.unit.name] = str(self.hostname)

        if not self.peer_relation:
            # just return self unit if no peers
            return peers

        for unit in self.peer_relation.units:
            if hostname := self.peer_relation.data[unit].get("peer_hostname"):
                peers[unit.name] = hostname

        return peers


if __name__ == "__main__":
    main(MimirWriterCharm)
