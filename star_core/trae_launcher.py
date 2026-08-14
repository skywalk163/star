"""
Trae 启动器（trae_launcher）- 自动以 CDP 调试端口拉起 Trae Work

把 scripts/launch_trae_cdp.py 的"探测 exe + 启动 + 等端口就绪"逻辑抽成
可复用函数，供 TraeWorkAdapter.connect() 在 CDP 端口不可达时自动拉起
Trae，让"连接 Trae"像连接 DuMate 一样一键完成。

== 如何绕过 Trae 的 CLI 严格解析（已实测 + 静态确认）==================
Trae 0.1.50 的 exe 是 VS Code 的 ``code`` CLI 分支：
  - 传 ``--remote-debugging-port=9223`` → 报 ``bad option`` 并立即退出；
  - 传位置参数（如路径）→ 被当成 node 模块 ``require``，报
    ``Cannot find module``。
即**命令行永远无法把 CDP 端口传给 Trae**。

但 Trae 主进程（main.js）会读取 user data 目录下的 ``argv.json``，
对其中的 ``remote-debugging-port`` 走 ``app.commandLine.appendSwitch``
（main.js 第 1902 行附近有允许列表 + appendSwitch 逻辑，已确认）。
因此唯一可靠做法是：把 ``remote-debugging-port`` 写进 ``argv.json``，
再以**零参数**启动 Trae，由主进程把它附加到 electron 命令行。

设计要点：
- 幂等：端口已可用 → 直接返回 True，不重复拉起。
- 写 argv.json：``ensure_trae_cdp_argv`` 把端口写入
  ``~/<dataFolderName>/argv.json``（默认 ``~/.trae-cn/argv.json``），
  与 Trae 的 ``argvResource`` 解析一致。
- 清单实例锁：强杀 Trae 后 ``code.lock`` 可能残留，启动前清理，
  避免新实例被误判为"已在运行"而静默退出。
- 跨平台：Windows 下用 DETACHED_PROCESS 让 Trae 脱离父进程独立运行。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

#: 默认 CDP 端口（与 TraeWorkAdapter / launch_trae_cdp.py 保持一致）
_DEFAULT_TRAE_CDP_PORT = 9223

#: Trae 可执行文件候选路径（覆盖常见安装位置）
_TRAE_PATHS: List[str] = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Trae CN\Trae CN.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\TRAE SOLO CN\TRAE SOLO CN.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Trae\Trae.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Trae\Trae.exe"),
]


def find_trae_exe() -> Optional[str]:
    """查找 Trae 可执行文件路径。

    依次检查候选安装路径，再从 PATH 查找常见可执行文件名。

    Returns:
        exe 绝对路径，未找到返回 None
    """
    for path in _TRAE_PATHS:
        if path and os.path.isfile(path):
            return path
    for name in ("Trae.exe", "Trae CN.exe", "TRAE SOLO CN.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def is_cdp_alive(port: int, timeout: float = 2.0) -> bool:
    """检查 CDP 端口是否可达（/json 返回 200）。"""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_cdp(port: int, timeout: float = 30.0) -> bool:
    """等待 CDP 端口变为可用。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_cdp_alive(port):
            return True
        time.sleep(1.0)
    return False


def list_targets(port: int) -> List[dict]:
    """列出 CDP targets（需端口已可用）。"""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def _strip_jsonc_comments(text: str) -> str:
    """去掉 JSONC（含 // 与 /* */ 注释）的注释，便于 json.loads 解析。

    Trae 的 argv.json 默认带 ``//`` 注释，标准 json 无法解析，需要此函数。
    """
    out: list = []
    in_str = False
    escape = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def get_trae_argv_json_path() -> str:
    """计算 Trae 的 argv.json 绝对路径（与 main.js 的 argvResource 一致）。

    Trae main.js: ``argvResource = ut(userHome, product.dataFolderName, "argv.json")``
    其中 ``userHome = os.homedir()``，``dataFolderName`` 默认 ``.trae-cn``
    （来自 product.json）。本机实测路径为 ``C:\\Users\\skywalk\\.trae-cn\\argv.json``。

    Returns:
        argv.json 绝对路径
    """
    data_folder = ".trae-cn"
    # 优先从 product.json 读取真实 dataFolderName，避免硬编码漂移
    try:
        exe = find_trae_exe()
        if exe:
            pj = os.path.join(os.path.dirname(exe), "resources", "app", "product.json")
            if os.path.isfile(pj):
                import json
                with open(pj, "r", encoding="utf-8", errors="ignore") as f:
                    dn = json.load(f).get("dataFolderName")
                if dn:
                    data_folder = dn
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), data_folder, "argv.json")


