from django.shortcuts import render
from plant.models.plantSpine_models import PlantSpine

def plant_blueprint(request):
    """
    Displays all PlantSpine records in a table.
    """
    records = PlantSpine.objects.all()
    return render(request, 'plant/plant_blueprint.html', {
        'records': records,
    })
