from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any

_DEVICE_TREE_MODEL = Path('/proc/device-tree/model')
_DEVICE_TREE_COMPATIBLE = Path('/proc/device-tree/compatible')
_DMI_ROOT = Path('/sys/class/dmi/id')
_OS_RELEASE = Path('/etc/os-release')
_MEMINFO = Path('/proc/meminfo')
_CPUINFO = Path('/proc/cpuinfo')


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors='replace').replace('\x00', '').strip()
    except OSError:
        return ''


def _read_os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    text = _read_text(_OS_RELEASE)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key] = value.strip().strip('"')
    return values


def _userspace_architecture() -> str:
    try:
        result = subprocess.run(
            ['dpkg', '--print-architecture'],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        value = result.stdout.strip()
        if value:
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.machine() or 'Unknown'


def _processor_name() -> str:
    cpuinfo = _read_text(_CPUINFO)
    preferred_keys = ('model name', 'Model Name', 'Processor', 'cpu model')
    for key in preferred_keys:
        prefix = f'{key}\t'
        for line in cpuinfo.splitlines():
            if line.startswith(prefix) or line.startswith(f'{key}:'):
                return line.split(':', 1)[-1].strip()
    try:
        result = subprocess.run(
            ['lscpu'], check=False, capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.splitlines():
            if line.casefold().startswith('model name:'):
                return line.split(':', 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or 'Unknown'


def _memory_total_bytes() -> int:
    for line in _read_text(_MEMINFO).splitlines():
        if line.startswith('MemTotal:'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1]) * 1024
                except ValueError:
                    break
    return 0


def _machine_identity() -> tuple[str, str, bool]:
    model = _read_text(_DEVICE_TREE_MODEL)
    if model:
        return model, '', model.casefold().startswith('raspberry pi')

    vendor = _read_text(_DMI_ROOT / 'sys_vendor')
    product = _read_text(_DMI_ROOT / 'product_name')
    version = _read_text(_DMI_ROOT / 'product_version')
    parts = [part for part in (vendor, product, version) if part]
    if parts:
        # Avoid repeating a vendor already embedded in the product name.
        if vendor and product.casefold().startswith(vendor.casefold()):
            parts = [product] + ([version] if version else [])
        return ' '.join(parts), vendor, False

    fallback = platform.node() or platform.machine() or 'Unknown'
    return fallback, vendor, False



def _device_tree_compatible() -> list[str]:
    try:
        raw = _DEVICE_TREE_COMPATIBLE.read_bytes()
    except OSError:
        return []
    return [item.decode("utf-8", errors="replace").strip() for item in raw.split(b"\x00") if item]


def detect_hardware_profile() -> str:
    compatible = set(_device_tree_compatible())
    if "raspberrypi,model-zero-w" in compatible:
        return "rpi-zero-w"
    return "default"

def collect_system_info() -> dict[str, Any]:
    machine, manufacturer, is_raspberry_pi = _machine_identity()
    os_release = _read_os_release()
    memory_bytes = _memory_total_bytes()
    return {
        'machine': machine,
        'manufacturer': manufacturer,
        'is_raspberry_pi': is_raspberry_pi,
        'operating_system': os_release.get('PRETTY_NAME') or platform.platform(),
        'kernel': platform.release() or 'Unknown',
        'kernel_architecture': platform.machine() or 'Unknown',
        'userspace_architecture': _userspace_architecture(),
        'processor': _processor_name(),
        'cpu_cores': os.cpu_count() or 0,
        'memory_bytes': memory_bytes,
        'device_tree_compatible': _device_tree_compatible(),
        'hardware_profile': detect_hardware_profile(),
    }
