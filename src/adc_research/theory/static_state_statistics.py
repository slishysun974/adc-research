"""Offline finite-record identities; no platform or calibration imports."""

import numpy as np


def mean_covariance_loss(phi, target, states):
    """Fixed evaluation matrix, population covariance (divisor M), no rounding."""
    phi, target, states = map(lambda x: np.asarray(x, dtype=float), (phi, target, states))
    mean = states.mean(axis=0)
    centered = states - mean
    covariance = centered.T @ centered / len(states)
    gram = phi.T @ phi / len(phi)
    mean_loss = float(np.mean((phi @ mean - target)**2))
    variance_loss = float(np.trace(gram @ covariance))
    return {"mean": mean.tolist(), "covariance": covariance.tolist(),
            "mean_state_mse": mean_loss, "state_variance_mse": variance_loss,
            "average_continuous_mse": mean_loss + variance_loss}


def finite_increment_balance(states, origin):
    """Exact finite telescoping balance, NOT a stationarity or white-noise test."""
    e = np.asarray(states, dtype=float) - np.asarray(origin, dtype=float)
    delta = np.diff(e, axis=0)
    left = e[:-1]
    w = len(delta)
    cross = (left.T @ delta + delta.T @ left) / w
    power = delta.T @ delta / w
    boundary = (np.outer(e[-1], e[-1]) - np.outer(e[0], e[0])) / w
    return {"transitions": w, "mean_increment": delta.mean(axis=0).tolist(),
            "mean_boundary": ((e[-1]-e[0])/w).tolist(),
            "cross": cross.tolist(), "increment_second_moment": power.tolist(),
            "second_moment_boundary": boundary.tolist(),
            "maximum_balance_error": float(np.max(np.abs(cross + power - boundary)))}
