"""
global_and_local_convergence Sim.

Extensions over MonaSim:
  * Per-tick recording of the **global convergence percentage** — the
    fraction of agents whose ``message_to_share['converged']`` is True
    (the flag our CBBA subclass stamps each tick). 4-agent system:
    2 converged + 2 in conflict → 50%, 1 converged + 3 in conflict → 25%,
    and so on. ``global_convergence: True`` in CBBA means agents only
    move when this hits 100%.
  * On shutdown (e.g. user presses 'q'), save two artefacts alongside the
    standard timewise CSV:
        <base>_convergence.csv  — sim_time, wall_clock, convergence_pct
        <base>_convergence.png  — one figure, two subplots side-by-side
                                  (sim-time on x; wall-clock on x).

Wiring for all four MONA modes (full_simulation / puppet / p2p / offboard)
is inherited from MonaSim — driven by ``mona.mode``.
"""
from platforms.mona.mona_sim import MonaSim


class Sim(MonaSim):

    # ── reset(): allocate the convergence log alongside the base records ────
    def reset(self):
        super().reset()
        # Each entry: (simulation_time, wall_clock, convergence_pct)
        self.convergence_records = []

    # ── record_timewise_result(): also stamp convergence % this tick ───────
    def record_timewise_result(self):
        super().record_timewise_result()

        n = len(self.agents)
        if n == 0:
            pct = 0.0
        else:
            converged = sum(
                1 for a in self.agents
                if getattr(a, 'message_to_share', None) is not None
                and a.message_to_share.get('converged', False)
            )
            pct = 100.0 * converged / n

        self.convergence_records.append(
            (self.simulation_time, self.wall_clock, pct)
        )

    # ── save_results(): emit the convergence CSV + PNG ─────────────────────
    def save_results(self):
        super().save_results()
        if self.save_timewise_result_csv and self.convergence_records:
            self._plot_convergence()

    def _plot_convergence(self):
        # Lazy imports — pulls matplotlib/pandas only on save.
        import matplotlib.pyplot as plt
        import pandas as pd

        base = self.result_saver.result_file_path.rsplit('.', 1)[0]

        df = pd.DataFrame(
            self.convergence_records,
            columns=['simulation_time', 'wall_clock', 'convergence_pct'],
        )
        csv_path = base + '_convergence.csv'
        df.to_csv(csv_path, index=False)
        print(f"[Convergence] Saved: {csv_path}")

        fig, (ax_sim, ax_wall) = plt.subplots(1, 2, figsize=(14, 5))

        ax_sim.plot(df['simulation_time'], df['convergence_pct'],
                    color='tab:blue', linewidth=1.5)
        ax_sim.set_xlabel('Simulation Time (s)')
        ax_sim.set_ylabel('Convergence (%)')
        ax_sim.set_title('Convergence vs Simulation Time')
        ax_sim.set_ylim(-2, 105)
        ax_sim.grid(True, alpha=0.4)

        ax_wall.plot(df['wall_clock'], df['convergence_pct'],
                     color='tab:green', linewidth=1.5)
        ax_wall.set_xlabel('Wall Clock Time (s)')
        ax_wall.set_ylabel('Convergence (%)')
        ax_wall.set_title('Convergence vs Wall Clock Time')
        ax_wall.set_ylim(-2, 105)
        ax_wall.grid(True, alpha=0.4)

        fig.tight_layout()
        png_path = base + '_convergence.png'
        fig.savefig(png_path)
        plt.close(fig)
        print(f"[Convergence] Saved: {png_path}")
