"""Emergency Green Corridor Controller for connected urban intersections.

Coordinates priority green waves for emergency vehicles across multiple intersections
while strictly maintaining non-conflicting phases, yellow/red clearances, and safe phase transitions.
"""

from __future__ import annotations

import logging
from time import time
from typing import Any, Mapping, Sequence

from simulation.models.emergency import (
    CorridorMetrics,
    CorridorPlan,
    CorridorState,
    EmergencyRequest,
    IntersectionPriorityPlan,
)

logger = logging.getLogger(__name__)

# Standard topological approach links for 4-intersection and 8-intersection networks
DEFAULT_TOPOLOGY_LINKS: dict[tuple[str, str], str] = {
    # 4-intersection square: (from_id, to_id) -> approach from which to_id is entered
    ("J1", "J2"): "west",   # Moving East: enters J2 from West
    ("J2", "J1"): "east",
    ("J1", "J3"): "north",  # Moving South: enters J3 from North
    ("J3", "J1"): "south",
    ("J2", "J4"): "north",  # Moving South: enters J4 from North
    ("J4", "J2"): "south",
    ("J3", "J4"): "west",   # Moving East: enters J4 from West
    ("J4", "J3"): "east",
    # 8-intersection grid extension (J5 - J8)
    ("J3", "J5"): "north",
    ("J5", "J3"): "south",
    ("J4", "J6"): "north",
    ("J6", "J4"): "south",
    ("J5", "J6"): "west",
    ("J6", "J5"): "east",
    ("J5", "J7"): "north",
    ("J7", "J5"): "south",
    ("J6", "J8"): "north",
    ("J8", "J6"): "south",
    ("J7", "J8"): "west",
    ("J8", "J7"): "east",
}


def approach_to_phase(approach: str) -> int:
    """Map directional arrival approach to canonical signal green phase."""
    app = approach.lower().strip()
    if app in ("north", "south"):
        return 0  # Phase 0 serves North-South
    elif app in ("east", "west"):
        return 2  # Phase 2 serves East-West
    return 0


