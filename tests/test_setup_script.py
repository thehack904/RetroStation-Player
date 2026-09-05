from pathlib import Path


SETUP_SCRIPT = Path(__file__).parents[1] / "scripts" / "setup.sh"


def _install_summary(script: str) -> str:
    start = script.index('echo "RetroStation Player installed."')
    end = script.index("restore_pi_boot_config_for_purge()")
    return script[start:end]


def test_install_summary_includes_default_auth_credentials():
    summary = _install_summary(SETUP_SCRIPT.read_text(encoding="utf-8"))

    assert 'if [[ "$ENABLE_AUTH" == true ]]; then' in summary
    assert 'echo "Authentication: enabled"' in summary
    assert 'echo "Username: $AUTH_USERNAME"' in summary
    assert 'if [[ "$AUTH_MUST_CHANGE" == true ]]; then' in summary
    assert 'echo "Password: $AUTH_PASSWORD"' in summary


def test_install_summary_only_prints_password_for_default_credentials():
    summary = _install_summary(SETUP_SCRIPT.read_text(encoding="utf-8"))

    auth_block = summary.split('if [[ "$ENABLE_AUTH" == true ]]; then', 1)[1]
    password_block = auth_block.split('if [[ "$AUTH_MUST_CHANGE" == true ]]; then', 1)[1]

    assert 'echo "Password: $AUTH_PASSWORD"' in password_block
    assert password_block.index('echo "Password: $AUTH_PASSWORD"') < password_block.index("fi")


def test_install_uses_supported_python_and_module_pip():
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "python3-venv python3-pip" in script
    assert "sys.version_info >= (3, 10)" in script
    assert '"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip' in script
    assert '"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"' in script


def test_install_supports_multiple_linux_package_managers():
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "detect_package_manager()" in script
    assert 'case "${os_id:-}" in' in script
    assert 'debian|ubuntu|linuxmint|raspbian' in script
    assert 'fedora|rhel|centos|rocky|almalinux' in script
    assert 'arch|manjaro|archarm' in script
    assert 'dnf install -y "$package"' in script
    assert 'yum install -y "$package"' in script
    assert 'pacman -S --noconfirm "$package"' in script


def test_install_prompts_for_required_reboot_and_explains_declining():
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    prompt = script.split("prompt_reboot() {", 1)[1].split("\n}\n", 1)[0]

    assert '[[ "$REBOOT_REQUIRED" == true ]] || return 0' in prompt
    assert 'read -r -p "Reboot now? [y/N] " answer' in prompt
    assert "[Yy]|[Yy][Ee][Ss]) reboot ;;" in prompt
    assert "A reboot is required for the player services to work correctly." in prompt
    assert "prompt_reboot" in script.split("cmd_install() {", 1)[1]
