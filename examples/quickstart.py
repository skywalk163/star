"""
群星 Star - 快速使用示例

演示如何使用星核核心功能
"""

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


async def demo_scan_stars():
    """示例1: 扫描星体"""
    print("\n" + "=" * 60)
    print("🌌 示例 1: 扫描当前运行的 AI Agent")
    print("=" * 60)
    
    from star_core import StarSeeker
    
    seeker = StarSeeker()
    
    # 查看支持的星体类型
    types = seeker.list_star_types()
    print(f"\n📋 支持的星体类型（共 {len(types)} 种）：")
    for name, info in list(types.items())[:5]:
        print(f"  • {name}: {info['description']}")
    
    # 扫描星体
    print("\n🔭 正在扫描星空...")
    stars = seeker.scan_skies(force=True)
    
    if stars:
        print(f"\n✨ 发现 {len(stars)} 颗闪耀的星体：")
        for s in stars[:5]:
            status = "💫 闪耀中" if s.is_shining else "🔵 空闲"
            print(f"  [{s.star_type}] PID={s.pid} {status}")
            print(f"    标题: {s.title[:50]}...")
    else:
        print("\n🌑 暂无运行中的星体")
    
    return stars


async def demo_plugin_system():
    """示例2: 插件系统"""
    print("\n" + "=" * 60)
    print("🔌 示例 2: 插件系统")
    print("=" * 60)
    
    from star_core.plugin_system import PluginManager, PluginStatus
    
    pm = PluginManager(plugin_dir="star_plugins")
    
    # 发现插件
    discovered = pm.discover_plugins()
    print(f"\n📦 发现 {len(discovered)} 个插件：")
    for p in discovered:
        icon = {
            PluginStatus.DISABLED: "⚪",
            PluginStatus.LOADED: "🟡",
            PluginStatus.ACTIVE: "🟢",
            PluginStatus.ERROR: "🔴"
        }.get(p.status, "⚪")
        print(f"  {icon} {p.name} v{p.version} - {p.description}")
        print(f"     类型: {p.plugin_type.value}, 作者: {p.author}")
    
    # 加载示例插件
    if discovered:
        first = discovered[0]
        print(f"\n📥 加载插件: {first.name}")
        success = pm.load_plugin(first.name)
        if success:
            print(f"   ✅ 加载成功")
            info = pm.get_plugin_info(first.name)
            if info:
                print(f"   状态: {info.status.value}")
        else:
            print(f"   ❌ 加载失败")