def ensure_trae_cdp_argv(port: int = _DEFAULT_TRAE_CDP_PORT) -> bool:
    """确保 Trae 的 argv.json 含 ``remote-debugging-port``，使零参数启动即带 CDP。

    已存在且端口一致 → 直接返回 True（幂等）。
    否则解析现有 argv.json（容忍 // 注释），写入/更新端口后回写。

    Args:
        port: 调试端口（默认 9223）。

    Returns:
        True 表示 argv.json 已就绪（含该端口）
    """
    import json

    path = get_trae_argv_json_path()
    key = "remote-debugging-port"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data: dict = {}
        if os.path.isfile(path):
            raw = open(path, "r", encoding="utf-8", errors="ignore").read()
            try:
                data = json.loads(_strip_jsonc_comments(raw))
            except Exception:
                data = {}
        if str(data.get(key)) == str(port):
            return True
        data[key] = str(port)
        with open(path, "w", encoding="utf-8") as f:
            f.write("// 由 Star 自动维护：开启 CDP 调试端口供 Star 驱动 Trae。\n")
            f.write("// 修改后需彻底重启 Trae 才生效。\n")
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        logger.info("ensure_trae_cdp_argv: 已写入 argv.json (%s -> port %s)", path, port)
        return True
    except Exception as e:  # pragma: no cover
        logger.warning("ensure_trae_cdp_argv: 写入失败: %s", e)
        return False


def _clean_trae_singleton_lock() -> None:
    """清理 Trae 单实例锁 code.lock，避免强杀后新实例被误判为已在运行。

    Trae 强杀（taskkill /F）后，user data 目录下的 ``code.lock`` 可能残留，
    导致后续零参数启动被单实例逻辑静默退出。启动前清理它。
    """
    candidates = [
        os.path.join(os.path.expandvars("%APPDATA%"), "TRAE SOLO CN", "code.lock"),
        os.path.join(os.path.expanduser("~"), ".trae-cn", "code.lock"),
    ]
    for c in candidates:
        try:
            if os.path.isfile(c):
                os.remove(c)
                logger.info("已清理单实例锁: %s", c)
        except Exception as e:  # pragma: no cover
            logger.warning("清理单实例锁失败 %s: %s", c, e)


