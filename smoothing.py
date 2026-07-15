from collections import deque
import yaml   # NEW: needed to read params.yaml

class MovingAverage:
    """Tracks a rolling average of a scalar value."""
    def __init__(self, maxlen=15):
        self.window = deque(maxlen=maxlen)

    def update(self, value):
        self.window.append(value)
        return sum(self.window) / len(self.window)

    def ready(self):
        """True once the window is full — avoids outputting a string
        based on only 1-2 samples right after an object appears."""
        return len(self.window) == self.window.maxlen

# NEW: loads a ratio from params.yaml stored as a string like "7.5 / 106"
# and evaluates it as a fraction for full floating-point precision.
def load_ratio(key, path="params.yaml"):
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    raw = config[key]  # e.g. "29.7 / 381"
    numerator, denominator = raw.split("/")
    return float(numerator.strip()) / float(denominator.strip())
    
    