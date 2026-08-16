"""Comate（文心快码）CDP 通道装配。

命名说明：本仓库把 Comate 记作 ``dumate``（``AI_ID="dumate"``、命名管道
``comate-kernel-<port>``），本模块沿用该历史命名，驱动的是 **Comate**。
独立安装的 DuMate 桌面端（``DuMate.exe``）是另一个产品，见
``star_core/dumate_app_launcher.py``。

与 Trae 同源：Comate 也是 VS Code / Electron fork，主进程读取
``~/<dataFolderName>/argv.json``（本机 ``~/.comate/argv.json``）并对其中的
``remote-debugging-port`` 走 ``app.commandLine.appendSwitch``，因此写入该键后
**零参数启动**即自带 CDP 调试端口，无需在命令行传 ``--remote-debugging-port``。

与 ``trae_launcher`` 的关键差异（务必保留）：
    Comate 往往就是当前正在运行本进程的 IDE 本体。杀掉并重启它会直接终止
    调用方所在的会话，因此本模块**不提供** kill/restart 能力，只负责：
      1. 写入 argv.json（幂等、可逆，下次启动生效）
      2. 探测调试端口是否就绪
      3. 枚举渲染器 target
    重启由用户自行决定时机。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import List, Optional

from star_core.trae_launcher import _strip_jsonc_comments

logger = logging.getLogger(__name__)

#: Comate 默认 CDP 端口。9223 已被 Trae 占用，故错开。
DEFAULT_DUMATE_CDP_PORT = 9224

#: Comate 安装目录候选（按优先级）
_EXE_CANDIDATES = (
    os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "Programs", "Comate", "comate.exe"
    ),
    r"C:\Program Files\Comate\comate.exe",
    r"C:\Program Files (x86)\Comate\comate.exe",
)


def find_comate_exe() -> Optional[str]:
    """定位 comate.exe 绝对路径；找不到返回 None。"""
    for p in _EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def get_comate_argv_json_path() -> str:
    """计算 Comate 的 argv.json 绝对路径（与主进程 argvResource 一致）。

    优先从 ``resources/app/product.json`` 读取真实 ``dataFolderName``，
    避免硬编码漂移；读不到时回退 ``.comate``。
    """
    data_folder = ".comate"
    try:
        exe = find_comate_exe()
        if exe:
            pj = os.path.join(os.path.dirname(exe), "resources", "app", "product.json")
            if os.path.isfile(pj):
                with open(pj, encoding="utf-8", errors="ignore") as f:
                    dn = json.load(f).get("dataFolderName")
                if dn:
                    data_folder = dn
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), data_folder, "argv.json")


def is_cdp_alive(port: int = DEFAULT_DUMATE_CDP_PORT, timeout: float = 2.0) -> bool:
    """探测 ``/json/version`` 判断调试端口是否就绪。"""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout
        ):
            return True
    except Exception:
        return False


def list_targets(port: int = DEFAULT_DUMATE_CDP_PORT) -> List[dict]:
    """枚举调试端口下的所有 target；失败返回空列表。"""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json", timeout=3.0
        ) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def ensure_comate_cdp_argv(port: int = DEFAULT_DUMATE_CDP_PORT) -> bool:
    """确保 argv.json 含 ``remote-debugging-port``，使下次零参数启动即带 CDP。

    幂等：已是目标端口时直接返回 True，不重写文件。
    保守：解析失败时**不覆盖**用户配置，返回 False 而非写入一个新文件，
    避免抹掉 locale 等既有设置。

    Returns:
        True 表示 argv.json 已就绪（含该端口）
    """
    path = get_comate_argv_json_path()
    key = "remote-debugging-port"

    conf: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            parsed = json.loads(_strip_jsonc_comments(raw))
            if not isinstance(parsed, dict):
                logger.warning(
                    "ensure_comate_cdp_argv: %s 顶层不是对象，拒绝覆盖", path
                )
                return False
            conf = parsed
        except Exception as e:
            logger.warning(
                "ensure_comate_cdp_argv: 解析 %s 失败(%s)，拒绝覆盖用户配置", path, e
            )
            return False

    if str(conf.get(key, "")) == str(port):
        return True

    conf[key] = str(port)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent="\t", ensure_ascii=False)
        logger.info("ensure_comate_cdp_argv: 已写入 %s (port %s)", path, port)
        return True
    except Exception as e:
        logger.warning("ensure_comate_cdp_argv: 写入 %s 失败: %s", path, e)
        return False


def get_cdp_readiness(port: int = DEFAULT_DUMATE_CDP_PORT) -> dict:
    """汇报 CDP 通道就绪度，供 API / UI 展示与引导用户重启。

    Returns:
        dict: ``argv_ready`` 是否已写入端口；``port_alive`` 端口是否已监听；
        ``needs_restart`` 已写配置但端口未起（等用户重启 Comate）；
        ``targets`` 端口活着时的 target 数量。
    """
    path = get_comate_argv_json_path()
    argv_ready = False
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                conf = json.loads(_strip_jsonc_comments(f.read()))
            argv_ready = str(conf.get("remote-debugging-port", "")) == str(port)
        except Exception:
            argv_ready = False

    alive = is_cdp_alive(port)
    return {
        "port": port,
        "argv_path": path,
        "argv_ready": argv_ready,
        "port_alive": alive,
        "needs_restart": argv_ready and not alive,
        "targets": len(list_targets(port)) if alive else 0,
    }
