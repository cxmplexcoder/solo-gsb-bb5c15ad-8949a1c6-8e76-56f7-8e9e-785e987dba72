"""API 请求 / 响应数据模型（Pydantic v2）。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Phase = Literal["A", "B", "C"]
TimeSlot = Literal["morning", "evening"]

_PHASE_ORDER = {"A": 0, "B": 1, "C": 2}
_SLOT_ORDER = {"morning": 0, "evening": 1}


class Capacities(BaseModel):
    """A/B/C 各相容量（非负整数）。"""

    A: int = Field(..., ge=0, description="A 相容量")
    B: int = Field(..., ge=0, description="B 相容量")
    C: int = Field(..., ge=0, description="C 相容量")


class DeviceIn(BaseModel):
    """单台待分配设备。"""

    id: str = Field(..., min_length=1, max_length=64, description="设备唯一编号")
    power: int = Field(..., gt=0, description="设备功率（正整数）")
    allowed_phases: list[Phase] = Field(
        ..., min_length=1, description="可接入相位集合，非空，元素取自 A/B/C"
    )

    @field_validator("allowed_phases")
    @classmethod
    def _dedupe_and_order(cls, value: list[str]) -> list[str]:
        """去重并按 A/B/C 固定顺序排列。"""
        return sorted(set(value), key=_PHASE_ORDER.__getitem__)


class CalculationRequest(BaseModel):
    """创建一次排布计算的请求体。"""

    capacities: Capacities
    devices: list[DeviceIn] = Field(
        ..., min_length=1, max_length=12, description="设备列表，1~12 台"
    )

    @model_validator(mode="after")
    def _unique_device_ids(self) -> "CalculationRequest":
        ids = [d.id for d in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("设备编号必须唯一")
        return self


class Loads(BaseModel):
    """A/B/C 各相负载。"""

    A: int
    B: int
    C: int


class AssignmentItem(BaseModel):
    """单台设备的分配结果。"""

    device_id: str
    phase: Phase


class CalculationSummary(BaseModel):
    """计算记录摘要（列表接口使用）。"""

    id: int
    created_at: str
    capacities: Loads
    feasible: bool
    imbalance: Optional[int] = None
    loads: Optional[Loads] = None


class CalculationResult(CalculationSummary):
    """计算结果（创建接口返回）。"""

    message: str
    assignments: list[AssignmentItem]


class DeviceRecord(BaseModel):
    """持久化的设备输入及其分配结果。"""

    device_id: str
    power: int
    allowed_phases: list[str]
    assigned_phase: Optional[Phase] = None


class CalculationDetail(CalculationResult):
    """计算记录详情（含原始输入）。"""

    devices: list[DeviceRecord]


class CapacityUpgradeResult(BaseModel):
    """容量扩容建议结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    original_capacities: Loads = Field(..., description="原各相容量")
    capacity_upgrades: Loads = Field(..., description="各相需要增加的非负整数容量")
    suggested_capacities: Loads = Field(..., description="扩容后的建议容量")
    total_upgrade: int = Field(..., ge=0, description="三相扩容总量")
    max_upgrade: int = Field(..., ge=0, description="单相最大扩容量")
    assignments: list[AssignmentItem] = Field(..., description="扩容后的设备分配")
    loads: Loads = Field(..., description="建议容量下各相的实际负载")
    message: str


class RobustDeviceIn(BaseModel):
    """稳健预演的单台设备：功率为正整数区间 [min_power, max_power]。"""

    id: str = Field(..., min_length=1, max_length=64, description="设备唯一编号")
    min_power: int = Field(..., gt=0, description="功率下界（正整数）")
    max_power: int = Field(..., gt=0, description="功率上界（正整数）")
    allowed_phases: list[Phase] = Field(
        ..., min_length=1, description="可接入相位集合，非空，元素取自 A/B/C"
    )

    @field_validator("allowed_phases")
    @classmethod
    def _dedupe_and_order(cls, value: list[str]) -> list[str]:
        """去重并按 A/B/C 固定顺序排列。"""
        return sorted(set(value), key=_PHASE_ORDER.__getitem__)

    @model_validator(mode="after")
    def _min_not_above_max(self) -> "RobustDeviceIn":
        if self.min_power > self.max_power:
            raise ValueError("功率下界不能大于上界")
        return self


