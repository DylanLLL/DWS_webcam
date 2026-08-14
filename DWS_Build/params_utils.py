# params_utils.py
# Shared helpers for reading configuration values from params.yaml.

import yaml

def load_ratio(key, path="params.yaml"):
    """Loads a ratio from params.yaml stored as a string like '7.5 / 106'
    and evaluates it as a fraction for full floating-point precision."""
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    raw = config[key]
    numerator, denominator = raw.split("/")
    return float(numerator.strip()) / float(denominator.strip())


def load_camera_index(key, path="params.yaml"):
    """Loads a camera device index from params.yaml."""
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    return int(config[key])


def load_float(key, path="params.yaml"):
    """Loads a plain numeric value (not a fraction) from params.yaml."""
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    return float(config[key])
