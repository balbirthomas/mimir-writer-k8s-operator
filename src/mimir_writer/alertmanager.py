#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A interface to the Mimir Alertmanager API."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import yaml

from .config import MIMIR_PORT

logger = logging.getLogger(__name__)

DEFAULT_ALERT_TEMPLATE = r"""|
    {{ define "__alertmanager" }}AlertManager{{ end }}
    {{ define "__alertmanagerURL" }}{{ .ExternalURL }}/#/alerts?receiver={{ .Receiver | urlquery }}{{ end }}
"""

DEFAULT_ALERTMANAGER_CONFIG = {
    "global": {"http_config": {"tls_config": {"insecure_skip_verify": True}}},
    "templates": ["default_template"],
    "route": {
        "group_wait": "30s",
        "group_interval": "5m",
        "repeat_interval": "1h",
        "receiver": "dummy",
    },
    "receivers": [{"name": "dummy", "webhook_configs": [{"url": "http://127.0.0.1:5001/"}]}],
}


class AlertManager:
    """A Mimir Alertmanger."""

    def __init__(self, host="localhost", tenant="anonymous", timeout=10):
        """Construct and Mimir Alertmanager object.

        Args:
            host: string hostname or address of Alertmager which this
                object must interface with.
            tenant: string tenant ID of Mimir Alertmanager.
            timeout: default timeout in seconds for API requests.
        """
        self._tenant = tenant
        self._host = host
        self._timeout = timeout
        self._base_url = f"http://{self._host}:{MIMIR_PORT}"

    def set_config(self, config) -> str:
        """Set and Mimir Alertmanger configuration.

        Args:
            config: A dictionary representing a valid Mimir Alertmanager
                configuration.
        """
        url = urljoin(self._base_url, "/api/v1/alerts")
        headers = {"Content-Type": "application/yaml"}
        post_data = yaml.dump(config).encode("utf-8")
        response = self._post(url, post_data, headers=headers)

        return response

    def get_alert_rules(self) -> dict:
        """Get all alert rules.

        Returns:
            All alert rules currently set for Mimir Alertmanager. The rules
            are returned as a dictionary. The keys of the dictionary are the
            tenant IDs. The values of this key is a list of alert rule group
            defined for that specific tenant. Each alert rule group in the
            list is itself a dictionary with two keys "name" which is the name
            of the alert rule group and "rules" which is a list of alert rules
            in the group. The list of alert rules is itself a list of dictionaries.
            Each alert rule dictionary contains the alert rule, name, expression,
            labels and annotations.
        """
        url = urljoin(self._base_url, "/prometheus/config/v1/rules")
        response = self._get(url)
        rules = {}
        if response:
            rules = yaml.safe_load(response)

        return rules

    def get_alerts(self) -> dict:
        """Get currently firing alerts.

        Returns:
            All alerts that are currently firing.
        """
        alerts = {}
        url = urljoin(self._base_url, "/prometheus/api/v1/alerts")
        response = self._get(url)

        if response:
            alerts = json.loads(response)

        return alerts

    def set_alert_rule_group(self, group) -> str:
        """Set a new alert rule group.

        Args:
            group: a dictionary representing a single alert rule group.
        """
        url = urljoin(self._base_url, f"/prometheus/config/v1/rules/{self._tenant}")
        headers = {"Content-Type": "application/yaml"}
        post_data = yaml.dump(group).encode("utf-8")
        response = self._post(url, post_data, headers=headers)

        return response

    def delete_alert_rule_group(self, groupname) -> str:
        """Delete an alert rule group.

        Args:
            groupname: a string representing the name of group to be deleted.
        """
        url = urljoin(self._base_url, f"/prometheus/config/v1/rules/{self._tenant}/{groupname}")
        response = self._delete(url)

        return response

    def _get(self, url, headers=None, timeout=None, encoding="utf-8") -> str:
        """Make a HTTP GET request to Mimir Alertmanager."""
        body = ""
        request = Request(url, headers=headers or {}, method="GET")
        timeout = timeout if timeout else self._timeout

        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                charset = response.headers.get_content_charset()
                enc = charset if charset else encoding
                body = body.decode(encoding=enc)
        except HTTPError as error:
            logger.debug(
                "Failed to fetch %s, status: %s, reason: %s",
                url,
                error.status,
                error.reason,
            )
        except URLError as error:
            logger.debug("Invalid URL %s : %s", url, error)
        except TimeoutError:
            logger.debug("Request timeout fetching URL %s", url)

        return body

    def _post(self, url, post_data, headers=None, timeout=None) -> str:
        """Make a HTTP POST request to Mimir Alertmanager."""
        status = ""
        timeout = timeout if timeout else self._timeout
        request = Request(url, headers=headers or {}, data=post_data, method="POST")

        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.status
        except HTTPError as error:
            logger.debug(
                "Failed posting to %s, status: %s, reason: %s",
                url,
                error.status,
                error.reason,
            )
        except URLError as error:
            logger.debug("Invalid URL %s : %s", url, error)
        except TimeoutError:
            logger.debug("Request timeout during posting to URL %s", url)

        return status

    def _delete(self, url, headers=None, timeout=None) -> str:
        """Make a HTTP DELETE request to Mimir Alertmanager."""
        status = ""
        timeout = timeout if timeout else self._timeout
        request = Request(url, headers=headers or {}, method="DELETE")

        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.status
        except HTTPError as error:
            logger.debug(
                "Delete failed %s, status: %s, reason: %s",
                url,
                error.status,
                error.reason,
            )
        except URLError as error:
            logger.debug("Invalid URL %s : %s", url, error)
        except TimeoutError:
            logger.debug("Request timeout deleting %s", url)

        return status
