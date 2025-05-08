from django.http import HttpResponse

def temp_display(request):
    # This will show up in your console/log when this URL is hit
    print("hello world")
    return HttpResponse("Temperature display endpoint hit.")
