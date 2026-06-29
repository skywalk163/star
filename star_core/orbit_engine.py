"""
星轨引擎（OrbitEngine）- 任务调度核心

管理任务的生命周期：创建、分配、执行、监控、完成的完整流程
"""

import asyncio
import uuid
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import deque


# 导入星核组件
from star_core.star_seeker import StarSeeker, StarBody
from star_core.star_assigner import StarAssigner
from star_core.star_gazer import StarGazer


class StarStatus(Enum):
    """星芒状态"""
    NASCENT = "nascent"           # 初生（新创建）
    ORBITING = "orbiting"         # 入轨（已分配）
    SHINING = "shining"           # 闪耀（Agent 正在处理）
    AWAITING_ECHO = "awaiting"    # 待回响（等待用户审查）
    CONSTELLATED = "constellated" # 成星（完成）
    FADED = "faded"               # 暗淡（失败）
    DARKENED = "darkened"        # 熄灭（取消）


class StarPriority(Enum):
    """星等（优先级）"""
    DIM = 0        # 暗星（低）
    NORMAL = 1     # 常星（正常）
    BRIGHT = 2     # 亮星（高）
    SUPERNOVA = 3  # 超新星（紧急）


class ConstellationStatus(Enum):
    """星座状态"""
    FORMING = "forming"           # 形成中（创建中）
    READY = "ready"               # 就绪（待发射）
    ORCHESTRATING = "orchestrating"  # 编排中（执行中）
    CONSTELLATED = "constellated" # 成星（完成）
    FADED = "faded"               # 暗淡（失败）


