from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable
from urllib.parse import urljoin

import requests

ATTRIBUTE_RE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass(frozen=True)
class Channel:
    id: str
    number: str
    name: str
    logo: str
    group: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _parse_extinf(line: str, fallback_id: int) -> dict[str, str]:
    attrs = dict(ATTRIBUTE_RE.findall(line))
    display_name = line.split(",", 1)[1].strip() if "," in line else f"Channel {fallback_id}"
    channel_id = attrs.get("tvg-id") or attrs.get("channel-id") or str(fallback_id)
    number = attrs.get("tvg-chno") or attrs.get("channel-number") or str(fallback_id)
    return {
        "id": channel_id,
        "number": number,
        "name": attrs.get("tvg-name") or display_name,
        "logo": attrs.get("tvg-logo", ""),
        "group": attrs.get("group-title", ""),
    }


def parse_m3u(content: str, base_url: str = "") -> list[Channel]:
    channels: list[Channel] = []
    pending: dict[str, str] | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            pending = _parse_extinf(line, len(channels) + 1)
            continue
        if line.startswith("#"):
            continue
        if pending is None:
            pending = {
                "id": str(len(channels) + 1),
                "number": str(len(channels) + 1),
                "name": f"Channel {len(channels) + 1}",
                "logo": "",
                "group": "",
            }
        channels.append(Channel(url=urljoin(base_url, line), **pending))
        pending = None

    return channels


def fetch_channels(m3u_url: str, timeout: int = 15) -> list[Channel]:
    response = requests.get(m3u_url, timeout=timeout)
    response.raise_for_status()
    return parse_m3u(response.text, base_url=m3u_url)


def find_channel(channels: Iterable[Channel], channel_id: str) -> Channel | None:
    return next((channel for channel in channels if channel.id == channel_id), None)
