"""Hermes laptop daemon.

Runs as an NSSM Windows service. Hosts MCP tool servers over a local FastAPI
app bound to the Tailscale interface, and connects outbound to NATS for
cross-device dispatch.
"""

__version__ = "0.1.0"
