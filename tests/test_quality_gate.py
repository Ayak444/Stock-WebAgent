import http.client
import os
import socket
import threading
import unittest

from scripts.offline_unittest import network_is_blocked
from scripts.quality_gate import build_test_environment


class OfflineRunnerTests(unittest.TestCase):
    def test_network_is_blocked_before_tests_are_loaded(self):
        self.assertTrue(network_is_blocked())

    def test_tcp_and_dns_attempts_fail(self):
        self.assertTrue(network_is_blocked())
        with self.assertRaises(OSError):
            socket.create_connection(("example.invalid", 443))
        with socket.socket() as client:
            with self.assertRaises(OSError):
                client.connect(("203.0.113.1", 443))
        with self.assertRaises(OSError):
            socket.getaddrinfo("example.invalid", 443)

    def test_http_attempt_fails_and_local_socket_pair_works(self):
        self.assertTrue(network_is_blocked())
        connection = http.client.HTTPConnection("example.invalid", 80)
        with self.assertRaises(OSError):
            connection.connect()
        left, right = socket.socketpair()
        left.close()
        right.close()

    def test_local_create_connection_and_http_are_allowed(self):
        self.assertTrue(network_is_blocked())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)
            with socket.create_connection(listener.getsockname(), timeout=2) as client:
                accepted, _ = listener.accept()
                client.sendall(b"ok")
                self.assertEqual(accepted.recv(2), b"ok")
                accepted.close()
            with socket.create_connection(
                ("localhost", listener.getsockname()[1]),
                timeout=2,
            ) as client:
                accepted, _ = listener.accept()
                client.sendall(b"localhost")
                self.assertEqual(accepted.recv(9), b"localhost")
                accepted.close()
            addresses = socket.getaddrinfo(
                "localhost",
                listener.getsockname()[1],
                type=socket.SOCK_STREAM,
            )
            self.assertTrue(addresses)
            self.assertTrue(
                all(address[-1][0] == "127.0.0.1" for address in addresses)
            )

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)

            def serve_http_once():
                accepted, _ = listener.accept()
                with accepted:
                    accepted.recv(4096)
                    accepted.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                        b"Connection: close\r\n\r\nOK"
                    )

            server_thread = threading.Thread(target=serve_http_once)
            server_thread.start()
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                listener.getsockname()[1],
                timeout=2,
            )
            connection.request("GET", "/")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"OK")
            connection.close()
            server_thread.join(timeout=2)
            self.assertFalse(server_thread.is_alive())

    @unittest.skipUnless(hasattr(socket.socket, "sendmsg"), "sendmsg unavailable")
    def test_sendmsg_blocks_external_udp_and_allows_local_sockets(self):
        self.assertTrue(network_is_blocked())
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            with self.assertRaises(OSError):
                sender.sendmsg([b"blocked"], [], 0, ("192.0.2.1", 9))

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
                receiver.bind(("127.0.0.1", 0))
                receiver.settimeout(2)
                sender.sendmsg([b"local"], [], 0, receiver.getsockname())
                self.assertEqual(receiver.recvfrom(5)[0], b"local")

        if hasattr(socket, "AF_UNIX"):
            left, right = socket.socketpair()
            try:
                left.sendmsg([b"unix"])
                self.assertEqual(right.recv(4), b"unix")
            finally:
                left.close()
                right.close()


class SanitizedEnvironmentTests(unittest.TestCase):
    def test_test_process_does_not_receive_production_credentials(self):
        for credential_name in (
            "GITHUB_TOKEN",
            "GROQ_API_KEY",
            "MAIAGENT_API_KEY",
            "SUPABASE_KEY",
            "SUPABASE_URL",
        ):
            self.assertNotIn(credential_name, os.environ)

    def test_credentials_are_not_forwarded_to_test_process(self):
        source = {
            "PATH": "safe-path",
            "CI": "true",
            "GITHUB_SHA": "abc123",
            "GITHUB_TOKEN": "github-secret",
            "GROQ_API_KEY": "groq-secret",
            "MAIAGENT_API_KEY": "maiagent-secret",
            "SUPABASE_KEY": "supabase-secret",
            "SUPABASE_URL": "https://secret.invalid",
        }

        environment = build_test_environment(source)

        self.assertEqual(environment["PATH"], "safe-path")
        self.assertEqual(environment["CI"], "true")
        self.assertEqual(environment["GITHUB_SHA"], "abc123")
        self.assertEqual(environment["PYTHON_DOTENV_DISABLED"], "1")
        for credential_name in (
            "GITHUB_TOKEN",
            "GROQ_API_KEY",
            "MAIAGENT_API_KEY",
            "SUPABASE_KEY",
            "SUPABASE_URL",
        ):
            self.assertNotIn(credential_name, environment)


if __name__ == "__main__":
    unittest.main()
