Simulation README
=================

A minimal simulator is provided at backend/sim/simulator.py for offline testing.
Usage:
- Import Simulator and create instance with grid_map (optional)
- Call start() to run simulator thread or step() for single steps

This simulator is intentionally simple; extend it to replay logs or feed synthetic sensor values to the planner for offline debugging.