class RobustRehearsalRequest(BaseModel):
    """稳健分相预演请求体（仅预演，不写入历史计算记录）。"""

    capacities: Capacities
    devices: list[RobustDeviceIn] = Field(
        ..., min_length=1, max_length=12, description="设备列表，1~12 台"
    )

    @model_validator(mode="after")
    def _unique_device_ids(self) -> "RobustRehearsalRequest":
        ids = [d.id for d in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("设备编号必须唯一")
        return self


class RobustRehearsalResult(BaseModel):
    """稳健分相预演结果。"""

    capacities: Loads = Field(..., description="各相容量（回显请求输入）")
    feasible: bool = Field(..., description="是否存在稳健可行分配")
    worst_imbalance: Optional[int] = Field(
        None, description="任意功率组合下三相最大负载与最小负载之差的最大值"
    )
    load_lower_bounds: Optional[Loads] = Field(
        None, description="各相负载下界（该相设备均取功率下界之和）"
    )
    load_upper_bounds: Optional[Loads] = Field(
        None, description="各相负载上界（该相设备均取功率上界之和）"
    )
    assignments: list[AssignmentItem] = Field(
        ..., description="稳健分配方案（按设备编号排序）；无解时为空"
    )
    message: str


class StartupPowerIn(BaseModel):
    """单台设备的启动瞬时功率。"""

    device_id: str = Field(
        ..., min_length=1, max_length=64, description="设备编号，须与计算记录一致"
    )
    startup_power: int = Field(
        ..., gt=0, description="启动瞬时功率（正整数，不低于该设备额定功率）"
    )


class StartupPlanRequest(BaseModel):
    """启动顺序预演请求体（仅预演，不修改历史计算记录）。"""

    startup_powers: list[StartupPowerIn] = Field(
        ...,
        min_length=1,
        max_length=12,
        description="逐台设备的启动瞬时功率，设备编号须与记录完全一致",
    )

    @model_validator(mode="after")
    def _unique_device_ids(self) -> "StartupPlanRequest":
        ids = [d.device_id for d in self.startup_powers]
        if len(ids) != len(set(ids)):
            raise ValueError("设备编号必须唯一")
        return self


class StartupStep(BaseModel):
    """启动顺序中的一步：某台设备的启动瞬间与其后的稳定状态。"""

    device_id: str
    phase: Phase
    rated_power: int = Field(..., description="额定功率")
    startup_power: int = Field(..., description="启动瞬时功率")
    transient_loads: Loads = Field(..., description="启动瞬间各相负载")
    transient_imbalance: int = Field(
        ..., description="启动瞬间三相负载最大值与最小值之差"
    )
    steady_loads: Loads = Field(..., description="启动完成后各相稳定负载")
    steady_imbalance: int = Field(
        ..., description="稳定状态三相负载最大值与最小值之差"
    )


class StartupPlanResult(BaseModel):
    """启动顺序预演结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    capacities: Loads = Field(..., description="各相容量（沿用原计算记录）")
    feasible: bool = Field(..., description="是否存在安全启动顺序")
    peak_imbalance: Optional[int] = Field(
        None, description="全过程三相负载最大值与最小值之差的峰值"
    )
    startup_order: list[str] = Field(
        ..., description="启动顺序（设备编号）；无安全顺序时为空"
    )
    steps: list[StartupStep] = Field(
        ..., description="逐步的瞬时与稳定负载；无安全顺序时为空"
    )
    message: str


class FaultMigrationItem(BaseModel):
    """一台故障相设备的迁移结果。"""

    device_id: str
    power: int = Field(..., description="设备功率（正整数）")
    from_phase: Phase = Field(..., description="原接入相位（即故障相）")
    to_phase: Phase = Field(..., description="迁入的健康相（A/B/C）")


class FaultDisconnectedItem(BaseModel):
    """一台被断开的故障相设备。"""

    device_id: str
    power: int = Field(..., description="设备功率（正整数）")
    phase: Phase = Field(..., description="原接入相位（即故障相）")


class PhaseFaultRehearsalResult(BaseModel):
    """单相故障保供预演结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    fault_phase: Phase = Field(..., description="故障相（A/B/C）")
    capacities: Loads = Field(..., description="各相容量（沿用原计算记录）")
    original_loads: Loads = Field(..., description="故障前各相负载（原记录分配）")
    loads: Loads = Field(
        ..., description="预演后各相负载（健康相设备不动 + 迁入设备；故障相为 0）"
    )
    migrations: list[FaultMigrationItem] = Field(
        ..., description="迁至健康相的故障相设备（按设备编号排序）"
    )
    disconnected: list[FaultDisconnectedItem] = Field(
        ..., description="被断开的故障相设备（按设备编号排序）"
    )
    retained_power: int = Field(
        ..., ge=0, description="保留设备的总功率（健康相不动设备 + 迁移设备）"
    )
    retained_count: int = Field(
        ..., ge=0, description="保留设备数（健康相不动设备 + 迁移设备）"
    )
    disconnected_power: int = Field(..., ge=0, description="断开设备的总功率")
    disconnected_count: int = Field(..., ge=0, description="断开设备数")
    message: str


class DeviceAdditionRequest(BaseModel):
    """新增设备接入预演请求体（仅预演，不修改历史计算记录）。"""

    devices: list[DeviceIn] = Field(
        ...,
        min_length=1,
        max_length=12,
        description="新增设备列表，1~12 台；编号不得与记录中已有设备重复，"
        "且新旧设备总数不得超过 12 台",
    )

    @model_validator(mode="after")
    def _unique_device_ids(self) -> "DeviceAdditionRequest":
        ids = [d.id for d in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("设备编号必须唯一")
        return self


class AdditionMigrationItem(BaseModel):
    """一台改相的原设备。"""

    device_id: str
    power: int = Field(..., description="设备功率（正整数）")
    from_phase: Phase = Field(..., description="原接入相位（A/B/C）")
    to_phase: Phase = Field(..., description="新接入相位（A/B/C）")


class DeviceAdditionPlanResult(BaseModel):
    """新增设备接入预演结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    capacities: Loads = Field(..., description="各相容量（沿用原计算记录，保持不变）")
    feasible: bool = Field(..., description="是否存在新旧设备全部接入的可行分配")
    imbalance: Optional[int] = Field(
        None, description="三相负载最大值与最小值之差"
    )
    loads: Optional[Loads] = Field(None, description="各相负载（均不超过原容量）")
    migrated_count: Optional[int] = Field(None, description="改相的原设备台数")
    existing_assignments: list[AssignmentItem] = Field(
        ..., description="原设备分配（按设备编号排序）；无解时为空"
    )
    new_assignments: list[AssignmentItem] = Field(
        ..., description="新设备分配（按设备编号排序）；无解时为空"
    )
    migrations: list[AdditionMigrationItem] = Field(
        ..., description="改相的原设备清单（按设备编号排序）；无解时为空"
    )
    message: str


class ShiftDeviceIn(BaseModel):
    """双时段错峰规划的单台设备。"""

    id: str = Field(..., min_length=1, max_length=64, description="设备唯一编号")
    power: int = Field(..., gt=0, description="设备功率（正整数）")
    allowed_phases: list[Phase] = Field(
        ..., min_length=1, description="可接入相位集合，非空，元素取自 A/B/C"
    )
    allowed_slots: list[TimeSlot] = Field(
        ...,
        min_length=1,
        description="允许运行时段集合，非空，元素取自 morning（早）/ evening（晚）",
    )

    @field_validator("allowed_phases")
    @classmethod
    def _dedupe_and_order_phases(cls, value: list[str]) -> list[str]:
        """去重并按 A/B/C 固定顺序排列。"""
        return sorted(set(value), key=_PHASE_ORDER.__getitem__)

    @field_validator("allowed_slots")
    @classmethod
    def _dedupe_and_order_slots(cls, value: list[str]) -> list[str]:
        """去重并按 早/晚 固定顺序排列。"""
        return sorted(set(value), key=_SLOT_ORDER.__getitem__)


class ShiftPlanRequest(BaseModel):
    """双时段错峰接入规划请求体（仅预演，不写入历史计算记录）。"""

    capacities: Capacities = Field(..., description="两时段共用的 A/B/C 相容量")
    devices: list[ShiftDeviceIn] = Field(
        ..., min_length=1, max_length=8, description="设备列表，1~8 台"
    )

    @model_validator(mode="after")
    def _unique_device_ids(self) -> "ShiftPlanRequest":
        ids = [d.id for d in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("设备编号必须唯一")
        return self


class ShiftAssignmentItem(BaseModel):
    """单台设备的错峰安排：恰选一个允许时段与一个允许相位。"""

    device_id: str
    slot: TimeSlot
    phase: Phase


class ShiftSlotPlan(BaseModel):
    """单个时段的三相负载情况。"""

    loads: Loads = Field(..., description="该时段 A/B/C 各相负载")
    total_load: int = Field(..., description="该时段三相负载之和")
    imbalance: int = Field(..., description="该时段三相负载最大值与最小值之差")


class ShiftSlots(BaseModel):
    """早、晚两个时段的三相负载情况。"""

    morning: ShiftSlotPlan = Field(..., description="早时段三相负载情况")
    evening: ShiftSlotPlan = Field(..., description="晚时段三相负载情况")


class ShiftPlanResult(BaseModel):
    """双时段错峰接入规划结果（仅预演，不写入历史计算记录）。"""

    capacities: Loads = Field(..., description="两时段共用的各相容量（回显请求输入）")
    feasible: bool = Field(..., description="是否存在可行错峰接入方案")
    peak_total_load: Optional[int] = Field(
        None, description="两时段总负载（三相之和）的较大值（首要优化目标）"
    )
    peak_imbalance: Optional[int] = Field(
        None, description="两时段三相负载差的较大值（次要优化目标）"
    )
    slots: Optional[ShiftSlots] = Field(
        None, description="早、晚两时段各自的三相负载、总负载与负载差；无解时为 null"
    )
    assignments: list[ShiftAssignmentItem] = Field(
        ..., description="设备安排（按设备编号排序）；无解时为空"
    )
    message: str


class PowerLogEventIn(BaseModel):
    """单条设备实际功率变更事件。"""

    device_id: str = Field(
        ..., min_length=1, max_length=64, description="设备编号，须存在于计算记录中"
    )
    timestamp: int = Field(
        ..., description="变更时刻（Unix 秒，须落在左闭右开窗口内）"
    )
    power: int = Field(..., ge=0, description="变更后的实际功率（非负整数）")


class PowerLogReplayRequest(BaseModel):
    """运行功率日志复盘请求体（仅复盘，不修改历史计算记录）。"""

    window_start: int = Field(
        ..., description="窗口起点（Unix 秒，须早于窗口终点）"
    )
    window_end: int = Field(..., description="窗口终点（Unix 秒）")
    events: list[PowerLogEventIn] = Field(
        ...,
        max_length=200,
        description="设备功率变更事件，0~200 条；窗口起点所有设备功率为 0，"
        "事件时刻须落在左闭右开窗口内，同一设备同一时刻不得重复",
    )

    @model_validator(mode="after")
    def _window_ordered(self) -> "PowerLogReplayRequest":
        if self.window_start >= self.window_end:
            raise ValueError("窗口起点须早于窗口终点")
        return self

    @model_validator(mode="after")
    def _events_in_window_and_unique(self) -> "PowerLogReplayRequest":
        seen: set[tuple[str, int]] = set()
        for event in self.events:
            if not self.window_start <= event.timestamp < self.window_end:
                raise ValueError(
                    f"事件时刻须落在左闭右开窗口 "
                    f"[{self.window_start}, {self.window_end}) 内："
                    f"设备 {event.device_id} 时刻 {event.timestamp}"
                )
            key = (event.device_id, event.timestamp)
            if key in seen:
                raise ValueError(
                    f"同一设备同一时刻不得重复："
                    f"设备 {event.device_id} 时刻 {event.timestamp}"
                )
            seen.add(key)
        return self


class PowerLogAlertItem(BaseModel):
    """一段超容告警：连续存在任一相超容的合并区间（左闭右开）。"""

    start: int = Field(..., description="告警区间起点（Unix 秒）")
    end: int = Field(..., description="告警区间终点（Unix 秒）")
    max_overload: Loads = Field(
        ...,
        description="告警区间内各相最大超额量（负载超出容量的最大值，未超容相为 0）",
    )


class PowerLogReplayResult(BaseModel):
    """运行功率日志复盘结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    capacities: Loads = Field(..., description="各相容量（沿用原计算记录）")
    window_start: int = Field(..., description="窗口起点（Unix 秒）")
    window_end: int = Field(..., description="窗口终点（Unix 秒）")
    alerts: list[PowerLogAlertItem] = Field(
        ..., description="合并后的超容告警（按起点升序）；无告警时为空"
    )
    peak_loads: Loads = Field(..., description="全窗口各相峰值负载")
    message: str


class CableSegmentIn(BaseModel):
    """单台设备所需的一整段电缆（不可拼接）。"""

    device_id: str = Field(
        ..., min_length=1, max_length=64, description="设备编号，须与计算记录一致"
    )
    length: int = Field(..., gt=0, description="该设备所需电缆段长度（正整数）")


class CableReelIn(BaseModel):
    """一个库存电缆盘。"""

    id: str = Field(..., min_length=1, max_length=64, description="电缆盘唯一编号")
    length: int = Field(..., gt=0, description="电缆盘长度（正整数）")


class CableCuttingRequest(BaseModel):
    """电缆盘裁切预演请求体（仅预演，不修改历史计算记录）。"""

    segments: list[CableSegmentIn] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="逐台设备给出的电缆段长度，设备编号须与记录完全一致（1~8 段）",
    )
    reels: list[CableReelIn] = Field(
        ...,
        max_length=8,
        description="库存电缆盘，0~8 个，编号唯一、长度为正整数；无盘时无解",
    )
    cut_loss: int = Field(
        ..., ge=0, description="同一盘上每个相邻切口的切割损耗（非负整数）"
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> "CableCuttingRequest":
        segment_ids = [s.device_id for s in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("电缆段的设备编号必须唯一")
        reel_ids = [r.id for r in self.reels]
        if len(reel_ids) != len(set(reel_ids)):
            raise ValueError("电缆盘编号必须唯一")
        return self


class CableCutItem(BaseModel):
    """某盘上裁给一台设备的一段电缆。"""

    device_id: str = Field(..., description="设备编号")
    length: int = Field(..., description="电缆段长度（正整数）")


class CableReelPlanItem(BaseModel):
    """单个启用盘的裁切清单。"""

    reel_id: str = Field(..., description="电缆盘编号")
    reel_length: int = Field(..., description="电缆盘原长度")
    cuts: list[CableCutItem] = Field(
        ..., description="本盘的裁切清单（按设备编号排序），每段电缆不可拼接"
    )
    occupied: int = Field(
        ...,
        description="占用长度 = 各段长度之和 +（段数 - 1）·切割损耗，不超过盘长",
    )
    remaining: int = Field(..., ge=0, description="剩余长度 = 盘长 - 占用长度")


class CableCuttingResultResponse(BaseModel):
    """电缆盘裁切预演结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    cut_loss: int = Field(..., ge=0, description="每个相邻切口的切割损耗")
    feasible: bool = Field(..., description="是否存在可裁出全部电缆段的方案")
    reel_count: Optional[int] = Field(
        None, description="启用盘数（首要优化目标）；无解时为 null"
    )
    reel_total_length: Optional[int] = Field(
        None, description="启用盘总长度（次要优化目标）；无解时为 null"
    )
    reel_sequence: list[str] = Field(
        ...,
        description="按设备编号排序后各设备所用电缆盘编号序列；无解时为空",
    )
    reel_plans: list[CableReelPlanItem] = Field(
        ..., description="各启用盘的裁切清单与剩余长度（按电缆盘编号排序）；无解时为空"
    )
    message: str


class CableRouteEdgeIn(BaseModel):
    """一条无向边（端点节点编号、正整数长度、可容纳电缆数 0~4）。"""

    u: int = Field(..., ge=0, description="边端点节点编号（0 至 node_count-1）")
    v: int = Field(..., ge=0, description="边端点节点编号（0 至 node_count-1）")
    length: int = Field(..., gt=0, description="边长度（正整数）")
    capacity: int = Field(..., ge=0, le=4, description="可容纳电缆数（0~4）")

    @model_validator(mode="after")
    def _no_self_loop(self) -> "CableRouteEdgeIn":
        if self.u == self.v:
            raise ValueError("边不得为自环：两端节点编号须不同")
        return self


class CableRoutePhaseStarts(BaseModel):
    """各相起点节点编号。"""

    A: int = Field(..., ge=0, description="A 相起点节点编号")
    B: int = Field(..., ge=0, description="B 相起点节点编号")
    C: int = Field(..., ge=0, description="C 相起点节点编号")


class CableRouteTerminalIn(BaseModel):
    """一台设备的终点节点。"""

    device_id: str = Field(
        ..., min_length=1, max_length=64, description="设备编号，须与计算记录一致"
    )
    node: int = Field(..., ge=0, description="终点节点编号（0 至 node_count-1）")


class CableRoutesRequest(BaseModel):
    """电缆路由预演请求体（仅预演，不修改历史计算记录）。"""

    node_count: int = Field(
        ..., ge=1, le=6, description="节点数（1~6），节点编号 0 至 node_count-1"
    )
    edges: list[CableRouteEdgeIn] = Field(
        ..., max_length=8, description="无向边，0~8 条；无自环、无重复"
    )
    phase_starts: CableRoutePhaseStarts = Field(..., description="各相起点节点编号")
    terminals: list[CableRouteTerminalIn] = Field(
        ...,
        min_length=1,
        max_length=4,
        description="逐台设备的终点节点，设备编号须与记录完全一致（1~4 台）",
    )

    @model_validator(mode="after")
    def _validate_graph(self) -> "CableRoutesRequest":
        n = self.node_count
        seen: set[tuple[int, int]] = set()
        for edge in self.edges:
            if edge.u >= n or edge.v >= n:
                raise ValueError(
                    f"边端点节点编号须在 0 至 {n - 1} 之间：({edge.u}, {edge.v})"
                )
            key = (min(edge.u, edge.v), max(edge.u, edge.v))
            if key in seen:
                raise ValueError(f"无向边不得重复：({edge.u}, {edge.v})")
            seen.add(key)
        for phase, node in (
            ("A", self.phase_starts.A),
            ("B", self.phase_starts.B),
            ("C", self.phase_starts.C),
        ):
            if node >= n:
                raise ValueError(
                    f"{phase} 相起点节点编号须在 0 至 {n - 1} 之间：{node}"
                )
        ids = [t.device_id for t in self.terminals]
        if len(ids) != len(set(ids)):
            raise ValueError("终点映射的设备编号必须唯一")
        for terminal in self.terminals:
            if terminal.node >= n:
                raise ValueError(
                    f"终点节点编号须在 0 至 {n - 1} 之间："
                    f"设备 {terminal.device_id} 的节点 {terminal.node}"
                )
        return self


class CableRouteItem(BaseModel):
    """一台设备的电缆路由结果。"""

    device_id: str
    phase: Phase = Field(..., description="接入相位（沿用原计算记录）")
    path: list[int] = Field(
        ..., description="自所属相起点至终点的无重复节点路径（节点编号序列）"
    )
    length: int = Field(
        ..., ge=0, description="路径长度（途经边长度之和，零边路径为 0）"
    )


class CableRouteEdgeUsageItem(BaseModel):
    """一条边的占用情况。"""

    u: int = Field(..., description="边端点节点编号")
    v: int = Field(..., description="边端点节点编号")
    length: int = Field(..., description="边长度（回显请求输入）")
    capacity: int = Field(..., description="可容纳电缆数（回显请求输入）")
    used: int = Field(
        ..., ge=0, description="最优方案下经过该边的电缆数，不超过容量"
    )


class CableRoutesResultResponse(BaseModel):
    """电缆路由预演结果（原计算记录不做任何修改）。"""

    id: int
    created_at: str
    feasible: bool = Field(..., description="是否存在可行电缆路由方案")
    total_length: Optional[int] = Field(
        None, description="各设备路径长度之和（联合优化目标）；无解时为 null"
    )
    routes: list[CableRouteItem] = Field(
        ..., description="各设备路由（按设备编号排序）；无解时为空"
    )
    edge_usages: list[CableRouteEdgeUsageItem] = Field(
        ..., description="各边占用（与请求边顺序一致）；无解时各边占用为 0"
    )
    message: str
