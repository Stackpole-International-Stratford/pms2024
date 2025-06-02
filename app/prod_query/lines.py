# myapp/lines.py

from plant.models.plantSpine_models import PlantSpine

class _LinesProxy:
    """A list‐like proxy that always re‐loads from the DB."""
    def _load(self):
        # you can catch DoesNotExist if you like
        return PlantSpine.objects.get(name="default").data

    def __iter__(self):
        return iter(self._load())

    def __len__(self):
        return len(self._load())

    def __getitem__(self, i):
        data = self._load()
        return data[i]        # handles both int and slice

    def __getattr__(self, attr):
        # forward any other list methods (e.g. .count, .index, etc.)
        return getattr(self._load(), attr)

# this is what all your views import
lines = _LinesProxy()
