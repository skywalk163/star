#!/usr/bin/env python3
"""DuMateAppCDPBridge 验证脚本（DuMate 桌面端 / 百度搭子）。

DuMate 每次发版都会换前端资源哈希、偶尔调 DOM，"发送没反应""读不到回复"这类
间接症状排查起来很费时。升级后先跑这个脚本，一次看清端口、target、每个角色的
选择器命中情况，再决定要不要改 star_core/dumate_app_cdp_bridge.py 的候选选择器。

前置：DuMate 必须带调试端口启动（单实例锁，必须先退出再重启）::

    python scripts/test_dumate_app_cdp.py --launch

用法::

    python scripts/test_dumate_app_cdp.py                # 体检（只读，安全）
    python scripts/test_dumate_app_cdp.py --launch        # 需要时重启 DuMate 开端口
    python scripts/test_dumate_app_cdp.py --send "你好"   # 实发一条（会动用户会话）
    python scripts/test_dumate_app_cdp.py --read          # 读最后一条回复
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
_PYLIBS = PROJECT_ROOT / ".pylibs"
if _PYLIBS.is_dir():
    sys.path.insert(0, str(_PYLIBS))


def show_readiness(port: int) -> dict:
    """打印安装/运行/端口就绪度，含已安装版本号。"""
    from star_core.dumate_app_launcher import get_cdp_readiness

    info = get_cdp_readiness(port)
    print("\n=== 就绪度 ===")
    for key in ("version", "exe", "running", "running_cdp_port", "port_alive",
                "needs_restart", "targets"):
        print(f"  {key:18} {info.get(key)}")
    if info["needs_restart"]:
        print("\n  DuMate 在跑但没开调试端口。带 --launch 可重启它开端口"
              "（会关掉当前 DuMate 窗口）。")
    return info


def probe(port: int) -> bool:
    """选择器体检：逐角色报告命中的候选与数量。"""
    from star_core.dumate_app_cdp_bridge import DuMateAppCDPBridge

    bridge = DuMateAppCDPBridge(port=port)
    print("\n=== 选择器体检 ===")
    result = bridge.probe_selectors()
    if not result.get("roles"):
        print(f"  失败: {result.get('reason')}")
        return False

    for role, info in result["roles"].items():
        matched = info.get("matched")
        mark = "OK  " if matched else "MISS"
        print(f"  [{mark}] {role:10} count={info.get('count', 0):<3} {matched or '(无命中)'}")
        if not matched:
            for cand in info.get("candidates", []):
                print(f"           候选 {cand['sel']} -> {cand['count']}")

    missing = result.get("missing") or []
    # 空闲时没有"停止"按钮是正常的，不算失配
    blocking = [r for r in missing if r != "stop"]
    if blocking:
        print(f"\n  需要修选择器的角色: {', '.join(blocking)}")
        print("  改 star_core/dumate_app_cdp_bridge.py 里对应的 _*_SELS 候选组。")
    else:
        print("\n  关键角色全部命中（stop 仅在生成中出现，空闲缺失属正常）。")
    return not blocking


def main() -> int:
    from star_core.dumate_app_launcher import (
        DEFAULT_DUMATE_APP_CDP_PORT,
        launch_dumate_app_with_cdp,
    )

    parser = argparse.ArgumentParser(description="DuMate 桌面端 CDP 通道验证")
    parser.add_argument("--port", type=int, default=DEFAULT_DUMATE_APP_CDP_PORT)
    parser.add_argument("--launch", action="store_true",
                        help="端口未开时重启 DuMate 以开启调试端口（会关掉当前窗口）")
    parser.add_argument("--send", metavar="TEXT", help="实发一条消息（会写入用户会话）")
    parser.add_argument("--read", action="store_true", help="读取最后一条助手回复")
    args = parser.parse_args()

    info = show_readiness(args.port)

    if not info["port_alive"]:
        if not args.launch:
            print("\n端口未就绪，加 --launch 重启 DuMate，或手动带参数启动：")
            print(f'  "{info["exe"]}" --remote-debugging-port={args.port}')
            return 1
        print("\n=== 重启 DuMate 以开启调试端口 ===")
        if not launch_dumate_app_with_cdp(args.port):
            print("  启动失败")
            return 1
        print("  端口已就绪")

    ok = probe(args.port)

    from star_core.dumate_app_cdp_bridge import DuMateAppCDPBridge
    bridge = DuMateAppCDPBridge(port=args.port)
    print(f"\n=== 状态 ===\n  {bridge.get_status()}")

    if args.send:
        print(f"\n=== 发送: {args.send} ===")
        sent = bridge.send_message(args.send)
        print(f"  结果: {sent}")
        if sent:
            for _ in range(30):
                time.sleep(1.0)
                reply = bridge.get_new_response()
                if reply and bridge.get_status() == "idle":
                    break
            print(f"  回复: {json.dumps(bridge.get_new_response(), ensure_ascii=False)[:500]}")

    if args.read:
        print("\n=== 最后一条助手回复 ===")
        print(f"  {bridge.get_latest_response()[:500]}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
