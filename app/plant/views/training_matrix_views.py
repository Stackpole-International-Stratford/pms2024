from django.shortcuts import render

def training_matrix(request):
    """
    Temporary view to render the training_matrix template.
    """
    return render(request, 'plant/training_matrix.html')
