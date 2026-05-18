"""
CBBA subclass for the global_and_local_convergence scenario.

Two scenario-specific concerns layered on top of stock CBBA:

(1) **Communication-radius post-filter** (applies in every mona.mode).

    In p2p / offboard mode the ESP-NOW radio physically broadcasts to
    everyone in radio range; the upstream MonaComm filter
    (``MonaAgent._peer_in_range``) is supposed to drop senders outside
    ``agents.communication_radius`` before they reach CBBA, but this
    layer re-applies the same filter at the CBBA boundary so the
    constraint holds uniformly regardless of mode or future upstream
    changes. In full_simulation it is redundant (already filtered by
    ``BaseAgent.get_agents_nearby``) but cheap.

    The radius value is read once from yaml — ``self.agent.communication_radius``
    is intentionally NOT used here because MonaAgent mutates it at
    runtime to reflect observed peers; we need the configured cap.

(2) **Oracle-style convergence detection** — defined regardless of comm.

    Each tick we use the sim roster (``self.agent.agents_info``) to scan
    every agent's current CBBA bundle and find any task_id present in
    two or more bundles — those agents are the *duplicate owners*.
    This bypasses comm range by design: it is the metric that drives
    the convergence-percentage graph and the global-mode movement gate.

  - ``global_convergence: False`` (Local mode):
      An agent stops only if it itself is one of the duplicate owners.
      Conflict-free agents keep moving.

  - ``global_convergence: True`` (Global mode):
      If *any* duplicate exists anywhere in the swarm, *every* agent
      stops. Movement resumes only when no two agents share a task.

The base class is left untouched; this subclass only post-processes
``self.agent.messages_received`` (item 1) and the return value of
``super().decide()`` (item 2).
"""
from core.utils import config
from plugins.mrta.cbba.cbba import CBBA as _BaseCBBA


GLOBAL_CONVERGENCE = config['decision_making']['CBBA'].get('global_convergence', False)
COMM_RADIUS = float(config.get('agents', {}).get('communication_radius', 0) or 0)


class CBBA(_BaseCBBA):

    def decide(self, blackboard):
        # (1) Drop CBBA messages from peers outside the configured comm radius.
        self._filter_out_of_range_messages()

        result = super().decide(blackboard)

        # Broadcast our current bundle so peers' oracle scans can see it.
        if self.agent.message_to_share is not None:
            self.agent.message_to_share['bundle'] = list(self.bundle)

        # (2) Oracle-based convergence (Local vs Global).
        duplicate_owners = self._duplicate_claim_owners()

        if GLOBAL_CONVERGENCE:
            converged = (len(duplicate_owners) == 0)
        else:
            converged = (self.agent.agent_id not in duplicate_owners)

        if self.agent.message_to_share is not None:
            self.agent.message_to_share['converged'] = converged

        if not converged:
            return None
        return result

    # ----------------------------------------------------------------------
    # (1) Comm-radius post-filter on messages_received
    # ----------------------------------------------------------------------
    def _filter_out_of_range_messages(self):
        # Configured radius <= 0 means "global comm" — no filter.
        if COMM_RADIUS <= 0:
            return
        if self.agent.agents_info is None:
            return

        pos_by_id = {a.agent_id: a.position for a in self.agent.agents_info}
        my_pos = self.agent.position
        r_sq = COMM_RADIUS * COMM_RADIUS

        filtered = []
        for m in self.agent.messages_received:
            if not m:
                continue
            sender_id = m.get('agent_id')
            sender_pos = pos_by_id.get(sender_id)
            if sender_pos is None:
                # Unknown sender id → drop (can't verify range)
                continue
            if (my_pos - sender_pos).length_squared() > r_sq:
                continue
            filtered.append(m)
        self.agent.messages_received = filtered

    # ----------------------------------------------------------------------
    # (2) Sim-level oracle: who currently shares a task with someone else?
    # Uses the full roster (agents_info) so it bypasses communication range
    # — that's the whole point of this check.
    # ----------------------------------------------------------------------
    def _duplicate_claim_owners(self) -> set:
        if self.agent.agents_info is None:
            return set()

        # task_id -> set of agent_ids that have it in their bundle
        claims: dict = {}
        for a in self.agent.agents_info:
            mts = getattr(a, 'message_to_share', None) or {}
            for tid in mts.get('bundle', []):
                claims.setdefault(tid, set()).add(a.agent_id)

        duplicate_owners = set()
        for owners in claims.values():
            if len(owners) > 1:
                duplicate_owners.update(owners)
        return duplicate_owners
