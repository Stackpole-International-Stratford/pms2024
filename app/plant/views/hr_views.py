from django.shortcuts import render

def absentee_forms(request):
    # log to console
    print("⚠️ Absentee forms view hit!")
    # render the template
    return render(request, 'plant/absentee.html')

