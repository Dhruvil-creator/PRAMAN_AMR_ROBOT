"""MQ sensor wrapper for PRAMAN AMR.

Provides a unified interface for MQ2 and MQ135 readings.
"""
from backend.sensors.gas import read_mq2, read_mq135


def read_all():
    """Return both MQ2 and MQ135 readings.

    Output format is compatible with the unified system payload.
    """
    return {
        "mq2": read_mq2(),
        "mq135": read_mq135()
    }


def get_gas_profile():
    """Get annotated gas sensor data for the dashboard."""
    return read_all()
