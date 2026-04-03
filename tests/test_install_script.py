from pathlib import Path


def test_install_script_uses_environment_python_and_playwright():
    content = Path("install.sh").read_text(encoding="utf-8")

    assert "-m pip install -r requirements.txt" in content
    assert "-m playwright install chromium" in content
    assert "scrapling" not in content
