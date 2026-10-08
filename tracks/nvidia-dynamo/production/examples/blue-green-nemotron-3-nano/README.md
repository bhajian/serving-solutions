# Blue/green model upgrade

1. Change the model revision or engine flags in `tools/render_graphs.py`, re-render, and
   apply the result as the green graph (`green/`, graph name `nemotron-3-nano-green`).
2. Wait for the green frontend to report Ready; it only does so once its workers are
   discovered.
3. Shift the HTTPRoute weights (90/10, then 50/50, then 0/100) while watching the
   TTFT/ITL SLO alerts in tracks/nvidia-dynamo/observability.
4. Promote: apply green as the main graph and delete the old one.

The operator rolls each graph independently, with the Grove update strategy
`RollingRecreate`; the gateway moves traffic between graphs. UNVALIDATED — scheduled.
