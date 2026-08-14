#!/usr/bin/env python3
"""启动 Trae 并开启 CDP 调试端口（通过 argv.json，绕过 CLI 严格解析）。

用法:
    python scripts/launch_trae_cdp.py
    python scripts/launch_trae_cdp.py --port 9224
    python scripts/launch_trae_cdp.py --wait
    python scripts/launch_trae_cdp.py --list

说明:
    Trae 0.1.50 的 code CLI 拒绝 --remote-debugging-port（报 bad option），
    且把位置参数当 node 模块 require。因此本脚本复用 star_core.trae_launcher：
    把 remote-debugging-port 写入 ~/.trae-cn/argv.json，再以零参数启动 Trae，
    由主进程读取 argv.json 开启 CDP。启动后检查端口并打印连接信息。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 项目根目录与 star_core
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 默认 CDP 端口
_DEFAULT_PORT = 9223


def main():
    parser = argparse.ArgumentParser(description="启动 Trae 并开启 CDP 调试端口（argv.json 方式）")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help=f"CDP 端口 (默认 {_DEFAULT_PORT})")
    parser.add_argument("--wait", action="store_true", help="等待 CDP 端口可用后退出")
    parser.add_argument("--list", action="store_true", help="列出 CDP targets 后退出（需 Trae 已启动）")
    args = parser.parse_args()

    # 延迟导入，避免无 star_core 环境直接崩
    try:
        from star_core.trae_launcher import (
            is_cdp_alive,
            list_targets,
            launch_trae_with_cdp,
        )
    except Exception as e:
        print(f"无法加载 star_core.trae_launcher: {e}")
        sys.exit(1)

    # --list 模式：仅列出 targets
    if args.list:
        if not is_cdp_alive(args.port):
            print(f"CDP 端口 {args.port} 不可达。请先用 --wait 启动 Trae。")
            sys.exit(1)
        targets = list_targets(args.port)
        print(f"CDP targets (port {args.port}):")
        for t in targets:
            print(f"  [{t.get('type', '?')}] {t.get('title', '?')[:60]}")
            print(f"    url: {t.get('url', '?')[:80]}")
        print(f"\n共 {len(targets)} 个 target")
        return

    # 端口已可用：直接列 targets
    if is_cdp_alive(args.port):
        print(f"CDP 端口 {args.port} 已可用 — Trae 已带调试端口运行。")
        if not args.wait:
            targets = list_targets(args.port)
            print(f"当前 targets ({len(targets)} 个):")
            for t in targets[:5]:
                print(f"  [{t.get('type', '?')}] {t.get('title', '?')[:50]}")
        return

    # 通过 argv.json + 零参数启动 Trae
    print(f"正在通过 argv.json 以 CDP 端口 {args.port} 启动 Trae...")
    ok = launch_trae_with_cdp(args.port, timeout=30.0)
    if not ok:
        print(f"启动失败 — CDP 端口 {args.port} 未变为可用。")
        print("可尝试先彻底关闭 Trae，再运行本脚本；或检查 Trae 是否安装。")
        sys.exit(1)

    print(f"CDP 端口 {args.port} 已可用!")
    if args.wait:
        targets = list_targets(args.port)
        print(f"当前 targets ({len(targets)} 个):")
        for t in targets[:5]:
            print(f"  [{t.get('type', '?')}] {t.get('title', '?')[:50]}")
    else:
        print(f"Trae 已启动。可在 5-10 秒后运行:")
        print(f"  python scripts/launch_trae_cdp.py --port {args.port} --list")


if __name__ == "__main__":
    main()
