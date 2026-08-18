"""DuMate 桌面端启动器 —— 版本探测与就绪度诊断测试。

不启动真实应用：get_installed_version 是 best-effort 诊断信息，本测试只锁住
「任何环境下都不抛错」「有值时形如版本号」以及「就绪度字典把版本带出来」。
"""

from __future__ import annotations

from star_core import dumate_app_launcher as launcher


def test_get_installed_version_never_raises():
    # 未安装 / 非 Windows / 无权限 都应安静返回 None，而不是把启动链路带崩
    version = launcher.get_installed_version()
    assert version is None or isinstance(version, str)
    if version:
        parts = version.split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts)


def test_get_installed_version_none_when_exe_missing(monkeypatch):
    monkeypatch.setattr(launcher, "find_dumate_app_exe", lambda: None)
    assert launcher.get_installed_version() is None


def test_readiness_exposes_version(monkeypatch):
    monkeypatch.setattr(launcher, "is_cdp_alive", lambda port: False)
    monkeypatch.setattr(launcher, "is_dumate_app_running", lambda: False)
    monkeypatch.setattr(launcher, "get_running_cdp_port", lambda: None)
    monkeypatch.setattr(launcher, "find_dumate_app_exe", lambda: r"C:\x\DuMate.exe")
    monkeypatch.setattr(launcher, "get_installed_version", lambda: "1.0.70")

    info = launcher.get_cdp_readiness(port=9225)
    assert info["version"] == "1.0.70"
    assert info["needs_restart"] is False
    assert info["targets"] == 0
