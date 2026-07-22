from __future__ import annotations

import os
import socket
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import external_assets  # noqa: E402


class ExternalAssetNetworkTests(unittest.TestCase):
    def test_validated_socket_resolves_once_and_connects_to_numeric_address(self):
        address = ("93.184.216.34", 443)
        raw_socket = mock.Mock()
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)]

        with mock.patch.object(external_assets.socket, "getaddrinfo", return_value=resolved) as getaddrinfo:
            with mock.patch.object(external_assets.socket, "socket", return_value=raw_socket):
                connected = external_assets._connect_validated_socket(
                    "assets.example",
                    443,
                    timeout=5,
                )

        self.assertIs(raw_socket, connected)
        getaddrinfo.assert_called_once_with("assets.example", 443, type=socket.SOCK_STREAM)
        raw_socket.connect.assert_called_once_with(address)

    def test_validated_socket_rejects_private_dns_answer_before_connecting(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))]

        with mock.patch.object(external_assets.socket, "getaddrinfo", return_value=resolved):
            with mock.patch.object(external_assets.socket, "socket") as socket_factory:
                with self.assertRaisesRegex(ValueError, "non-public"):
                    external_assets._connect_validated_socket("assets.example", 443, timeout=5)

        socket_factory.assert_not_called()

    def test_https_connection_keeps_original_hostname_for_tls(self):
        raw_socket = mock.Mock()
        wrapped_socket = mock.Mock()
        context = mock.Mock()
        context.wrap_socket.return_value = wrapped_socket
        connection = external_assets._ValidatedHTTPSConnection(
            "assets.example",
            443,
            timeout=5,
            context=context,
        )

        with mock.patch.object(external_assets, "_connect_validated_socket", return_value=raw_socket):
            connection.connect()

        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="assets.example")
        self.assertIs(wrapped_socket, connection.sock)


if __name__ == "__main__":
    unittest.main()
