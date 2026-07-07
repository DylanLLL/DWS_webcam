# smoothing.py
from collections import deque

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
    
    