from unittest.mock import patch

from retrostation_player.config import request_system_reboot, save_zero_w_composite_overscan, set_startup_screen_enabled


def test_save_zero_w_composite_overscan_calls_privileged_helper():
    with patch('subprocess.run') as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '/boot/firmware/cmdline.txt\n'
        run.return_value.stderr = ''
        path = save_zero_w_composite_overscan('480i', {'left': 8, 'right': 9, 'top': 4, 'bottom': 5})
    assert str(path) == '/boot/firmware/cmdline.txt'
    assert run.call_args.args[0] == [
        'sudo', '-n', '/usr/local/libexec/retrostation-player-composite-overscan',
        '480i', '8', '9', '4', '5',
    ]


def test_save_zero_w_composite_overscan_can_disable_overscan():
    with patch('subprocess.run') as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '/boot/firmware/cmdline.txt\n'
        run.return_value.stderr = ''
        save_zero_w_composite_overscan('576i', None)
    assert run.call_args.args[0][-2:] == ['disable', '576i']


def test_save_zero_w_composite_overscan_surfaces_helper_error():
    with patch('subprocess.run') as run:
        run.return_value.returncode = 1
        run.return_value.stdout = ''
        run.return_value.stderr = 'permission denied'
        try:
            save_zero_w_composite_overscan('480i', {'left': 1, 'right': 1, 'top': 1, 'bottom': 1})
        except OSError as exc:
            assert 'permission denied' in str(exc)
        else:
            raise AssertionError('Expected helper failure')


def test_request_system_reboot_uses_same_scoped_helper():
    with patch('subprocess.run') as run:
        run.return_value.returncode = 0
        run.return_value.stdout = 'reboot-requested\n'
        run.return_value.stderr = ''
        request_system_reboot()
    assert run.call_args.args[0] == [
        'sudo', '-n', '/usr/local/libexec/retrostation-player-composite-overscan', 'reboot'
    ]


def test_reset_zero_w_composite_overscan_uses_privileged_helper():
    import retrostation_player.config as config
    from unittest.mock import patch
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "/boot/firmware/cmdline.txt|/boot/firmware/config.txt\n"
        run.return_value.stderr = ""
        result = config.reset_zero_w_composite_overscan()
    assert "cmdline.txt" in result
    assert run.call_args.args[0] == [
        "sudo", "-n", "/usr/local/libexec/retrostation-player-composite-overscan", "reset-original"
    ]


def test_set_startup_screen_enabled_uses_scoped_helper():
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "enabled\n"
        run.return_value.stderr = ""
        set_startup_screen_enabled(True)
    assert run.call_args.args[0] == [
        "sudo", "-n", "/usr/local/libexec/retrostation-player-startup-screen-control", "enable"
    ]


def test_set_startup_screen_disabled_uses_scoped_helper():
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "disabled\n"
        run.return_value.stderr = ""
        set_startup_screen_enabled(False)
    assert run.call_args.args[0] == [
        "sudo", "-n", "/usr/local/libexec/retrostation-player-startup-screen-control", "disable"
    ]
