"""DuMate 桌面端（DuMate.exe / 千帆桌面端）CDP 通道装配。

== 命名澄清（务必先读）=================================================
本仓库历史上的 ``dumate_bridge`` / ``dumate_launcher`` / ``AI_ID="dumate"``
实际驱动的是 **Comate（文心快码）**：命名管道 ``\\\\.\\pipe\\comate-kernel-<port>``、
命令 ``COMATE_AGENT_*``、数据目录 ``~/.comate-engine``。

本模块驱动的是**另一个独立产品**：独立安装的 DuMate 桌面端
（``DuMate.exe``，Electron 43.1.1 / DuMate 1.0.69，用户数据目录
``%APPDATA%\\qianfan-desktop-app``）。两者进程、端口、协议均不相干，
故以 ``dumate_app_`` 前缀区分，避免与既有 ``dumate_`` 模块冲突。

== 为什么必须重启才能拿到 CDP（已静态确认）============================
对 ``resources/app.asar`` 扫描结果：
  - ``remote-debugging-port`` 出现 0 次、``appendSwitch`` 出现 0 次
    → 应用自身不读 argv.json、也不注入该开关，Trae 那套"写 argv.json 后
    零参数启动"的绕行通道在这里**不存在**；只能在命令行直传。
  - ``requestSingleInstanceLock()`` 出现 2 次，未拿到锁即 ``app.quit()``
    → 单实例应用，带新开关的进程无法与旧实例并存，**重启前必须先终止**。

因此本模块与 ``dumate_launcher``（Comate，刻意不提供 kill）取向相反：
Comate 常常就是运行调用方的 IDE 本体，杀它等于自杀；而 DuMate 桌面端是
独立进程，可以安全地停止并重启。

== 启动必须清理 ELECTRON_* 环境变量（2026-08-16 踩坑）=================
若调用方本身跑在 Electron 宿主里（如 Comate 的集成终端），环境中会带
``ELECTRON_RUN_AS_NODE=1``。该变量会被子进程继承，使 ``DuMate.exe``
**退化为纯 Node 解释器**：
  - 无参数启动 → 没有脚本可跑，立即 exit 0，GUI 根本不出现；
  - 带参数启动 → Node 拒绝未知选项，打印 ``bad option:
    --remote-debugging-port=...`` 并 exit 9。
两种现象都极易被误判为"应用拒绝调试端口"或"单实例锁残留"。
因此 :func:`launch_dumate_app_with_cdp` 启动时会剔除所有 ``ELECTRON_*``。

== 副进程 ==============================================================

DuMate 会拉起一组 sidecar：``dumate-na.exe`` / ``dumate-router.exe`` /
``dumate-main-server.exe`` / ``dumate-opencode.exe`` /
``dumate-browser-extension-relay.exe``。它们占用 52922 / 52150 / 19228 等
固定端口，强杀主进程后可能残留并让新实例起不来，故停止时一并清扫。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import List, Optional, Tuple

from star_core.trae_launcher import is_cdp_alive, list_targets, wait_for_cdp

logger = logging.getLogger(__name__)

#: DuMate 桌面端默认 CDP 端口。9223 归 Trae、9224 归 Comate，故取 9225。
DEFAULT_DUMATE_APP_CDP_PORT = 9225

#: DuMate.exe 候选安装路径（按优先级）
_EXE_CANDIDATES: Tuple[str, ...] = (
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\DuMate\DuMate.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\DuMate\DuMate.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\DuMate\DuMate.exe"),
)

#: 主进程可执行名（小写）
_MAIN_EXE_NAME = "dumate.exe"

#: sidecar 可执行名（小写）；停止时一并清扫，避免端口残留
_SIDECAR_EXE_NAMES = frozenset(
    {
        "dumate-na.exe",
        "dumate-router.exe",
        "dumate-main-server.exe",
        "dumate-opencode.exe",
        "dumate-browser-extension-relay.exe",
    }
)

#: 用户数据目录（Electron userData），供诊断展示
USER_DATA_DIR = os.path.join(
    os.path.expandvars("%APPDATA%"), "qianfan-desktop-app"
)


def find_dumate_app_exe() -> Optional[str]:
    """定位 DuMate.exe 绝对路径；找不到返回 None。"""
    for path in _EXE_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    found = shutil.which("DuMate.exe")
    return found or None


def _clean_launch_env() -> dict:
    """返回剔除所有 ``ELECTRON_*`` 后的环境变量副本。

    调用方若身处 Electron 宿主的集成终端，环境里会有
    ``ELECTRON_RUN_AS_NODE=1``；被 DuMate.exe 继承后它会当纯 Node 跑，
    导致"启动即退出"（详见模块 docstring）。
    """
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("ELECTRON")}



def _iter_dumate_procs():
    """迭代所有 DuMate 相关进程，yield ``(proc, name_lower, cmdline)``。

    psutil 是 requirements.txt 的既有依赖；未安装时静默产出空序列，
    让上层通过"找不到进程"降级而非抛栈。
    """
    try:
        import psutil
    except ImportError:  # pragma: no cover
        logger.warning("_iter_dumate_procs: psutil 未安装，无法枚举进程")
        return

    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info.get("name") or "").lower()
        if name != _MAIN_EXE_NAME and name not in _SIDECAR_EXE_NAMES:
            continue
        try:
            cmdline = proc.cmdline()
        except Exception:
            cmdline = []
        yield proc, name, cmdline


def find_running_dumate_app_processes() -> List[dict]:
    """枚举正在运行的 DuMate 桌面端进程。

    Returns:
        每项含 ``pid`` / ``name`` / ``is_main`` / ``cdp_port``。
        ``is_main`` 指 Electron 主进程（命令行不带 ``--type=``）；
        ``cdp_port`` 为命令行中已生效的 ``--remote-debugging-port``（无则 None）。
    """
    out: List[dict] = []
    for proc, name, cmdline in _iter_dumate_procs():
        is_main = name == _MAIN_EXE_NAME and not any(
            a.startswith("--type=") for a in cmdline
        )
        cdp_port: Optional[int] = None
        for arg in cmdline:
            if arg.startswith("--remote-debugging-port="):
                try:
                    cdp_port = int(arg.split("=", 1)[1])
                except ValueError:
                    pass
                break
        out.append(
            {"pid": proc.pid, "name": name, "is_main": is_main, "cdp_port": cdp_port}
        )
    return sorted(out, key=lambda d: d["pid"])


def is_dumate_app_running() -> bool:
    """DuMate 桌面端是否正在运行（不论有无调试端口）。"""
    return any(p["name"] == _MAIN_EXE_NAME for p in find_running_dumate_app_processes())


def get_running_cdp_port() -> Optional[int]:
    """返回当前 DuMate 主进程命令行上的调试端口；未开启返回 None。"""
    for p in find_running_dumate_app_processes():
        if p["is_main"] and p["cdp_port"]:
            return p["cdp_port"]
    return None


def stop_dumate_app(timeout: float = 12.0) -> List[int]:
    """停止 DuMate 桌面端及其 sidecar。

    先对 Electron 主进程发 terminate，给它机会走 ``will-quit`` 钩子自行收尾
    子进程；等待后再清扫仍存活的 DuMate 相关进程（含 sidecar 与残留渲染器）。

    Args:
        timeout: 等待优雅退出的总秒数。

    Returns:
        被终止的 PID 列表（升序）。
    """
    try:
        import psutil
    except ImportError:  # pragma: no cover
        logger.warning("stop_dumate_app: psutil 未安装，无法停止进程")
        return []

    mains = [p for p, name, cmd in _iter_dumate_procs()
             if name == _MAIN_EXE_NAME and not any(a.startswith("--type=") for a in cmd)]
    killed: List[int] = []

    for proc in mains:
        try:
            proc.terminate()
            killed.append(proc.pid)
            logger.info("stop_dumate_app: 已请求主进程退出 pid=%s", proc.pid)
        except Exception as e:
            logger.warning("stop_dumate_app: terminate pid=%s 失败: %s", proc.pid, e)

    if mains:
        psutil.wait_procs(mains, timeout=max(timeout * 0.5, 3.0))

    # 清扫残留（主进程未响应、或 sidecar 未被父进程带走）
    deadline = time.time() + timeout
    while time.time() < deadline:
        leftovers = [p for p, _n, _c in _iter_dumate_procs()]
        if not leftovers:
            break
        for proc in leftovers:
            try:
                proc.kill()
                if proc.pid not in killed:
                    killed.append(proc.pid)
            except Exception:
                pass
        psutil.wait_procs(leftovers, timeout=2.0)

    leftovers = [p.pid for p, _n, _c in _iter_dumate_procs()]
    if leftovers:
        logger.warning("stop_dumate_app: 仍有进程存活: %s", leftovers)
    return sorted(set(killed))


def launch_dumate_app_with_cdp(
    port: int = DEFAULT_DUMATE_APP_CDP_PORT,
    timeout: float = 40.0,
    restart_if_running: bool = True,
) -> bool:
    """以 CDP 调试端口启动 DuMate 桌面端。

    流程（幂等）：
    - 端口已可用 → 直接返回 True。
    - 已在运行但端口未开：``restart_if_running`` 为 False 时拒绝动作返回
      False（把"要不要杀掉用户正在用的 DuMate"的决定权交给调用方）；
      为 True 时先 :func:`stop_dumate_app` 再拉起。
    - 带 ``--remote-debugging-port=<port>`` 启动，等端口就绪。

    Args:
        port: CDP 端口（默认 9225）。
        timeout: 等待端口就绪的最长秒数。
        restart_if_running: 允许为开启调试端口而重启已在运行的实例。

    Returns:
        True 表示 CDP 端口已可用。
    """
    if is_cdp_alive(port):
        return True

    exe = find_dumate_app_exe()
    if not exe:
        logger.warning(
            "launch_dumate_app_with_cdp: 未找到 DuMate.exe（已检查 %s 及 PATH）",
            _EXE_CANDIDATES,
        )
        return False

    if is_dumate_app_running():
        if not restart_if_running:
            logger.info(
                "launch_dumate_app_with_cdp: DuMate 正在运行且未开调试端口，"
                "restart_if_running=False，不做处理"
            )
            return False
        # 单实例锁：带新开关的进程无法与旧实例并存，必须先停
        stop_dumate_app()

    logger.info(
        "launch_dumate_app_with_cdp: 启动 %s --remote-debugging-port=%d", exe, port
    )
    try:
        subprocess.Popen(
            [exe, f"--remote-debugging-port={port}"],
            env=_clean_launch_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("launch_dumate_app_with_cdp: 启动失败: %s", e)
        return False

    return wait_for_cdp(port, timeout=timeout)


def get_cdp_readiness(port: int = DEFAULT_DUMATE_APP_CDP_PORT) -> dict:
    """汇报 CDP 通道就绪度，供 API / UI 展示与引导。

    Returns:
        dict: ``exe`` 安装路径（None 表示未安装）；``running`` 是否在跑；
        ``running_cdp_port`` 当前实例命令行上的调试端口；
        ``port_alive`` 目标端口是否已监听；
        ``needs_restart`` 在跑但目标端口不可用（需重启才能开 CDP）；
        ``targets`` 端口活着时的 target 数量。
    """
    alive = is_cdp_alive(port)
    running = is_dumate_app_running()
    return {
        "port": port,
        "exe": find_dumate_app_exe(),
        "user_data_dir": USER_DATA_DIR,
        "running": running,
        "running_cdp_port": get_running_cdp_port(),
        "port_alive": alive,
        "needs_restart": running and not alive,
        "targets": len(list_targets(port)) if alive else 0,
    }
