"""Run unittest discovery with network access disabled before test imports."""

from __future__ import annotations

import ipaddress
import socket
import unittest
from typing import NoReturn


class OfflineNetworkError(OSError):
    """Raised when a test attempts to use the network."""


def _deny_network(*_args: object, **_kwargs: object) -> NoReturn:
    raise OfflineNetworkError("network access is disabled by the offline test runner")


_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_SENDMSG = getattr(socket.socket, "sendmsg", None)
_ORIGINAL_SENDTO = socket.socket.sendto
_AF_UNIX = getattr(socket, "AF_UNIX", None)


def _normalize_local_address(address: object) -> tuple[object, ...] | None:
    if not isinstance(address, tuple) or not address:
        return None
    host = address[0]
    if host == "localhost":
        host = "127.0.0.1"
    try:
        if not ipaddress.ip_address(host).is_loopback:
            return None
    except (TypeError, ValueError):
        return None
    return (host, *address[1:])


def _is_local_address(address: object) -> bool:
    return _normalize_local_address(address) is not None


def _is_local_socket(socket_instance: socket.socket, address: object) -> bool:
    is_unix_socket = _AF_UNIX is not None and socket_instance.family == _AF_UNIX
    return is_unix_socket or _is_local_address(address)


def _connect(socket_instance: socket.socket, address: object) -> object:
    if _is_local_socket(socket_instance, address):
        return _ORIGINAL_CONNECT(socket_instance, address)
    return _deny_network()


def _connect_ex(socket_instance: socket.socket, address: object) -> object:
    if _is_local_socket(socket_instance, address):
        return _ORIGINAL_CONNECT_EX(socket_instance, address)
    return _deny_network()


def _create_connection(address: object, *args: object, **kwargs: object) -> object:
    normalized_address = _normalize_local_address(address)
    if normalized_address is None:
        return _deny_network()
    return _ORIGINAL_CREATE_CONNECTION(normalized_address, *args, **kwargs)


def _getaddrinfo(
    host: object,
    port: object,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0,
) -> object:
    normalized_address = _normalize_local_address((host, port))
    if normalized_address is None:
        return _deny_network()
    return _ORIGINAL_GETADDRINFO(
        normalized_address[0],
        port,
        family,
        type,
        proto,
        flags | socket.AI_NUMERICHOST,
    )


def _sendto(socket_instance: socket.socket, *args: object, **kwargs: object) -> object:
    address = args[-1] if args else kwargs.get("address")
    if _is_local_socket(socket_instance, address):
        return _ORIGINAL_SENDTO(socket_instance, *args, **kwargs)
    return _deny_network()


def _sendmsg(socket_instance: socket.socket, *args: object, **kwargs: object) -> object:
    if _ORIGINAL_SENDMSG is None:
        return _deny_network()
    if _AF_UNIX is not None and socket_instance.family == _AF_UNIX:
        return _ORIGINAL_SENDMSG(socket_instance, *args, **kwargs)

    address = args[3] if len(args) >= 4 else kwargs.get("address")
    if address is None:
        try:
            address = socket_instance.getpeername()
        except OSError:
            return _deny_network()
    if _is_local_address(address):
        return _ORIGINAL_SENDMSG(socket_instance, *args, **kwargs)
    return _deny_network()


def network_is_blocked() -> bool:
    return bool(getattr(socket, "_stock_webagent_network_blocked", False))


def install_network_block() -> None:
    """Block TCP, UDP, and DNS entry points while preserving local socket pairs."""
    if network_is_blocked():
        return

    socket.create_connection = _create_connection
    socket.getaddrinfo = _getaddrinfo
    socket.getfqdn = _deny_network
    socket.gethostbyaddr = _deny_network
    socket.gethostbyname = _deny_network
    socket.gethostbyname_ex = _deny_network
    socket.getnameinfo = _deny_network
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    if _ORIGINAL_SENDMSG is not None:
        socket.socket.sendmsg = _sendmsg
    socket.socket.sendto = _sendto
    socket._stock_webagent_network_blocked = True


def main() -> int:
    install_network_block()
    program = unittest.main(module=None, exit=False)
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
