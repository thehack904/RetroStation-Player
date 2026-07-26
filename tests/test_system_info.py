from retrostation_player import system_info


def test_device_tree_machine_identity(monkeypatch):
    monkeypatch.setattr(system_info, '_read_text', lambda path: 'Raspberry Pi 5 Model B Rev 1.0' if path == system_info._DEVICE_TREE_MODEL else '')
    machine, manufacturer, is_pi = system_info._machine_identity()
    assert machine == 'Raspberry Pi 5 Model B Rev 1.0'
    assert manufacturer == ''
    assert is_pi is True


def test_dmi_machine_identity(monkeypatch):
    values = {
        system_info._DEVICE_TREE_MODEL: '',
        system_info._DMI_ROOT / 'sys_vendor': 'Hewlett-Packard',
        system_info._DMI_ROOT / 'product_name': 'HP Compaq Elite 8300 USDT',
        system_info._DMI_ROOT / 'product_version': '',
    }
    monkeypatch.setattr(system_info, '_read_text', lambda path: values.get(path, ''))
    machine, manufacturer, is_pi = system_info._machine_identity()
    assert machine == 'Hewlett-Packard HP Compaq Elite 8300 USDT'
    assert manufacturer == 'Hewlett-Packard'
    assert is_pi is False


def test_memory_total_bytes(monkeypatch):
    monkeypatch.setattr(system_info, '_read_text', lambda path: 'MemTotal:       2027220 kB\n')
    assert system_info._memory_total_bytes() == 2027220 * 1024


def test_zero_w_hardware_profile(monkeypatch):
    monkeypatch.setattr(system_info, '_device_tree_compatible', lambda: ['raspberrypi,model-zero-w', 'brcm,bcm2835'])
    assert system_info.detect_hardware_profile() == 'rpi-zero-w'
