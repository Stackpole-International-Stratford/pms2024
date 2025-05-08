from django.shortcuts import render

def temp_display(request):
    # Log to the console
    print("hello world")
    # Render the template
    return render(request, 'plant/temp_display.html')