class EmergencyGreenCorridorController:
    """Orchestrates multi-intersection emergency green wave priority."""

    def __init__(
        self,
        managed_intersection_ids: Sequence[str] | None = None,
        max_request_age_seconds: float = 120.0,
        emergency_green_seconds: int = 40,
        non_priority_green_seconds: int = 22,
        yellow_seconds: int = 4,
        all_red_seconds: int = 2,
        default_inter_junction_distance_meters: float = 200.0,
        topology_links: Mapping[tuple[str, str], str] | None = None,
    ) -> None:
        self.managed_ids = set(managed_intersection_ids) if managed_intersection_ids else set()
        self.max_request_age_seconds = float(max_request_age_seconds)
        self.emergency_green = int(emergency_green_seconds)
        self.non_priority_green = int(non_priority_green_seconds)
        self.yellow_seconds = int(yellow_seconds)
        self.all_red_seconds = int(all_red_seconds)
        self.default_distance = float(default_inter_junction_distance_meters)
        self.topology_links = dict(topology_links or DEFAULT_TOPOLOGY_LINKS)

        # Active corridors: emergency_vehicle_id -> CorridorPlan
        self._corridors: dict[str, CorridorPlan] = {}
        # Active requests: emergency_vehicle_id -> EmergencyRequest
        self._requests: dict[str, EmergencyRequest] = {}
        # Intersection allocations: intersection_id -> (emergency_vehicle_id, priority_phase)
        self._intersection_allocations: dict[str, tuple[str, int]] = {}

    def get_corridor_plan(self, emergency_vehicle_id: str) -> CorridorPlan | None:
        return self._corridors.get(emergency_vehicle_id)

    def get_active_corridors(self) -> dict[str, CorridorPlan]:
        return {
            k: v for k, v in self._corridors.items() if v.corridor_status == CorridorState.ACTIVE
        }

    def get_active_override(self, intersection_id: str) -> IntersectionPriorityPlan | None:
        """Return the active priority override for an intersection, if currently active."""
        alloc = self._intersection_allocations.get(intersection_id)
        if not alloc:
            return None
        veh_id, _ = alloc
        corridor = self._corridors.get(veh_id)
        if corridor and corridor.corridor_status == CorridorState.ACTIVE:
            plan = corridor.intersection_plans.get(intersection_id)
            if plan and plan.status == CorridorState.ACTIVE:
                return plan
        return None

    def _determine_approach(
        self,
        from_id: str | None,
        to_id: str,
        hints: Mapping[str, str],
        route: Sequence[str],
    ) -> str:
        """Determine arrival approach for intersection to_id along the corridor route."""
        # 1. Check explicit hints
        if to_id in hints:
            return hints[to_id].lower().strip()

        # 2. Check topology link from preceding intersection
        if from_id is not None:
            pair = (from_id, to_id)
            if pair in self.topology_links:
                return self.topology_links[pair]

        # 3. For first intersection, infer from next intersection direction or default
        if len(route) > 1:
            next_pair = (route[0], route[1])
            if next_pair in self.topology_links:
                # If going from J1 to J2 (eastbound), vehicle entered J1 from west
                return self.topology_links[next_pair]

        return "west"

    def request_corridor(
        self,
        request: EmergencyRequest | Mapping[str, Any],
        current_time: float | None = None,
    ) -> CorridorPlan:
        """Validate, resolve conflicts, and activate an emergency green corridor."""
        now = time() if current_time is None else float(current_time)

        # 1. Parse request
        if isinstance(request, EmergencyRequest):
            req = request
        elif isinstance(request, (dict, Mapping)):
            req = EmergencyRequest.from_dict(request)
        else:
            raise ValueError(f"Invalid emergency request format: {type(request)}")

        veh_id = req.emergency_vehicle_id

        # 2. Check freshness / expiration
        age = now - req.timestamp
        if age > self.max_request_age_seconds:
            plan = CorridorPlan(
                emergency_vehicle_id=veh_id,
                corridor_status=CorridorState.EXPIRED,
                affected_intersections=[],
                intersection_plans={},
                validation_result=f"Request expired (age={age:.1f}s > max={self.max_request_age_seconds:.1f}s)",
                is_valid=False,
            )
            self._corridors[veh_id] = plan
            return plan

        # 3. Check route validity
        if not req.route:
            plan = CorridorPlan(
                emergency_vehicle_id=veh_id,
                corridor_status=CorridorState.REJECTED,
                affected_intersections=[],
                intersection_plans={},
                validation_result="Route is empty",
                is_valid=False,
            )
            self._corridors[veh_id] = plan
            return plan

        # Check managed intersections if network is configured
        if self.managed_ids:
            missing_ids = [iid for iid in req.route if iid not in self.managed_ids]
            if missing_ids:
                plan = CorridorPlan(
                    emergency_vehicle_id=veh_id,
                    corridor_status=CorridorState.REJECTED,
                    affected_intersections=[],
                    intersection_plans={},
                    validation_result=f"Route contains unknown intersections: {missing_ids}",
                    is_valid=False,
                )
                self._corridors[veh_id] = plan
                return plan

        # 4. Handle duplicate request from the same vehicle
        if veh_id in self._requests and veh_id in self._corridors:
            existing = self._corridors[veh_id]
            if existing.corridor_status == CorridorState.ACTIVE and existing.affected_intersections == list(req.route):
                logger.info("Duplicate/heartbeat request for active corridor %s", veh_id)
                return existing

        # 5. Conflict Resolution: check for overlapping active corridors on the route
        for idx, iid in enumerate(req.route):
            if iid in self._intersection_allocations:
                active_veh, active_phase = self._intersection_allocations[iid]
                if active_veh != veh_id and active_veh in self._requests:
                    active_req = self._requests[active_veh]
                    # Compute incoming requested phase
                    from_iid = req.route[idx - 1] if idx > 0 else None
                    approach = self._determine_approach(from_iid, iid, req.approach_hints, req.route)
                    req_phase = approach_to_phase(approach)

                    # Only conflict if requested phases differ
                    if req_phase != active_phase:
                        # Deterministic Conflict Hierarchy:
                        # 1. Priority Rank ("critical" > "high" > "medium" > "low")
                        # 2. Timestamp (FIFO)
                        # 3. Lexicographical vehicle_id
                        incoming_wins = False
                        if req.priority_rank > active_req.priority_rank:
                            incoming_wins = True
                        elif req.priority_rank == active_req.priority_rank:
                            if req.timestamp < active_req.timestamp:
                                incoming_wins = True
                            elif req.timestamp == active_req.timestamp:
                                incoming_wins = req.emergency_vehicle_id < active_req.emergency_vehicle_id

                        if not incoming_wins:
                            msg = (
                                f"Preempted by higher/earlier emergency request '{active_veh}' "
                                f"at intersection '{iid}'"
                            )
                            plan = CorridorPlan(
                                emergency_vehicle_id=veh_id,
                                corridor_status=CorridorState.REJECTED,
                                affected_intersections=[],
                                intersection_plans={},
                                validation_result=msg,
                                is_valid=False,
                            )
                            self._corridors[veh_id] = plan
                            return plan
                        else:
                            # Preempt existing lower-priority request
                            logger.info("Preempting lower-priority corridor %s at %s", active_veh, iid)
                            self._release_intersection(iid, active_veh)

        # 6. Build Priority Plans for affected intersections along the route
        intersection_plans: dict[str, IntersectionPriorityPlan] = {}
        affected = list(req.route)
        speed = max(1.0, req.speed_mps)

        cumulative_distance = 0.0
        for idx, iid in enumerate(affected):
            from_iid = affected[idx - 1] if idx > 0 else None
            approach = self._determine_approach(from_iid, iid, req.approach_hints, req.route)
            phase = approach_to_phase(approach)
            eta = cumulative_distance / speed

            plan = IntersectionPriorityPlan(
                intersection_id=iid,
                priority_approach=approach,
                priority_phase=phase,
                priority_green_seconds=self.emergency_green,
                non_priority_green_seconds=self.non_priority_green,
                status=CorridorState.ACTIVE,
                estimated_arrival_seconds=eta,
            )
            intersection_plans[iid] = plan
            self._intersection_allocations[iid] = (veh_id, phase)
            cumulative_distance += self.default_distance

        # 7. Initialize Corridor Metrics
        metrics = CorridorMetrics(
            corridor_id=f"corridor_{veh_id}_{int(now)}",
            emergency_vehicle_id=veh_id,
            route=req.route,
            intersections_affected=len(affected),
            signal_overrides_count=len(affected),
            activation_timestamp=now,
            # Baseline estimation: travel time + average 25s red cycle delay per intersection
            baseline_estimated_travel_time=round(
                (cumulative_distance / speed) + (len(affected) * 25.0), 2
            ),
        )

        corridor_plan = CorridorPlan(
            emergency_vehicle_id=veh_id,
            corridor_status=CorridorState.ACTIVE,
            affected_intersections=affected,
            intersection_plans=intersection_plans,
            validation_result="Emergency corridor activated successfully",
            is_valid=True,
            metrics=metrics,
        )

        self._requests[veh_id] = req
        self._corridors[veh_id] = corridor_plan
        return corridor_plan

    def advance_vehicle(
        self,
        emergency_vehicle_id: str,
        current_intersection_id: str,
        current_time: float | None = None,
    ) -> CorridorPlan | None:
        """Advance emergency vehicle along the corridor, releasing passed junctions."""
        now = time() if current_time is None else float(current_time)
        corridor = self._corridors.get(emergency_vehicle_id)
        if not corridor or corridor.corridor_status != CorridorState.ACTIVE:
            return None

        if current_intersection_id not in corridor.affected_intersections:
            return corridor

        idx = corridor.affected_intersections.index(current_intersection_id)

        # Release all preceding intersections passed by the vehicle
        for passed_idx in range(idx):
            passed_iid = corridor.affected_intersections[passed_idx]
            if passed_iid in corridor.intersection_plans:
                corridor.intersection_plans[passed_iid].status = CorridorState.RELEASED
            self._release_intersection(passed_iid, emergency_vehicle_id)

        # Current intersection is in active progress
        curr_plan = corridor.intersection_plans.get(current_intersection_id)
        if curr_plan:
            curr_plan.status = CorridorState.ACTIVE

        # Check if the emergency vehicle has reached and cleared the final destination
        if idx == len(corridor.affected_intersections) - 1:
            curr_plan.status = CorridorState.PASSED
            # Auto-release entire corridor upon clearing destination
            return self.release_corridor(emergency_vehicle_id, current_time=now)

        return corridor

    def release_corridor(
        self, emergency_vehicle_id: str, current_time: float | None = None
    ) -> CorridorPlan | None:
        """Release all corridor priority locks and finalize traversal metrics."""
        now = time() if current_time is None else float(current_time)
        corridor = self._corridors.get(emergency_vehicle_id)
        if not corridor:
            return None

        for iid in corridor.affected_intersections:
            if iid in corridor.intersection_plans:
                corridor.intersection_plans[iid].status = CorridorState.RELEASED
            self._release_intersection(iid, emergency_vehicle_id)

        corridor.corridor_status = CorridorState.RELEASED

        # Finalize metrics
        if corridor.metrics:
            m = corridor.metrics
            m.completion_timestamp = now
            m.corridor_activation_duration = round(now - m.activation_timestamp, 2)
            m.emergency_travel_time = m.corridor_activation_duration

        return corridor

    def _release_intersection(self, intersection_id: str, emergency_vehicle_id: str) -> None:
        if intersection_id in self._intersection_allocations:
            alloc_veh, _ = self._intersection_allocations[intersection_id]
            if alloc_veh == emergency_vehicle_id:
                del self._intersection_allocations[intersection_id]

    def reset(self) -> None:
        """Reset all active corridors, requests, and allocations."""
        self._corridors.clear()
        self._requests.clear()
        self._intersection_allocations.clear()
