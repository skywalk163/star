"""
群星（Star）命令行工具

提供命令行接口，方便快速操作星核
"""

import asyncio
import argparse
import sys
from typing import Optional

from loguru import logger


def cmd_scan(args):
    """扫描星体"""
    from star_core import StarSeeker
    
    seeker = StarSeeker()
    stars = seeker.scan_skies(force=True)
    
    if not stars:
        print("🌑 未发现任何星体")
        return
    
    print(f"⭐ 发现 {len(stars)} 颗星：")
    print("-" * 60)
    for s in stars:
        status = "💫 闪耀中" if s.is_shining else "🔵 空闲"
        print(f"  [{s.star_type}] PID: {s.pid}  {status}")
        print(f"    标题: {s.title}")
    print("-" * 60)


def cmd_list_types(args):
    """列出支持的星体类型"""
    from star_core import StarSeeker
    
    seeker = StarSeeker()
    types = seeker.list_star_types()
    
    print(f"📋 支持的星体类型（共 {len(types)} 种）：")
    print("-" * 60)
    for name, info in types.items():
        print(f"  {name}: {info['description']}")
        if info['process_names']:
            print(f"    进程: {', '.join(info['process_names'])}")
    print("-" * 60)


def cmd_plugins(args):
    """插件管理"""
    from star_core.plugin_system import PluginManager, PluginStatus
    
    pm = PluginManager(plugin_dir="star_plugins")
    discovered = pm.discover_plugins()
    
    print(f"🔌 发现 {len(discovered)} 个插件：")
    print("-" * 60)
    for p in discovered:
        status_icon = {
            PluginStatus.DISABLED: "⚪",
            PluginStatus.LOADED: "🟡",
            PluginStatus.ACTIVE: "🟢",
            PluginStatus.ERROR: "🔴"
        }.get(p.status, "⚪")
        print(f"  {status_icon} {p.name} v{p.version} ({p.plugin_type.value})")
        print(f"     {p.description}")
        print(f"     作者: {p.author}")
    print("-" * 60)


def cmd_stats(args):
    """查看统计信息"""
    from star_core.analytics import HistoryStore, StarAnalytics
    
    store = HistoryStore()
    analytics = StarAnalytics(store)
    overview = analytics.get_overview_stats()
    
    print("📊 星图统计概览")
    print("=" * 50)
    print(f"  总任务数:     {overview['total_novas']}")
    print(f"  已完成:       {overview['completed']} ✨")
    print(f"  失败:         {overview['failed']} 🌑")
    print(f"  已取消:       {overview['cancelled']}")
    print(f"  成功率:       {overview['success_rate']}%")
    if overview['avg_duration']:
        print(f"  平均耗时:     {overview['avg_duration']}s")
    print("=" * 50)


def cmd_history(args):
    """查看历史记录"""
    from star_core.analytics import HistoryStore
    
    store = HistoryStore()
    records = store.query_novas(limit=args.limit)
    
    if not records:
        print("📭 暂无历史记录")
        return
    
    print(f"📜 历史记录（最近 {len(records)} 条）：")
    print("-" * 70)
    for r in records:
        status_icon = {
            'constellated': '✨',
            'faded': '🌑',
            'darkened': '⚫',
            'shining': '💫',
            'awaiting': '⏳',
            'nascent': '🌱',
            'orbiting': '🛸'
        }.get(r['final_status'], '❓')
        print(f"  {status_icon} {r['id']} - {r['title']}")
        print(f"     [{r.get('assigned_star', '未知')}] {r['final_status']}")
        print(f"     创建: {r['created_at']}")
    print("-" * 70)


def cmd_server(args):
    """启动 API 服务"""
    import uvicorn
    
    logger.info(f"🚀 启动星光服务 on port {args.port}")
    
    uvicorn.run(
        "star_api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


def cmd_info(args):
    """显示版本信息"""
    print("⭐ 群星 Star - AI Agent 调度中心")
    print("=" * 50)
    print("  版本: 0.1.0")
    print("  状态: 公测版 (Beta)")
    print("  作者: Star Team")
    print("  许可证: MIT")
    print("=" * 50)
    print()
    print("使用 'star --help' 查看可用命令")


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="star",
        description="群星 Star - AI Agent 调度中心",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  star scan           扫描当前运行的 AI Agent
  star server         启动 API 服务
  star stats          查看统计信息
  star plugins        管理插件
  star history        查看历史记录
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # scan 命令
    scan_parser = subparsers.add_parser("scan", help="扫描星体")
    
    # types 命令
    types_parser = subparsers.add_parser("types", help="列出支持的星体类型")
    
    # plugins 命令
    plugins_parser = subparsers.add_parser("plugins", help="插件管理")
    
    # stats 命令
    stats_parser = subparsers.add_parser("stats", help="统计信息")
    
    # history 命令
    hist_parser = subparsers.add_parser("history", help="历史记录")
    hist_parser.add_argument("--limit", type=int, default=10, help="显示数量 (默认10)")
    
    # server 命令
    server_parser = subparsers.add_parser("server", help="启动 API 服务")
    server_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    server_parser.add_argument("--port", type=int, default=8765, help="监听端口")
    server_parser.add_argument("--reload", action="store_true", help="热重载模式")
    
    # info 命令
    info_parser = subparsers.add_parser("info", help="版本信息")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    commands = {
        "scan": cmd_scan,
        "types": cmd_list_types,
        "plugins": cmd_plugins,
        "stats": cmd_stats,
        "history": cmd_history,
        "server": cmd_server,
        "info": cmd_info,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        try:
            cmd_func(args)
        except KeyboardInterrupt:
            print("\n👋 再见！")
        except Exception as e:
            logger.error(f"命令执行失败: {e}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