async def demo_analytics():
    """示例3: 统计分析"""
    print("\n" + "=" * 60)
    print("📊 示例 3: 历史记录与统计分析")
    print("=" * 60)
    
    from star_core.analytics import HistoryStore, StarAnalytics
    from star_core import Nova, StarPriority, StarStatus
    from datetime import datetime, timedelta
    
    store = HistoryStore(db_path="data/demo_history.db")
    analytics = StarAnalytics(store)
    
    # 生成一些模拟数据
    print("\n📝 生成模拟历史数据...")
    
    for i in range(20):
        nova = Nova(
            title=f"测试任务 {i+1}",
            description="这是一个演示任务",
            starlight=f"请执行第 {i+1} 个任务",
            priority=StarPriority.NORMAL
        )
        nova.assigned_star = f"star_type_{i % 4}"
        nova.status = StarStatus.CONSTELLATED if i % 5 != 0 else StarStatus.FADED
        nova.result_starlight = f"任务 {i+1} 完成结果" * 10
        nova.created_at = datetime.now() - timedelta(hours=i * 2)
        nova.updated_at = nova.created_at + timedelta(minutes=30 + i * 5)
        
        store.record_nova(nova)
    
    # 概览统计
    print("\n📈 概览统计:")
    overview = analytics.get_overview_stats()
    for key, value in overview.items():
        if key == "success_rate":
            print(f"  {key}: {value}%")
        elif value is not None:
            print(f"  {key}: {value}")
    
    # 按星体类型统计
    print("\n🌟 按星体类型统计:")
    star_stats = analytics.get_star_type_stats()
    for star_type, stats in star_stats.items():
        print(f"  {star_type}: 共{stats['total']}个, 成功率{stats['success_rate']}%")
    
    # 每日统计
    print("\n📅 近7日统计:")
    daily = analytics.get_daily_stats(7)
    for d in daily:
        bar = "█" * (d['completed'] // 2)
        print(f"  {d['date']}: 完成{d['completed']:2d} {bar}")
    
    # 完整报告
    print("\n📋 完整统计报告已生成")
    report = analytics.generate_report()
    print(f"   报告生成时间: {report['generated_at']}")


async def demo_constellation():
    """示例4: 星座（多星协同）"""
    print("\n" + "=" * 60)
    print("🌠 示例 4: 星座协同（多星协作）")
    print("=" * 60)
    
    from star_core import Constellation, Nova, StarPriority, ConstellationStatus
    
    # 创建星座
    constellation = Constellation(
        name="内容创作协同",
        description="多任务并行内容创作",
        execution_mode="parallel"
    )
    
    # 添加多个新星
    for i in range(3):
        nova = Nova(
            title=f"子任务 {i+1}",
            description=f"并行执行的子任务 {i+1}",
            starlight=f"执行子任务 {i+1}",
            priority=StarPriority.NORMAL
        )
        constellation.add_nova(nova)
    
    print(f"\n🌌 星座: {constellation.name}")
    print(f"   模式: {constellation.execution_mode}")
    print(f"   新星数: {len(constellation.novas)}")
    print(f"   状态: {constellation.status.value}")
    
    # 查看进度
    progress = constellation.get_progress()
    print(f"\n📊 进度: {progress['completed']}/{progress['total']} ({progress['percentage']}%)")
    
    # 持久化存储
    from star_core import ConstellationStorage
    
    storage = ConstellationStorage(db_path="data/demo_constellations.db")
    storage.save_constellation(constellation)
    
    # 重新加载
    loaded = storage.load_constellation(constellation.id)
    if loaded:
        print(f"\n💾 星座已保存并重新加载: {loaded.name}")
    
    # 结果对比
    from star_core import ResultComparator
    
    text1 = "人工智能正在改变世界的方方面面"
    text2 = "AI技术正在改变各个领域"
    
    similarity = ResultComparator.calculate_similarity(text1, text2)
    levenshtein = ResultComparator.levenshtein_similarity(text1, text2)
    common = ResultComparator.find_common_parts(text1, text2)
    
    print(f"\n🔍 结果对比示例:")
    print(f"   Jaccard 相似度: {similarity:.2f}")
    print(f"   Levenshtein 相似度: {levenshtein:.2f}")
    print(f"   公共部分: {common}")
    
    print(f"\n📝 对比报告:")
    report = ResultComparator.compare_results([text1, text2])
    print(f"   对数量: {report['pair_count']}")
    print(f"   平均相似度: {report['avg_similarity']:.2f}")


async def main():
    """运行所有示例"""
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    
    print("⭐ 群星 Star - 快速使用示例")
    print("本脚本展示群星核心功能的基本用法")
    
    demos = [
        ("扫描星体", demo_scan_stars),
        ("插件系统", demo_plugin_system),
        ("历史与统计", demo_analytics),
        ("星座协同", demo_constellation),
    ]
    
    for name, demo_func in demos:
        try:
            await demo_func()
        except Exception as e:
            print(f"\n❌ 示例 [{name}] 执行出错: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🎉 示例运行完成！")
    print("=" * 60)
    print("\n更多功能请查看:")
    print("  • 启动服务: star server")
    print("  • 扫描星体: star scan")
    print("  • 查看统计: star stats")
    print("  • 管理插件: star plugins")
    print("\nAPI 文档: http://localhost:8765/docs")


if __name__ == "__main__":
    asyncio.run(main())
