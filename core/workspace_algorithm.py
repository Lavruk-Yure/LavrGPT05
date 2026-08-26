# -*- coding: utf-8 -*-
"""Base contract for algorithms hosted by one Algorithm Workspace."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeAlias

from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_runtime_requirements import WorkspaceWarmupRequirement
from core.workspace_signal import WorkspaceSignalProposal

if TYPE_CHECKING:
    from core.workspace_chart import WorkspaceChartSeries
    from core.workspace_runtime import WorkspaceRuntimeContext

_SignalIterable: TypeAlias = Iterable[WorkspaceSignalProposal]
WorkspaceSignalOutput: TypeAlias = WorkspaceSignalProposal | _SignalIterable | None


class WorkspaceAlgorithmError(RuntimeError):
    """Invalid algorithm lifecycle or output."""


class WorkspaceAlgorithm(ABC):
    """Canonical algorithm contract used by Replay and future live modes."""

    @abstractmethod
    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        """Bind immutable WSP identity and per-workspace parameters."""

    @abstractmethod
    def start(self) -> None:
        """Start local algorithm processing without placing broker orders."""

    @abstractmethod
    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        """Process one canonical market event and optionally propose signals."""

    def warmup_requirements(
        self,
    ) -> tuple[WorkspaceWarmupRequirement, ...] | None:
        """Return computed component requirements or None for legacy mode."""
        return None

    def chart_series(
        self,
        timestamps: tuple[datetime, ...],
    ) -> tuple[WorkspaceChartSeries, ...]:
        """Return bounded factual series for active or stopped chart review."""
        _ = timestamps
        return ()

    @abstractmethod
    def on_order_event(self, event: object) -> None:
        """Receive a future broker-neutral order event."""

    @abstractmethod
    def stop(self) -> None:
        """Stop local processing without closing broker positions."""


class PassiveWorkspaceAlgorithm(WorkspaceAlgorithm):
    """Safe default until a concrete algorithm is registered."""

    def __init__(self, algorithm_id: str) -> None:
        self.algorithm_id = str(algorithm_id or "").strip()
        self.context: WorkspaceRuntimeContext | None = None
        self.parameters: dict[str, Any] = {}
        self.started = False

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        self.context = context
        self.parameters = dict(parameters)

    def start(self) -> None:
        if self.context is None:
            raise WorkspaceAlgorithmError("Algorithm is not configured")
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        _ = event
        if not self.started:
            raise WorkspaceAlgorithmError("Algorithm is not started")
        return None

    def on_order_event(self, event: object) -> None:
        _ = event
        if not self.started:
            raise WorkspaceAlgorithmError("Algorithm is not started")

    def stop(self) -> None:
        self.started = False


def create_workspace_algorithm(algorithm_id: str) -> WorkspaceAlgorithm:
    """Return the safe default implementation for an unregistered algorithm."""
    return PassiveWorkspaceAlgorithm(algorithm_id)


def create_registered_workspace_algorithm(
    algorithm_id: str,
) -> WorkspaceAlgorithm:
    """Return the production WSP algorithm or the passive fallback."""
    normalized_id = str(algorithm_id or "").strip().upper()
    if normalized_id in {"RAILALGORITHM", "MACD_ALLIGATOR_REPLAY"}:
        from core.workspace_alligator import (
            WorkspaceMacdAlligatorReplayAlgorithm,
        )

        return WorkspaceMacdAlligatorReplayAlgorithm(algorithm_id)
    return create_workspace_algorithm(algorithm_id)


def normalize_signal_output(
    output: WorkspaceSignalOutput,
) -> tuple[WorkspaceSignalProposal, ...]:
    """Normalize one algorithm callback result into validated proposals."""
    if output is None:
        return ()
    if isinstance(output, WorkspaceSignalProposal):
        return (output,)
    try:
        proposals = tuple(output)
    except TypeError as exc:
        raise WorkspaceAlgorithmError(
            "on_market_event must return signal proposals or None"
        ) from exc
    if not all(isinstance(proposal, WorkspaceSignalProposal) for proposal in proposals):
        raise WorkspaceAlgorithmError(
            "on_market_event returned an invalid signal proposal"
        )
    return proposals
