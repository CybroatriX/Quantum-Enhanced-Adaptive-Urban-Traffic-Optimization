"""Dynamic traffic event manager for simulating real-world urban disruptions."""

from __future__ import annotations

import copy
import logging
from time import time
from typing import Any, Mapping, Sequence

from perception.models import TrafficObservation, VALID_APPROACHES
from simulation.models.events import DynamicEvent, EventMetrics, EventStatus, EventType

logger = logging.getLogger(__name__)


class DynamicEventManager:
    """Manages dynamic real-world traffic events across multi-intersection networks."""

    def __init__(self, managed_intersection_ids: Sequence[str] | None = None) -> None:
        self.managed_ids = set(managed_intersection_ids) if managed_intersection_ids else set()
        self._events: dict[str, DynamicEvent] = {}
        self._cancelled_event_ids: set[str] = set()
        self._event_metrics: dict[str, EventMetrics] = {}

    def register_event(
        self,
        event: DynamicEvent | Mapping[str, Any],
        current_time: float | None = None,
    ) -> tuple[bool, str, DynamicEvent | None]:
        """Validate and register a new dynamic traffic event.

        Returns:
            (success, status_message, registered_event_or_None)
        """
        now = current_time if current_time is not None else time()

        # Parse & Validate
        try:
            if isinstance(event, DynamicEvent):
                ev = event
            elif isinstance(event, (dict, Mapping)):
                ev = DynamicEvent.from_dict(event)
            else:
                return False, f"Unsupported event format: {type(event)}", None
        except ValueError as err:
            return False, f"Validation error: {err}", None

        # Check network membership if managed_ids configured
        if self.managed_ids:
            unknown = [iid for iid in ev.affected_intersection_ids if iid not in self.managed_ids]
            if unknown:
                return False, f"Unknown intersection IDs: {unknown}", None

        # Check freshness / expiration
        if ev.end_time < now:
            return False, f"Event is already expired (end_time={ev.end_time} < now={now})", None

        # Handle duplicate event ID
        if ev.event_id in self._events:
            existing = self._events[ev.event_id]
            if existing == ev:
                logger.info("Duplicate identical event registration '%s' accepted idempotently.", ev.event_id)
                return True, "Duplicate identical event registered idempotently", ev
            else:
                logger.info("Updating existing event '%s' with new parameters.", ev.event_id)

        # Clear from cancelled set if re-registered
        self._cancelled_event_ids.discard(ev.event_id)
        self._events[ev.event_id] = ev

        # Initialize tracking metrics
        self._event_metrics[ev.event_id] = EventMetrics(
            event_id=ev.event_id,
            event_type=ev.event_type,
            affected_intersections=list(ev.affected_intersection_ids),
            start_time=ev.start_time,
            end_time=ev.end_time,
        )

        status_str = "active" if ev.is_active_at(now) else "scheduled"
        return True, f"Event '{ev.event_id}' registered successfully ({status_str})", ev

    def cancel_event(self, event_id: str, current_time: float | None = None) -> bool:
        """Cancel an active or scheduled event by ID."""
        eid = str(event_id).strip()
        if eid in self._events:
            now = current_time if current_time is not None else time()
            self._cancelled_event_ids.add(eid)
            ev = self._events[eid]
            if eid in self._event_metrics:
                m = self._event_metrics[eid]
                m.activation_duration = max(0.0, now - ev.start_time)
            return True
        return False

    def get_event(self, event_id: str) -> DynamicEvent | None:
        """Retrieve an event by ID if registered and not cancelled."""
        eid = str(event_id).strip()
        if eid in self._cancelled_event_ids:
            return None
        return self._events.get(eid)

    def get_event_status(self, event_id: str, current_time: float | None = None) -> EventStatus | None:
        """Get the current lifecycle status of an event."""
        eid = str(event_id).strip()
        if eid not in self._events:
            return None
        if eid in self._cancelled_event_ids:
            return EventStatus.CANCELLED
        now = current_time if current_time is not None else time()
        return self._events[eid].status_at(now)

    def get_all_events(
        self,
        active_only: bool = False,
        intersection_id: str | None = None,
        current_time: float | None = None,
    ) -> list[DynamicEvent]:
        """List registered events with optional filtering."""
        now = current_time if current_time is not None else time()
        results: list[DynamicEvent] = []

        for eid, ev in self._events.items():
            if eid in self._cancelled_event_ids:
                continue
            if active_only and not ev.is_active_at(now):
                continue
            if intersection_id is not None and str(intersection_id) not in ev.affected_intersection_ids:
                continue
            results.append(ev)

        return results

    def get_active_events_for_intersection(
        self,
        intersection_id: str,
        current_time: float | None = None,
    ) -> list[DynamicEvent]:
        """Get all currently active events impacting a given intersection."""
        return self.get_all_events(
            active_only=True,
            intersection_id=intersection_id,
            current_time=current_time,
        )

    def has_active_events(
        self,
        intersection_id: str,
        current_time: float | None = None,
    ) -> bool:
        """Quick check if an intersection is affected by active events."""
        return len(self.get_active_events_for_intersection(intersection_id, current_time)) > 0

    def apply_to_observation(
        self,
        observation: TrafficObservation,
        current_time: float | None = None,
        base_road_capacity: int = 100,
    ) -> tuple[TrafficObservation, int, dict[str, Any]]:
        """Apply active dynamic events to transform an observation into an effective state.

        Preserves the canonical TrafficObservation contract while computing
        effective queues, vehicle counts, and road capacity.

        Returns:
            (effective_observation, effective_road_capacity, event_metadata)
        """
        now = current_time if current_time is not None else observation.timestamp
        iid = observation.intersection_id
        active_events = self.get_active_events_for_intersection(iid, current_time=now)

        if not active_events:
            # No events: return un-modified observation and baseline capacity
            return observation, base_road_capacity, {
                "events_applied": False,
                "active_event_ids": [],
                "effective_capacity": base_road_capacity,
                "min_pedestrian_green": 0,
            }

        # Clone approach queues and counts to compute effective impact
        eff_queues = dict(observation.queue_lengths)
        eff_approaches = dict(observation.approach_counts)
        eff_vehicle_count = int(observation.vehicle_count)

        min_capacity_factor = 1.0
        max_ped_green = 0
        applied_event_ids: list[str] = []
        applied_event_types: list[str] = []

        for ev in active_events:
            applied_event_ids.append(ev.event_id)
            applied_event_types.append(ev.event_type)

            # 1. Capacity impact
            min_capacity_factor = min(min_capacity_factor, ev.capacity_factor)

            # 2. Pedestrian demand
            if ev.min_pedestrian_green > max_ped_green:
                max_ped_green = ev.min_pedestrian_green

            # 3. Approach queues and counts
            for app in ev.affected_approaches:
                if app in eff_queues:
                    # Apply queue adder
                    eff_queues[app] = max(0, eff_queues[app] + ev.queue_adder)
                    # Apply demand multiplier
                    if ev.demand_multiplier != 1.0:
                        eff_queues[app] = int(round(eff_queues[app] * ev.demand_multiplier))
                    # Adjust approach counts proportionally
                    eff_approaches[app] = max(eff_queues[app], eff_approaches[app] + ev.queue_adder)

        # Update total effective vehicle count
        new_total_queue = sum(eff_queues.values())
        eff_vehicle_count = max(eff_vehicle_count, new_total_queue + 2)

        # Compute effective road capacity
        effective_capacity = max(5, int(round(base_road_capacity * min_capacity_factor)))

        # Construct new effective TrafficObservation conforming to canonical schema
        effective_obs = TrafficObservation(
            timestamp=observation.timestamp,
            source=f"{observation.source}_event_adapted",
            intersection_id=observation.intersection_id,
            vehicle_count=eff_vehicle_count,
            approach_counts=eff_approaches,
            queue_lengths=eff_queues,
            class_counts=dict(observation.class_counts),
            detections=observation.detections,
            tracking_available=observation.tracking_available,
            tracked_vehicle_count=eff_vehicle_count,
            average_confidence=observation.average_confidence,
        )

        metadata = {
            "events_applied": True,
            "active_event_ids": applied_event_ids,
            "active_event_types": applied_event_types,
            "effective_capacity": effective_capacity,
            "capacity_factor": round(min_capacity_factor, 2),
            "min_pedestrian_green": max_ped_green,
            "original_queues": dict(observation.queue_lengths),
            "effective_queues": eff_queues,
        }

        # Update event metrics
        for eid in applied_event_ids:
            if eid in self._event_metrics:
                m = self._event_metrics[eid]
                m.queues_during[iid] = new_total_queue
                m.signal_overrides_count += 1

        return effective_obs, effective_capacity, metadata

    def get_metrics(self, event_id: str) -> EventMetrics | None:
        """Retrieve evaluation metrics for an event."""
        return self._event_metrics.get(event_id)

    def get_all_metrics(self) -> dict[str, EventMetrics]:
        """Retrieve all recorded event metrics."""
        return dict(self._event_metrics)
