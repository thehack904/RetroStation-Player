"""mpv JSON IPC controller.

Provides :class:`MpvIpcController` for sending JSON IPC commands to a running
mpv process over a Unix domain socket.  The controller is intentionally
stateless with respect to the mpv process itself: callers are responsible for
starting mpv with ``--input-ipc-server`` pointing at the chosen socket path and
for cleaning up the socket file after the process exits.

Usage::

    from retrostation_player.mpv_ipc import MpvIpcController, MpvIpcError

    ipc = MpvIpcController("/tmp/my-player.sock")

    # Check whether mpv has created the socket yet
    if ipc.is_socket_ready():
        ipc.set_property("volume", 80)
        current = ipc.get_property("volume")
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any


class MpvIpcError(OSError):
    """Raised when mpv IPC communication fails or mpv rejects a command."""


class MpvIpcController:
    """Send JSON IPC commands to a running mpv process.

    :param socket_path: Path to the Unix socket created by mpv when started
        with ``--input-ipc-server=<path>``.
    :param timeout: Per-operation socket timeout in seconds.
    """

    def __init__(self, socket_path: Path | str, timeout: float = 2.0) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = float(timeout)

    def is_socket_ready(self) -> bool:
        """Return ``True`` if the mpv IPC socket file exists on the filesystem.

        This is a lightweight presence check only; it does not verify that mpv
        is actively listening on the socket.
        """
        return self.socket_path.exists()

    def send_command(self, command: list[Any]) -> dict[str, Any]:
        """Send a JSON IPC command to mpv and return the parsed response.

        :param command: mpv IPC command as a list, e.g.
            ``["set_property", "volume", 80]``.
        :returns: The parsed mpv response dictionary.
        :raises MpvIpcError: If the socket is unreachable, the connection
            times out, or mpv returns an error response.
        """
        payload = (json.dumps({"command": command}) + "\n").encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(str(self.socket_path))
                sock.sendall(payload)
                response = b""
                while not response.endswith(b"\n"):
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
        except OSError as exc:
            raise MpvIpcError(
                f"Unable to communicate with mpv over {self.socket_path}: {exc}"
            ) from exc

        if not response:
            raise MpvIpcError(
                f"mpv closed the connection without sending a response over {self.socket_path}"
            )
        result: dict[str, Any] = json.loads(response.decode().strip())
        error = result.get("error")
        if error not in {None, "success"}:
            raise MpvIpcError(f"mpv IPC command rejected: {error}")
        return result

    def get_property(self, name: str) -> Any:
        """Return the current value of an mpv property.

        :param name: Property name, e.g. ``"volume"`` or ``"pause"``.
        :raises MpvIpcError: If the property cannot be retrieved.
        """
        result = self.send_command(["get_property", name])
        return result.get("data")

    def set_property(self, name: str, value: Any) -> None:
        """Set an mpv property to the given value.

        :param name: Property name, e.g. ``"volume"`` or ``"pause"``.
        :param value: New property value.
        :raises MpvIpcError: If the property cannot be set.
        """
        self.send_command(["set_property", name, value])
