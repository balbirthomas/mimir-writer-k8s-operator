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
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from charms.prometheus_k8s.v0.prometheus_remote_write import (
    PrometheusRemoteWriteProvider,
)
from mimir_writer.alertmanager import (
    DEFAULT_ALERT_TEMPLATE,
    DEFAULT_ALERTMANAGER_CONFIG,
    AlertManager,
)
from mimir_writer.config import (
    MIMIR_CONFIG_FILE,
    MIMIR_DIRS,
    MIMIR_PORT,
    MIMIR_PUSH_PATH,
    alertmanager_storage_config,
    block_storage_config,
    compactor_config,
    distributor_config,
    ingester_config,
    ruler_config,
    ruler_storage_config,
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
        self._alertmanager = AlertManager()

        # library objects for managing charm relations
        self.remote_write_provider = PrometheusRemoteWriteProvider(
            self, endpoint_port=MIMIR_PORT, endpoint_path=MIMIR_PUSH_PATH
        )

        # charm lifecycle event handlers
        self.framework.observe(self.on.mimir_writer_pebble_ready, self._on_mimir_writer_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.on.receive_remote_write_relation_changed,
            self._on_remote_write_relation_changed,
        )

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
        targets = "distributor,ingester,compactor,store-gateway,purger,ruler,alertmanager"
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

        self._set_alertmanager_config()
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, _):
        """Handle Mimir configuration change.

        Configuration changes are handled by setting a new Mimir
        and Alertmanager configuration and restarting Mimir. Also
        it is check if replication has been enabled without object
        storage and in this case blocked status is set.
        """
        self._set_mimir_config()
        self._set_alertmanager_config()
        mimir_restarted = self._restart_mimir()

        if mimir_restarted:
            self.unit.status = ActiveStatus()

        if self.app.planned_units() > 1 and not self.config.get("s3", ""):
            self.unit.status = BlockedStatus("Replication requires object storage")

    def _on_remote_write_relation_changed(self, _):
        """Handle change with remote write consumers.

        In response to changes with remote write consumers,
        Mimir's alert rules are updated to the current set of
        alert rules provided by all remote write consumers.
        """
        container = self.unit.get_container(self._name)

        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        alerts_for_all_relations = self.remote_write_provider.alerts()
        for _, alerts in alerts_for_all_relations.items():
            self._set_alert_rules(alerts["groups"])

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
            "ruler": ruler_config(),
            "ruler_storage": ruler_storage_config(),
            "server": server_config(),
            "store_gateway": store_gateway_config(),
            "alertmanager_storage": alertmanager_storage_config(),
            "memberlist": memberlist_config(self.unit.name, self.peers),
        }

        return yaml.dump(config)

    def _set_alertmanager_config(self):
        """Set the Mimir Alertmanager configuration.

        Configuration for Mimir Alertmanager is obtained from
        two charm config options if available. Alternatively
        a dummy default configuration is set. Mimir requires
        a default configuration to start Alertmanager.
        """
        container = self.unit.get_container(self._name)

        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return False

        cfg = self.config["alertmanager_template"] or DEFAULT_ALERT_TEMPLATE
        tpl = self.config["alertmanager_config"] or yaml.dump(DEFAULT_ALERTMANAGER_CONFIG)
        aconfig = {
            "template_files": {
                "default_template": cfg,
            },
            "alertmanager_config": tpl,
        }
        self._alertmanager.set_config(aconfig)

        return True

    def _set_alert_rules(self, groups):
        """Set a new alert rule group in Mimir Alertmanager.

        Args:
            groups: a list of alert rule groups. Each item in the list
            is a single alert rule group represent by a dictionary. This
            dictionary should have two top level keys "name" - the name
            of the alert rule group and "rules" - the list of alert rules.
        """
        failed_groups = []
        for group in groups:
            alert_uploaded = self._alertmanager.set_alert_rule_group(group)
            if not alert_uploaded:
                logger.debug("Failed to set alert group %s", group)
                failed_groups.append(group)

        return failed_groups

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
