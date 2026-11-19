import asyncio


class PaneLocks:
    """One lock per pane, shared by everything that types into or closes a pane; `structure` serializes closes and creations."""

    def __init__(self):
        self._locks: dict = {}
        self.structure = asyncio.Lock()

    def get(self, pane: str) -> asyncio.Lock:
        return self._locks.setdefault(pane, asyncio.Lock())