def launch_trae_with_cdp(port: int = _DEFAULT_TRAE_CDP_PORT, timeout: float = 30.0) -> bool:
    """以 CDP 调试端口启动 Trae（通过 argv.json，绕过 CLI 严格解析）。

    Trae 0.1.50 的 code CLI 拒绝 ``--remote-debugging-port``（报 bad option），
    且把位置参数当成 node 模块 require。唯一可靠的绕行方式是在 user data 目录
    的 ``argv.json`` 中写入 ``remote-debugging-port``，再以**零参数**启动，由
    Trae 主进程读取后 ``appendSwitch`` 到 electron 命令行。

    流程：
    - 端口已可用 → 直接返回 True（幂等）。
    - 否则：确保 argv.json 含该端口 → 清理单实例锁 → 零参数拉起 → 等端口就绪。

    Args:
        port: CDP 端口号（默认 9223）。
        timeout: 等待 CDP 端口就绪的最长秒数（默认 30）。

    Returns:
        True 表示 CDP 端口已可用（Trae 可连接）
    """
    if is_cdp_alive(port):
        return True

    trae_exe = find_trae_exe()
    if not trae_exe:
        logger.warning(
            "launch_trae_with_cdp: 未找到 Trae 可执行文件（已检查 %s 及 PATH）",
            _TRAE_PATHS,
        )
        return False

    if not ensure_trae_cdp_argv(port):
        logger.warning("launch_trae_with_cdp: 无法写入 argv.json，放弃启动")
        return False

    _clean_trae_singleton_lock()

    logger.info(
        "launch_trae_with_cdp: 零参数启动 Trae（主进程将读 argv.json 开 CDP %d）",
        port,
    )
    try:
        subprocess.Popen(
            [trae_exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("launch_trae_with_cdp: 启动失败: %s", e)
        return False

    return wait_for_cdp(port, timeout=timeout)


def find_running_trae_processes(exe_path: Optional[str] = None) -> List[int]:
    """查找正在运行的 Trae 进程 PID 列表（按 exe 文件名匹配）。

    通过 wmic 枚举进程名与 PID 再匹配。注意中文 Windows 上 wmic 输出
    为 GBK 编码，必须用 bytes + gbk(errors='ignore') 解码，否则会触发
    UnicodeDecodeError 导致探测失败（从而"先关旧实例"失效）。

    Args:
        exe_path: Trae 可执行文件路径（默认自动探测）。仅用于精确匹配。

    Returns:
        正在运行的 Trae PID 列表（去重、升序），未找到返回空列表。
    """
    exact = os.path.basename(exe_path).lower() if exe_path else None
    pids: List[int] = []
    try:
        # 读取字节，按 gbk 解码（errors=ignore）规避中文系统编码问题
        out = subprocess.run(
            ["wmic", "process", "get", "ProcessId,Name"],
            capture_output=True, timeout=15,
        ).stdout.decode("gbk", "ignore")
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            # 行尾为 PID，前面是可能含空格的进程名
            parts = line.rsplit(None, 1)
            if len(parts) != 2:
                continue
            pname, pid = parts
            pl = pname.lower()
            # 精确匹配 exe 名，或"名称含 trae 且以 .exe 结尾"的宽松匹配
            if (exact and pl == exact) or (pl.endswith(".exe") and "trae" in pl):
                try:
                    pids.append(int(pid))
                except ValueError:
                    pass
    except Exception as e:  # pragma: no cover
        logger.warning("find_running_trae_processes: wmic 查询失败: %s", e)
    return sorted(set(pids))


def is_trae_running(exe_path: Optional[str] = None) -> bool:
    """Trae 是否正在运行（无需以调试端口启动）。"""
    return bool(find_running_trae_processes(exe_path))


def kill_trae_processes(exe_path: Optional[str] = None, timeout: float = 8.0) -> List[int]:
    """终止所有正在运行的 Trae 进程（含子进程树）。

    Args:
        exe_path: Trae 可执行文件路径（默认自动探测）。
        timeout: 等待进程退出的秒数。

    Returns:
        成功发出终止信号的 PID 列表。
    """
    pids = find_running_trae_processes(exe_path)
    if not pids:
        return []

    logger.info("kill_trae_processes: 发现 %d 个 Trae 进程: %s", len(pids), pids)
    killed: List[int] = []
    for pid in pids:
        try:
            # /T 杀掉整棵进程树（Electron 主进程 + 渲染/辅助进程）
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True, text=True, timeout=10,
            )
            killed.append(pid)
        except Exception as e:  # pragma: no cover
            logger.warning("kill_trae_processes: 终止 PID %s 失败: %s", pid, e)

    # 等待进程真正退出（避免单实例锁残留导致新实例仍被抢占）
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not find_running_trae_processes(exe_path):
            break
        time.sleep(0.5)
    logger.info("kill_trae_processes: 已终止 %s", killed)
    return killed


def restart_trae_with_cdp(
    port: int = _DEFAULT_TRAE_CDP_PORT,
    launch_timeout: float = 30.0,
) -> bool:
    """关闭所有正在运行的 Trae 实例，再以 CDP 调试端口重启。

    用于解决"Trae 已在运行但未开调试端口，单实例锁占用导致 connect
    无法拉起 CDP 实例"的场景：先彻底退出旧实例（清单实例锁），
    再通过 argv.json + 零参数启动带调试端口的新实例。

    Args:
        port: CDP 端口号（默认 9223）。
        launch_timeout: 等待新实例 CDP 端口就绪的最长秒数。

    Returns:
        True 表示新实例 CDP 端口已可用
    """
    kill_trae_processes(None)
    return launch_trae_with_cdp(port, timeout=launch_timeout)
