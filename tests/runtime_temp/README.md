# Temporary Workspace Runtime Checks

This directory contains temporary Work runners: exploratory checks, probes,
debug and diagnostic scripts, anatomy and sweep studies, counterfactuals,
prototypes, one-off helpers, and temporary reproduction runners.

The directory may be cleaned periodically. Before cleanup, verify that retained
tests in `tests/runtime_workspace` do not import modules from `runtime_temp`.
Production code must never depend on `tests/runtime_temp`.
