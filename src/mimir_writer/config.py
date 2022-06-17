#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utilities to construct Mimir configuration."""

MIMIR_PORT = 9009
MIMIR_PUSH_PATH = "/api/v1/push"
MIMIR_CONFIG_FILE = "/etc/mimir/config.yaml"

MIMIR_DIRS = {
    "bucket_store": "/tmp/mimir/tsdb-sync",
    "data": "/tmp/mimir/data/tsdb",
    "tsdb": "/tmp/mimir/tsdb",
    "compactor": "/tmp/mimir/compactor",
    "rules": "/tmp/mimir/rules",
    "data-alertmanager": "/tmp/mimir/data-alertmanager",
    "tenant-rules": "/tmp/mimir/rules/anonymous",
}


def block_storage_config(s3_config, retention_period):
    """Mimir Blocks Storage configuration."""
    cfg = {
        "bucket_store": {"sync_dir": MIMIR_DIRS["bucket_store"]},
        "tsdb": {"dir": MIMIR_DIRS["tsdb"], "retention_period": retention_period},
    }

    if s3_config:
        cfg["backend"] = "s3"
        cfg["s3"] = s3_config
    else:
        cfg["backend"] = "filesystem"
        cfg["filesystem"] = {"dir": MIMIR_DIRS["data"]}

    return cfg


def compactor_config():
    """Mimir Compactor configuration."""
    cfg = {
        "data_dir": MIMIR_DIRS["compactor"],
        "sharding_ring": {"kvstore": {"store": "memberlist"}},
    }

    return cfg


def distributor_config():
    """Mimir Distributor configuration."""
    cfg = {"ring": {"instance_addr": "127.0.0.1", "kvstore": {"store": "memberlist"}}}

    return cfg


def ingester_config():
    """Mimir Ingestor configuration."""
    cfg = {
        "ring": {
            "instance_addr": "127.0.0.1",
            "kvstore": {
                "store": "memberlist",
            },
            "replication_factor": 1,
        }
    }

    return cfg


def ruler_config():
    """Mimir Ruler configuration."""
    cfg = {"alertmanager_url": f"http://localhost:{MIMIR_PORT}/alertmanager"}

    return cfg


def ruler_storage_config():
    """Mimir Ruler Storage configuration."""
    cfg = {"backend": "filesystem", "filesystem": {"dir": MIMIR_DIRS["rules"]}}

    return cfg


def server_config():
    """Mimir Server configuration."""
    cfg = {"http_listen_port": MIMIR_PORT, "log_level": "error"}

    return cfg


def store_gateway_config():
    """Mimir Store Gateway configuration."""
    cfg = {"sharding_ring": {"replication_factor": 1}}

    return cfg


def alertmanager_storage_config():
    """Mimir Alertmanager Storage configuration."""
    cfg = {
        "backend": "filesystem",
        "filesystem": {"dir": MIMIR_DIRS["data-alertmanager"]},
    }

    return cfg


def memberlist_config(nodename, peers):
    """Mimir Member List configuration.

    Each member of a Mimir cluster needs to set its own "memberlist".
    Members in this cluster are part of a replica set.

    Args:
        nodename: a string name for this memberlist node.
        peers: a list of dictionaries providing the set of members
            which are part of the current Mimir cluster. Each dictionary
            in this list has as its values the hostnames of the memberlist.
            The keys are typical the node names.
    """
    cfg = {"node_name": nodename, "join_members": list(peers.values())}

    return cfg
