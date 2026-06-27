"""
異步任務隊列系統
使用 asyncio 和 aioredis（可選）實現後台任務處理
替代 APScheduler，確保主 FastAPI 線程不被阻塞
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from uuid import uuid4
import traceback

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任務狀態"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """任務定義"""
    id: str
    name: str
    handler: Callable
    args: tuple = ()
    kwargs: dict = None
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    created_at: str = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 0  # 0=低, 1=中, 2=高
    scheduled_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.kwargs is None:
            self.kwargs = {}
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        d = asdict(self)
        d['status'] = self.status.value
        d['handler'] = str(self.handler)
        return d


class TaskQueue:
    """
    內存型異步任務隊列
    生產環境可升級為 Redis/RabbitMQ
    """
    def __init__(self, max_workers: int = 10):
        self.queue: asyncio.PriorityQueue = None
        self.tasks: Dict[str, Task] = {}
        self.max_workers = max_workers
        self.workers = []
        self.running = False
        self.result_cache = {}  # 任務結果緩存
    
    async def initialize(self):
        """初始化隊列"""
        self.queue = asyncio.PriorityQueue()
        self.running = True
        
        # 啟動工作線程池
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
        
        logger.info(f"任務隊列已啟動，{self.max_workers} 個工作進程")
    
    async def shutdown(self):
        """關閉隊列"""
        self.running = False
        
        # 等待所有工作進程完成
        for worker in self.workers:
            await worker
        
        logger.info("任務隊列已關閉")
    
    async def submit(self, name: str, handler: Callable, 
                    args: tuple = (), kwargs: dict = None,
                    priority: int = 0, scheduled_time: Optional[datetime] = None) -> str:
        """
        提交任務到隊列
        返回任務 ID
        """
        if kwargs is None:
            kwargs = {}
        
        task_id = str(uuid4())
        task = Task(
            id=task_id,
            name=name,
            handler=handler,
            args=args,
            kwargs=kwargs,
            priority=priority,
            scheduled_time=scheduled_time
        )
        
        self.tasks[task_id] = task
        
        # 如果是定時任務，等待直到指定時間
        if scheduled_time:
            delay = (scheduled_time - datetime.now()).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
        
        # 加入隊列（負數優先級，因為 PriorityQueue 是最小堆）
        await self.queue.put((-priority, task_id))
        
        logger.debug(f"任務已提交: {task_id} ({name})")
        return task_id
    
    async def _worker(self, worker_id: int):
        """工作進程"""
        while self.running:
            try:
                # 從隊列取任務
                try:
                    _, task_id = await asyncio.wait_for(self.queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                
                if task_id not in self.tasks:
                    continue
                
                task = self.tasks[task_id]
                logger.info(f"[Worker-{worker_id}] 開始執行: {task.name} ({task_id})")
                
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now().isoformat()
                
                try:
                    # 執行任務處理函數
                    if asyncio.iscoroutinefunction(task.handler):
                        result = await task.handler(*task.args, **task.kwargs)
                    else:
                        result = task.handler(*task.args, **task.kwargs)
                    
                    task.result = result
                    task.status = TaskStatus.SUCCESS
                    task.completed_at = datetime.now().isoformat()
                    
                    logger.info(f"[Worker-{worker_id}] 完成: {task.name} ({task_id})")
                
                except Exception as e:
                    task.error = str(e)
                    task.retry_count += 1
                    
                    if task.retry_count <= task.max_retries:
                        # 重新加入隊列進行重試
                        task.status = TaskStatus.PENDING
                        await self.queue.put((-task.priority, task_id))
                        logger.warning(
                            f"[Worker-{worker_id}] 任務失敗，準備重試 ({task.retry_count}/{task.max_retries}): "
                            f"{task.name} ({task_id}) - {str(e)}"
                        )
                    else:
                        task.status = TaskStatus.FAILED
                        task.completed_at = datetime.now().isoformat()
                        logger.error(
                            f"[Worker-{worker_id}] 任務失敗（已達重試次數上限）: "
                            f"{task.name} ({task_id})\n{traceback.format_exc()}"
                        )
            
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] 出現異常: {e}\n{traceback.format_exc()}")
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """取得任務狀態"""
        if task_id not in self.tasks:
            return None
        
        task = self.tasks[task_id]
        return task.to_dict()
    
    def get_all_tasks(self, status: Optional[TaskStatus] = None) -> List[Dict]:
        """取得所有任務"""
        result = []
        for task in self.tasks.values():
            if status is None or task.status == status:
                result.append(task.to_dict())
        return result
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任務"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED):
            return False  # 無法取消已完成的任務
        
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now().isoformat()
        return True
    
    def get_queue_stats(self) -> Dict:
        """取得隊列統計"""
        total = len(self.tasks)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        success = sum(1 for t in self.tasks.values() if t.status == TaskStatus.SUCCESS)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        
        return {
            "total": total,
            "pending": pending,
            "running": running,
            "success": success,
            "failed": failed,
            "queue_size": self.queue.qsize() if self.queue else 0,
            "workers": self.max_workers
        }


class ScheduledTaskManager:
    """
    定時任務管理器
    替代 APScheduler，使用 asyncio.create_task + sleep
    """
    def __init__(self, task_queue: TaskQueue):
        self.task_queue = task_queue
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        self.task_definitions: Dict[str, Dict] = {}
    
    def schedule_daily(self, task_id: str, name: str, handler: Callable,
                      hour: int = 14, minute: int = 0, args: tuple = (), 
                      kwargs: dict = None) -> str:
        """
        安排每日定時任務
        """
        self.task_definitions[task_id] = {
            "name": name,
            "handler": handler,
            "hour": hour,
            "minute": minute,
            "args": args,
            "kwargs": kwargs or {}
        }
        
        # 啟動定時任務
        asyncio.create_task(self._run_daily_task(task_id))
        return task_id
    
    async def _run_daily_task(self, task_id: str):
        """執行每日定時任務"""
        if task_id not in self.task_definitions:
            return
        
        definition = self.task_definitions[task_id]
        
        while True:
            # 計算下次執行時間
            now = datetime.now()
            next_run = now.replace(
                hour=definition["hour"],
                minute=definition["minute"],
                second=0,
                microsecond=0
            )
            
            # 如果今天的時間已過，下次執行時間延到明天
            if next_run <= now:
                next_run += timedelta(days=1)
            
            # 等待直到執行時間
            delay = (next_run - datetime.now()).total_seconds()
            logger.info(f"定時任務 {task_id} 將在 {delay:.1f} 秒後執行")
            await asyncio.sleep(delay)
            
            # 提交任務到隊列
            await self.task_queue.submit(
                definition["name"],
                definition["handler"],
                definition["args"],
                definition["kwargs"],
                priority=2  # 定時任務優先級較高
            )
    
    def cancel_scheduled_task(self, task_id: str):
        """取消定時任務"""
        if task_id in self.scheduled_tasks:
            self.scheduled_tasks[task_id].cancel()
            del self.scheduled_tasks[task_id]
        
        if task_id in self.task_definitions:
            del self.task_definitions[task_id]


class AsyncJobRunner:
    """
    異步工作運行器
    提供便捷的任務提交和監控接口
    """
    def __init__(self):
        self.queue = TaskQueue(max_workers=10)
        self.scheduler = ScheduledTaskManager(self.queue)
    
    async def start(self):
        """啟動隊列系統"""
        await self.queue.initialize()
    
    async def stop(self):
        """停止隊列系統"""
        await self.queue.shutdown()
    
    async def run_background(self, name: str, handler: Callable,
                           args: tuple = (), kwargs: dict = None) -> str:
        """運行後台任務"""
        return await self.queue.submit(name, handler, args, kwargs, priority=0)
    
    async def run_high_priority(self, name: str, handler: Callable,
                               args: tuple = (), kwargs: dict = None) -> str:
        """運行高優先級任務"""
        return await self.queue.submit(name, handler, args, kwargs, priority=2)
    
    def schedule_daily(self, task_id: str, name: str, handler: Callable,
                      hour: int = 14, minute: int = 0) -> str:
        """安排每日定時任務"""
        return self.scheduler.schedule_daily(task_id, name, handler, hour, minute)
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """查詢任務狀態"""
        return self.queue.get_task_status(task_id)
    
    def get_stats(self) -> Dict:
        """取得統計信息"""
        return self.queue.get_queue_stats()


# 全局異步任務管理器實例
job_runner = AsyncJobRunner()