@dataclass
class Nova:
    """
    新星 - 任务数据模型
    
    Attributes:
        id: 唯一标识
        title: 任务标题
        description: 任务描述
        starlight: 发送给星的指令
        context_files: 上下文文件列表
        assigned_star: 分配的目标星类型
        status: 当前状态
        priority: 优先级
        created_at: 创建时间
        updated_at: 更新时间
        result_starlight: 星辉（Agent 返回结果）
        starlight_log: 星光日志（对话历史）
        echo: 回响（用户反馈）
        error: 错误信息
    """
    id: str
    title: str
    description: str
    starlight: str
    context_files: list[str] = field(default_factory=list)
    assigned_star: Optional[str] = None
    status: StarStatus = StarStatus.NASCENT
    priority: StarPriority = StarPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    result_starlight: Optional[str] = None
    starlight_log: list[dict] = field(default_factory=list)
    echo: Optional[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
    
    def update_status(self, new_status: StarStatus):
        """更新状态并记录时间"""
        self.status = new_status
        self.updated_at = datetime.now()
        self.starlight_log.append({
            'timestamp': self.updated_at.isoformat(),
            'status': new_status.value,
            'action': 'status_change'
        })
    
    def add_starlight(self, role: str, content: str):
        """添加星光日志"""
        self.starlight_log.append({
            'timestamp': datetime.now().isoformat(),
            'role': role,
            'content': content
        })
    
    def set_result(self, result: str):
        """设置执行结果"""
        self.result_starlight = result
        self.updated_at = datetime.now()


@dataclass
class Constellation:
    """
    星座 - 多星协同任务
    
    由多个 Nova 组成的复杂任务，支持串行/并行执行模式
    """
    id: str
    name: str
    description: str
    novas: list[Nova] = field(default_factory=list)
    status: ConstellationStatus = ConstellationStatus.FORMING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    execution_mode: str = "parallel"  # "parallel" 或 "sequential"
    completed_novas: list[str] = field(default_factory=list)  # 已完成的新星 ID
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
    
    def update_status(self, new_status: ConstellationStatus):
        """更新星座状态"""
        self.status = new_status
        self.updated_at = datetime.now()
    
    def is_all_complete(self) -> bool:
        """检查是否所有新星都完成"""
        terminal_statuses = {StarStatus.CONSTELLATED, StarStatus.FADED, StarStatus.DARKENED}
        return all(n.status in terminal_statuses for n in self.novas)
    
    def get_shining_novas(self) -> list[Nova]:
        """获取正在闪耀的新星"""
        return [n for n in self.novas if n.status == StarStatus.SHINING]
    
    def get_next_pending_nova(self) -> Optional[Nova]:
        """获取下一个待执行的新星（串行模式）"""
        for nova in self.novas:
            if nova.status in {StarStatus.NASCENT, StarStatus.ORBITING}:
                return nova
        return None


class OrbitEngine:
    """
    星轨引擎 - 任务调度核心
    
    负责：
    - 任务的创建与分配
    - 星体状态的监控
    - 任务队列的管理
    - 星轨的动态调整
    """

    # 星体亲缘性 - 根据任务特征匹配星体类型
    STAR_AFFINITY = {
        'trae': {
            'keywords': ['生成', '创建', '编写', '写', '实现', '开发', 'generate', 'create', 'write', 'implement'],
            'weight': 1.0
        },
        'codearts_atomcode': {
            'keywords': ['审查', 'review', '检查', '漏洞', '安全', '分析', 'audit'],
            'weight': 1.2
        },
        'cursor': {
            'keywords': ['重构', 'refactor', '迁移', '优化', '性能', '多文件', 'batch'],
            'weight': 1.1
        },
        'copilot': {
            'keywords': ['补全', 'complete', 'suggest', '建议', '提示'],
            'weight': 0.8
        },
        'windsurf': {
            'keywords': ['探索', 'explore', '查找', 'search', '发现'],
            'weight': 1.0
        },
        'claude': {
            'keywords': ['解释', 'explain', '分析', 'analyze', '理解', 'understand'],
            'weight': 1.0
        }
    }

    def __init__(
        self,
        star_seeker: Optional[StarSeeker] = None,
        star_assigner: Optional[StarAssigner] = None,
        star_gazer: Optional[StarGazer] = None,
        use_emissary: bool = True,
    ):
        self.star_seeker = star_seeker or StarSeeker()
        self.star_assigner = star_assigner or StarAssigner()
        self.star_gazer = star_gazer or StarGazer()
        self._use_emissary = use_emissary
        self._emissary_cache: dict[str, object] = {}
        
        self._orbit_queue: asyncio.Queue[Nova] = asyncio.Queue()
        self._active_novas: dict[str, Nova] = {}
        self._gaze_stop_events: dict[str, asyncio.Event] = {}
        
        # 星座管理
        self._constellations: dict[str, Constellation] = {}
        self._constellation_callbacks: dict[str, list[str]] = {}
        
        # 回调
        self._on_nova_status_change: Optional[Callable[[Nova], Awaitable[None]]] = None
        self._on_starlight_received: Optional[Callable[[Nova, str], Awaitable[None]]] = None

    def set_callbacks(
        self,
        on_status_change: Optional[Callable[[Nova], Awaitable[None]]] = None,
        on_starlight: Optional[Callable[[Nova, str], Awaitable[None]]] = None
    ):
        """设置回调函数"""
        self._on_nova_status_change = on_status_change
        self._on_starlight_received = on_starlight

    async def birth_nova(self, nova: Nova) -> str:
        """
        诞生新星 - 提交新任务
        
        Args:
            nova: 新星实例
            
        Returns:
            新星的 ID
        """
        # 如果未指定目标星，计算星轨
        if not nova.assigned_star:
            nova.assigned_star = self._calculate_orbit(nova)
        
        nova.update_status(StarStatus.NASCENT)
        nova.add_starlight('user', nova.starlight)
        
        # 加入队列
        await self._orbit_queue.put(nova)
        self._active_novas[nova.id] = nova
        
        return nova.id

    def _calculate_orbit(self, nova: Nova) -> str:
        """
        计算星轨 - 根据任务特征路由到合适的星
        
        通过关键词匹配计算最合适的星体类型
        """
        scores: dict[str, float] = {}
        
        text = f"{nova.title} {nova.description}".lower()
        
        for star_type, affinity in self.STAR_AFFINITY.items():
            score = 0.0
            for keyword in affinity['keywords']:
                if keyword.lower() in text:
                    score += affinity['weight']
            
            if score > 0:
                # 检查该类型星体是否可用
                available = self.star_seeker.get_idle_stars(star_type)
                if available:
                    scores[star_type] = score
        
        if not scores:
            # 默认返回任意可用星体
            idle = self.star_seeker.get_any_idle_star()
            return idle.star_type if idle else 'generic'
        
        # 返回得分最高的星体类型
        return max(scores, key=scores.get)

    async def launch_nova(self, nova_id: str, use_emissary: Optional[bool] = None) -> bool:
        """
        发射新星 - 将任务分配给星体执行
        
        Args:
            nova_id: 新星 ID
            use_emissary: 是否使用星使模式（None 表示自动选择）
            
        Returns:
            是否成功发射
        """
        nova = self._active_novas.get(nova_id)
        if not nova:
            return False
        
        # 获取目标星体实例
        target_stars = self.star_seeker.get_idle_stars(nova.assigned_star)
        if not target_stars:
            # 尝试任何空闲星体
            target_stars = self.star_seeker.get_idle_stars()
            if not target_stars:
                return False
        
        star = target_stars[0]
        
        # 决定使用哪种模式
        if use_emissary is None:
            use_emissary = self._use_emissary
        
        # 如果启用星使模式，直接使用（更通用）
        if use_emissary:
            return await self._launch_nova_with_emissary(nova, star)
        
        # 传统模式：文本注入 + UIA 观星
        nova.update_status(StarStatus.ORBITING)
        nova.add_starlight('system', f'分配给 {star.star_type} (PID: {star.pid})')
        
        success = self.star_assigner.send_starlight(star, nova.starlight)
        
        if success:
            nova.update_status(StarStatus.SHINING)
            star.mark_shining(True)
            
            await self._start_gazing(nova, star)
            
            if self._on_nova_status_change:
                await self._on_nova_status_change(nova)
        else:
            nova.update_status(StarStatus.FADED)
            nova.error = "Failed to send starlight to star"
        
        return success

    async def _start_gazing(self, nova: Nova, star: StarBody):
        """启动观星监控"""
        stop_event = asyncio.Event()
        self._gaze_stop_events[nova.id] = stop_event
        
        async def on_change(s: StarBody, content: str):
            nova.set_result(content)
            nova.add_starlight(star.star_type, content)
            
            if self._on_starlight_received:
                await self._on_starlight_received(nova, content)
            
            # 检查是否完成
            if self.star_gazer.detect_completion(s):
                stop_event.set()
                nova.update_status(StarStatus.AWAITING_ECHO)
                star.mark_shining(False)
        
        asyncio.create_task(
            self.star_gazer.async_continuous_gaze(star, on_change)
        )
    
    def _get_emissary(self, star: StarBody):
        """获取或创建星使"""
        if star.star_id in self._emissary_cache:
            return self._emissary_cache[star.star_id]
        
        from star_core.star_emissary import StarEmissary
        em = StarEmissary(star)
        self._emissary_cache[star.star_id] = em
        return em
    
    async def _launch_nova_with_emissary(self, nova: Nova, star: StarBody) -> bool:
        """
        使用星使方式发射新星（OCR 闭环）
        
        当 UIA 方式不可用时，使用 OCR + 剪贴板注入的闭环方式
        """
        try:
            import asyncio
            
            em = self._get_emissary(star)
            
            nova.update_status(StarStatus.ORBITING)
            nova.add_starlight('system', f'分配给 {star.star_type} (PID: {star.pid}) [星使模式]')
            
            # 发送指令（异步执行，不阻塞）
            success = em.send_prompt(nova.starlight)
            
            if not success:
                nova.update_status(StarStatus.FADED)
                nova.error = "Failed to send prompt via emissary"
                return False
            
            nova.update_status(StarStatus.SHINING)
            star.mark_shining(True)
            
            # 后台等待响应
            async def _wait_for_response():
                try:
                    response = em.wait_for_response()
                    nova.set_result(response)
                    nova.add_starlight(star.star_type, response)
                    
                    if self._on_starlight_received:
                        await self._on_starlight_received(nova, response)
                    
                    nova.update_status(StarStatus.AWAITING_ECHO)
                    star.mark_shining(False)
                    
                    if self._on_nova_status_change:
                        await self._on_nova_status_change(nova)
                        
                except Exception as e:
                    nova.update_status(StarStatus.FADED)
                    nova.error = str(e)
            
            asyncio.create_task(_wait_for_response())
            
            if self._on_nova_status_change:
                await self._on_nova_status_change(nova)
            
            return True
            
        except Exception as e:
            nova.update_status(StarStatus.FADED)
            nova.error = f"Emissary launch failed: {str(e)}"
            return False
    
    async def launch_nova_emissary(self, nova_id: str) -> bool:
        """
        使用星使模式发射新星（显式调用）
        
        Args:
            nova_id: 新星 ID
            
        Returns:
            是否成功
        """
        nova = self._active_novas.get(nova_id)
        if not nova:
            return False
        
        target_stars = self.star_seeker.get_idle_stars(nova.assigned_star)
        if not target_stars:
            target_stars = self.star_seeker.get_idle_stars()
            if not target_stars:
                return False
        
        star = target_stars[0]
        return await self._launch_nova_with_emissary(nova, star)

    async def adjust_orbit(self, nova_id: str, new_starlight: str) -> bool:
        """
        调轨 - 修改运行中的任务
        
        Args:
            nova_id: 新星 ID
            new_starlight: 新的指令内容
            
        Returns:
            是否成功调整
        """
        nova = self._active_novas.get(nova_id)
        if not nova:
            return False
        
        if nova.status != StarStatus.SHINING:
            return False
        
        # 获取当前执行的星体
        shining_stars = self.star_seeker.get_shining_stars()
        if not shining_stars:
            return False
        
        # 发送修正指令
        success = self.star_assigner.inject_correction(
            shining_stars[0],
            nova.starlight,
            new_starlight
        )
        
        if success:
            nova.starlight = new_starlight
            nova.add_starlight('star_core', f'星轨已调整: {new_starlight}')
            nova.updated_at = datetime.now()
        
        return success

    async def add_echo(self, nova_id: str, echo: str) -> bool:
        """
        添加回响 - 用户对结果的反馈
        
        Args:
            nova_id: 新星 ID
            echo: 用户反馈
            
        Returns:
            是否成功
        """
        nova = self._active_novas.get(nova_id)
        if not nova:
            return False
        
        nova.echo = echo
        nova.add_starlight('user', f'[回响] {echo}')
        
        # 如果需要继续执行，发送新指令
        if '继续' in echo or 'go on' in echo.lower():
            return await self.adjust_orbit(nova_id, echo)
        
        # 否则标记完成
        nova.update_status(StarStatus.CONSTELLATED)
        
        # 停止观星
        if nova_id in self._gaze_stop_events:
            self._gaze_stop_events[nova_id].set()
        
        return True

    async def fade_nova(self, nova_id: str, reason: str) -> bool:
        """
        使新星暗淡 - 标记任务失败
        
        Args:
            nova_id: 新星 ID
            reason: 失败原因
            
        Returns:
            是否成功
        """
        nova = self._active_novas.get(nova_id)
        if not nova:
            return False
        
        nova.update_status(StarStatus.FADED)
        nova.error = reason
        
        # 停止观星
        if nova_id in self._gaze_stop_events:
            self._gaze_stop_events[nova_id].set()
        
        return True

    async def darken_nova(self, nova_id: str) -> bool:
        """
        熄灭新星 - 取消任务
        
        Args:
            nova_id: 新星 ID
            
        Returns:
            是否成功
        """
        nova = self._active_novas.get(nova_id)
        if not nova:
            return False
        
        nova.update_status(StarStatus.DARKENED)
        
        # 停止观星
        if nova_id in self._gaze_stop_events:
            self._gaze_stop_events[nova_id].set()
        
        return True

    def get_nova(self, nova_id: str) -> Optional[Nova]:
        """获取新星"""
        return self._active_novas.get(nova_id)

    def get_novas_by_status(self, status: StarStatus) -> list[Nova]:
        """按状态获取新星列表"""
        return [n for n in self._active_novas.values() if n.status == status]

    def get_novas_by_star(self, star_type: str) -> list[Nova]:
        """按目标星类型获取新星列表"""
        return [n for n in self._active_novas.values() if n.assigned_star == star_type]

    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self._orbit_queue.qsize()

    async def process_queue(self):
        """处理队列中的任务（后台运行）"""
        while True:
            try:
                # 取出队首任务
                nova = await asyncio.wait_for(self._orbit_queue.get(), timeout=1.0)
                
                # 尝试发射
                await self.launch_nova(nova.id)
                
            except asyncio.TimeoutError:
                # 队列为空，继续等待
                continue
            except Exception as e:
                # 记录错误但继续运行
                pass

    def get_stats(self) -> dict:
        """获取调度统计"""
        stats = {
            'total_novas': len(self._active_novas),
            'queue_size': self._orbit_queue.qsize(),
            'by_status': {},
            'by_star': {},
            'shining_stars': len(self.star_seeker.get_shining_stars()),
            'idle_stars': len(self.star_seeker.get_idle_stars())
        }
        
        for status in StarStatus:
            stats['by_status'][status.value] = len(self.get_novas_by_status(status))
        
        for star_type in self.STAR_AFFINITY.keys():
            stats['by_star'][star_type] = len(self.get_novas_by_star(star_type))
        
        return stats

    async def create_constellation(
        self,
        name: str,
        description: str,
        nova_specs: list[dict],
        execution_mode: str = "parallel"
    ) -> Constellation:
        """
        创建星座 - 多星协同任务
        
        Args:
            name: 星座名称
            description: 描述
            nova_specs: 新星规格列表，每个包含 title, description, starlight, assigned_star
            execution_mode: 执行模式，"parallel"（并行）或 "sequential"（串行）
            
        Returns:
            创建的星座
        """
        constellation = Constellation(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            execution_mode=execution_mode
        )
        
        for spec in nova_specs:
            nova = Nova(
                id=str(uuid.uuid4())[:8],
                title=spec['title'],
                description=spec['description'],
                starlight=spec['starlight'],
                assigned_star=spec.get('assigned_star')
            )
            await self.birth_nova(nova)
            constellation.novas.append(nova)
        
        constellation.update_status(ConstellationStatus.READY)
        
        # 注册星座到存储
        self._constellations[constellation.id] = constellation
        
        return constellation

    async def launch_constellation(self, constellation_id: str) -> bool:
        """
        发射星座 - 启动所有组成新星
        
        Args:
            constellation_id: 星座 ID
            
        Returns:
            是否成功发射
        """
        constellation = self._constellations.get(constellation_id)
        if not constellation:
            return False
        
        if constellation.status not in {ConstellationStatus.READY, ConstellationStatus.ORCHESTRATING}:
            return False
        
        constellation.update_status(ConstellationStatus.ORCHESTRATING)
        
        if constellation.execution_mode == "parallel":
            # 并行模式：发射所有新星
            for nova in constellation.novas:
                if nova.status in {StarStatus.NASCENT}:
                    asyncio.create_task(self._launch_nova_with_constellation(nova, constellation))
        else:
            # 串行模式：发射第一个
            next_nova = constellation.get_next_pending_nova()
            if next_nova:
                await self._launch_nova_with_constellation(next_nova, constellation)
        
        return True

    async def _launch_nova_with_constellation(self, nova: Nova, constellation: Constellation):
        """发射新星（星座模式）"""
        success = await self.launch_nova(nova.id)
        if not success:
            constellation.completed_novas.append(nova.id)
            constellation.update_status(ConstellationStatus.FADED)
        
        # 注册回调，在新星完成时通知星座
        if hasattr(self, '_constellation_callbacks'):
            if constellation.id not in self._constellation_callbacks:
                self._constellation_callbacks[constellation.id] = []
            self._constellation_callbacks[constellation.id].append(nova.id)

    def get_constellation(self, constellation_id: str) -> Optional[Constellation]:
        """获取星座"""
        return self._constellations.get(constellation_id)

    def get_all_constellations(self) -> list[Constellation]:
        """获取所有星座"""
        return list(self._constellations.values())

    def get_constellations_by_status(self, status: ConstellationStatus) -> list[Constellation]:
        """按状态获取星座列表"""
        return [c for c in self._constellations.values() if c.status == status]

    def _on_constellation_nova_complete(self, constellation_id: str, nova_id: str):
        """当星座中的新星完成时的处理"""
        constellation = self._constellations.get(constellation_id)
        if not constellation:
            return
        
        constellation.completed_novas.append(nova_id)
        
        # 检查星座是否完成
        if constellation.is_all_complete():
            constellation.update_status(ConstellationStatus.CONSTELLATED)
        elif constellation.execution_mode == "sequential":
            # 串行模式：启动下一个
            next_nova = constellation.get_next_pending_nova()
            if next_nova:
                asyncio.create_task(self._launch_nova_with_constellation(next_nova, constellation))


class ConstellationStorage:
    """
    星座存储 - 持久化管理
    
    负责星座的持久化存储和加载
    """
    
    def __init__(self, db_path: str = "data/constellations.db"):
        import os
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS constellations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL,
                execution_mode TEXT DEFAULT 'parallel',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS novas (
                id TEXT PRIMARY KEY,
                constellation_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                starlight TEXT,
                assigned_star TEXT,
                status TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_starlight TEXT,
                echo TEXT,
                error TEXT,
                FOREIGN KEY (constellation_id) REFERENCES constellations(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS starlight_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nova_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT,
                content TEXT,
                FOREIGN KEY (nova_id) REFERENCES novas(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_constellation(self, constellation: Constellation):
        """保存星座"""
        import sqlite3
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 保存星座
        cursor.execute("""
            INSERT OR REPLACE INTO constellations 
            (id, name, description, status, execution_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            constellation.id,
            constellation.name,
            constellation.description,
            constellation.status.value,
            constellation.execution_mode,
            constellation.created_at.isoformat(),
            constellation.updated_at.isoformat()
        ))
        
        # 保存新星
        for nova in constellation.novas:
            cursor.execute("""
                INSERT OR REPLACE INTO novas
                (id, constellation_id, title, description, starlight, assigned_star,
                 status, priority, created_at, updated_at, result_starlight, echo, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nova.id,
                constellation.id,
                nova.title,
                nova.description,
                nova.starlight,
                nova.assigned_star,
                nova.status.value,
                nova.priority.value,
                nova.created_at.isoformat(),
                nova.updated_at.isoformat(),
                nova.result_starlight,
                nova.echo,
                nova.error
            ))
            
            # 保存日志
            for log in nova.starlight_log:
                cursor.execute("""
                    INSERT INTO starlight_logs (nova_id, timestamp, role, content)
                    VALUES (?, ?, ?, ?)
                """, (nova.id, log.get('timestamp', ''), log.get('role', ''), log.get('content', '')))
        
        conn.commit()
        conn.close()
    
    def load_constellation(self, constellation_id: str) -> Optional[Constellation]:
        """加载星座"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 加载星座
        cursor.execute("SELECT * FROM constellations WHERE id = ?", (constellation_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        # 加载新星
        cursor.execute("SELECT * FROM novas WHERE constellation_id = ?", (constellation_id,))
        nova_rows = cursor.fetchall()
        
        novas = []
        for nr in nova_rows:
            nova = Nova(
                id=nr['id'],
                title=nr['title'],
                description=nr['description'] or '',
                starlight=nr['starlight'] or '',
                assigned_star=nr['assigned_star'],
                status=StarStatus(nr['status']),
                priority=StarPriority(nr['priority']),
                created_at=datetime.fromisoformat(nr['created_at']),
                updated_at=datetime.fromisoformat(nr['updated_at']),
                result_starlight=nr['result_starlight'],
                echo=nr['echo'],
                error=nr['error']
            )
            
            # 加载日志
            cursor.execute(
                "SELECT * FROM starlight_logs WHERE nova_id = ? ORDER BY id",
                (nova.id,)
            )
            for lr in cursor.fetchall():
                nova.starlight_log.append({
                    'timestamp': lr['timestamp'],
                    'role': lr['role'],
                    'content': lr['content']
                })
            
            novas.append(nova)
        
        conn.close()
        
        constellation = Constellation(
            id=row['id'],
            name=row['name'],
            description=row['description'] or '',
            status=ConstellationStatus(row['status']),
            execution_mode=row['execution_mode'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
        constellation.novas = novas
        
        return constellation
    
    def load_all_constellations(self) -> list[Constellation]:
        """加载所有星座"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM constellations ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        constellations = []
        for row in rows:
            c = self.load_constellation(row['id'])
            if c:
                constellations.append(c)
        
        return constellations


class ResultComparator:
    """
    结果对比器 - 对比多个 Agent 的执行结果
    
    提供文本相似度计算、差异分析等功能
    """
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（0-1）
        
        使用 Jaccard 相似系数（基于词汇）
        """
        if not text1 or not text2:
            return 0.0
        
        # 简单词汇级 Jaccard
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        intersection = words1 & words2
        union = words1 | words2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    @staticmethod
    def calculate_levenshtein_similarity(text1: str, text2: str) -> float:
        """
        使用编辑距离计算相似度
        
        返回 0-1 的相似度，1 表示完全相同
        """
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0
        
        len1, len2 = len(text1), len(text2)
        
        # 动态规划计算编辑距离
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j
        
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if text1[i-1] == text2[j-1] else 1
                dp[i][j] = min(
                    dp[i-1][j] + 1,      # 删除
                    dp[i][j-1] + 1,      # 插入
                    dp[i-1][j-1] + cost  # 替换
                )
        
        distance = dp[len1][len2]
        max_len = max(len1, len2)
        
        return 1.0 - (distance / max_len) if max_len > 0 else 1.0
    
    @staticmethod
    def find_common_parts(texts: list[str]) -> list[str]:
        """
        找出多个文本的共同部分
        
        返回公共子句列表
        """
        if not texts:
            return []
        if len(texts) == 1:
            return [texts[0]]
        
        # 使用最短文本作为基准，找公共子串
        shortest = min(texts, key=len)
        common_parts = []
        
        # 简单的行级对比
        lines_by_text = [set(t.split('\n')) for t in texts]
        common_lines = lines_by_text[0]
        for lines in lines_by_text[1:]:
            common_lines &= lines
        
        return list(common_lines)
    
    @staticmethod
    def compare_novas(novas: list[Nova]) -> dict:
        """
        对比多个新星的结果
        
        Args:
            novas: 新星列表（通常来自同一星座的不同新星）
            
        Returns:
            对比结果字典
        """
        results = []
        for nova in novas:
            if nova.result_starlight:
                results.append(nova.result_starlight)
        
        if len(results) < 2:
            return {
                "novas": [{"id": n.id, "title": n.title, "status": n.status.value} for n in novas],
                "comparison": "需要至少两个结果才能对比"
            }
        
        # 计算两两相似度
        similarities = []
        pairs = []
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                sim = ResultComparator.calculate_similarity(results[i], results[j])
                lev_sim = ResultComparator.calculate_levenshtein_similarity(results[i], results[j])
                similarities.append({"pair": (i, j), "jaccard": sim, "levenshtein": lev_sim})
                pairs.append(f"{novas[i].id}-{novas[j].id}")
        
        # 找共同部分
        common_parts = ResultComparator.find_common_parts(results)
        
        # 统计各新星的输出长度
        output_lengths = [(novas[i].id, len(r)) for i, r in enumerate(results)]
        
        return {
            "novas": [
                {
                    "id": n.id,
                    "title": n.title,
                    "assigned_star": n.assigned_star,
                    "status": n.status.value,
                    "output_length": len(n.result_starlight) if n.result_starlight else 0,
                    "preview": (n.result_starlight or "")[:200]
                }
                for n in novas
            ],
            "similarities": similarities,
            "pairs": pairs,
            "average_similarity": sum(s['jaccard'] for s in similarities) / len(similarities) if similarities else 0,
            "average_levenshtein": sum(s['levenshtein'] for s in similarities) / len(similarities) if similarities else 0,
            "common_parts": common_parts,
            "output_lengths": output_lengths
        }
