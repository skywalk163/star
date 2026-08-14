#!/usr/bin/env python3
"""TraeCDPBridge 验证脚本。

测试项目:
1. CDP 端口连通性
2. Target 枚举与选择
3. 全局对象探测
4. 状态检测
5. 消息发送（可选，需 --send）
6. 响应读取（可选，需 --read）
7. 截图（可选，需 --screenshot）

用法:
    python scripts/test_trae_cdp.py
    python scripts/test_trae_cdp.py --send "hello"
    python scripts/test_trae_cdp.py --read
    python scripts/test_trae_cdp.py --screenshot
    python scripts/test_trae_cdp.py --probe
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 将项目根目录和 .pylibs 加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
_PYLIBS = PROJECT_ROOT / ".pylibs"
if _PYLIBS.is_dir():
    sys.path.insert(0, str(_PYLIBS))


def test_connectivity(port: int) -> bool:
    """测试 1: CDP 端口连通性。"""
    print("\n=== 测试 1: CDP 端口连通性 ===")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    alive = bridge.is_alive()
    print(f"  端口 {port}: {'可达' if alive else '不可达'}")
    if not alive:
        print("  请先运行: python scripts/launch_trae_cdp.py --wait")
    return alive


def test_find_target(port: int) -> dict | None:
    """测试 2: Target 枚举与选择。"""
    print("\n=== 测试 2: Target 枚举与选择 ===")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    target = bridge.find_chat_target()
    if target:
        print(f"  选中 target:")
        print(f"    id:    {target.get('id', '?')[:40]}")
        print(f"    title: {target.get('title', '?')[:60]}")
        print(f"    url:   {target.get('url', '?')[:80]}")
    else:
        print("  未找到合适的 target")
    return target


def test_probe_globals(port: int) -> dict | None:
    """测试 3: 全局对象探测。"""
    print("\n=== 测试 3: 全局对象探测 ===")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    result = bridge.probe_globals()
    if result:
        print(f"  探测结果:")
        print(f"  {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print("  探测失败")
    return result


def test_status(port: int) -> str:
    """测试 4: 状态检测。"""
    print("\n=== 测试 4: 状态检测 ===")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    status = bridge.get_status()
    print(f"  当前状态: {status}")
    return status


def test_send(port: int, text: str) -> bool:
    """测试 5: 消息发送。"""
    print(f"\n=== 测试 5: 消息发送 ===")
    print(f"  发送文本: {text[:50]}{'...' if len(text) > 50 else ''}")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    ok = bridge.send_message(text)
    print(f"  结果: {'成功' if ok else '失败'}")
    return ok


def test_read(port: int) -> str:
    """测试 6: 响应读取。"""
    print("\n=== 测试 6: 响应读取 ===")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    text = bridge.get_latest_response()
    if text:
        print(f"  读取到响应 ({len(text)} chars):")
        print(f"  {text[:200]}{'...' if len(text) > 200 else ''}")
    else:
        print("  未读取到响应")
    return text


def test_screenshot(port: int, output_path: str) -> bool:
    """测试 7: 截图。"""
    print(f"\n=== 测试 7: 截图 ===")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    data = bridge.take_screenshot()
    if data:
        Path(output_path).write_bytes(data)
        print(f"  截图已保存: {output_path} ({len(data)} bytes)")
        return True
    else:
        print("  截图失败")
        return False


def test_evaluate(port: int, expr: str) -> None:
    """测试 8: 任意 JS 执行。"""
    print(f"\n=== 测试 8: JS 执行 ===")
    print(f"  表达式: {expr[:80]}")
    from star_core.trae_cdp_bridge import TraeCDPBridge
    bridge = TraeCDPBridge(port=port)
    result = bridge.evaluate(expr)
    print(f"  结果: {json.dumps(result, indent=2, ensure_ascii=False) if result else 'None'}")


def main():
    parser = argparse.ArgumentParser(description="TraeCDPBridge 验证脚本")
    parser.add_argument("--port", type=int, default=9223, help="CDP 端口 (默认 9223)")
    parser.add_argument("--send", type=str, help="发送测试消息")
    parser.add_argument("--read", action="store_true", help="读取最新响应")
    parser.add_argument("--screenshot", type=str, nargs="?", const="trae_screenshot.png", help="截图并保存")
    parser.add_argument("--probe", action="store_true", help="探测全局对象")
    parser.add_argument("--eval", type=str, help="执行任意 JS 表达式")
    args = parser.parse_args()

    # 基础测试
    if not test_connectivity(args.port):
        sys.exit(1)

    target = test_find_target(args.port)
    if not target:
        print("\n无法找到 target，后续测试可能失败。")
        sys.exit(1)

    test_status(args.port)

    # 可选测试
    if args.probe:
        test_probe_globals(args.port)

    if args.send:
        ok = test_send(args.port, args.send)
        if ok and args.read:
            print("\n等待 5 秒后读取响应...")
            time.sleep(5)
            test_read(args.port)

    if args.read and not args.send:
        test_read(args.port)

    if args.screenshot:
        test_screenshot(args.port, args.screenshot)

    if args.eval:
        test_evaluate(args.port, args.eval)

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    main()
