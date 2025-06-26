#views/password_views.py
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from ..models.password_models import Password
from ..forms.password_forms import PasswordForm
from django.core.paginator import Paginator


def auth_page(request):
    """
    Display and process a simple authentication form for access to the password list.

    GET:
      - Renders the authentication page with an empty input and no error message.
    POST:
      - Reads `auth_input` from form data.
      - If the input matches the hard-coded password ('stackpole1'), marks the session
        as authenticated and redirects to the 'password_list' view.
      - Otherwise, re-renders the form with an error message.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET (to show the form) or POST
        (to submit the password).

    Returns
    -------
    django.http.HttpResponse
        - On GET or failed POST: renders 'passwords/auth.html' with optional `error_message`.
        - On successful POST: redirects to the 'password_list' URL.
    """
    error_message = None
    if request.method == 'POST':
        input_value = request.POST.get('auth_input', '')
        if input_value == 'stackpole1':
            request.session['authenticated'] = True
            return redirect('password_list')
        else:
            error_message = "Incorrect password. Please try again."

    return render(request, 'passwords/auth.html', {'error_message': error_message})


def password_list(request):
    """
    Display a paginated, searchable, and sortable list of non-deleted Password records.

    Access Control
    --------------
    - Redirects to 'auth_page' if the user is not authenticated via session.

    Query Parameters
    ----------------
    - q (str, optional): 
        Search term to filter passwords by asset number, label, username, or password.
    - sort (str, optional, default='-id'): 
        Django ordering string to sort the queryset.
    - per_page (int, optional, default=25): 
        Number of items to display per page.
    - page (int, optional): 
        Page number for pagination.

    Behavior
    --------
    1. Enforces session-based authentication.
    2. Parses and sanitizes `per_page` (falls back to 25 on invalid input).
    3. Filters out deleted records.
    4. If `q` is provided, applies a case-insensitive `icontains` filter on:
       - `password_asset__asset_number`
       - `label`
       - `username`
       - `password`
    5. Applies the specified `sort` ordering.
    6. Uses Django’s `Paginator` to paginate results.
    7. Renders the 'passwords/password_list.html' template with:
       - `page_obj`: the paginated page of passwords.
       - `query`, `sort`, `per_page`: echoing the current parameters for the UI.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP GET request, possibly with query parameters.

    Returns
    -------
    django.http.HttpResponse
        Renders the password list page, or redirects to authentication if not logged in.
    """
    if not request.session.get('authenticated'):
        return redirect('auth_page')

    query = request.GET.get('q', '')  # Default to empty string if None
    sort = request.GET.get('sort', '-id')
    per_page = request.GET.get('per_page', 25)
    
    try:
        per_page = int(per_page)
    except ValueError:
        per_page = 25

    if query:
        passwords = Password.objects.filter(
            Q(password_asset__asset_number__icontains=query) |  # Updated to search by asset number
            Q(label__icontains=query) |
            Q(username__icontains=query) |
            Q(password__icontains=query),
            deleted=False  # Exclude deleted records
        ).order_by(sort)
    else:
        passwords = Password.objects.filter(deleted=False).order_by(sort)

    paginator = Paginator(passwords, per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'passwords/password_list.html', {
        'page_obj': page_obj,
        'query': query,
        'sort': sort,
        'per_page': per_page,
    })


def password_create(request):
    """
    Display and process the form to create a new Password record.

    GET:
      - Instantiates an empty PasswordForm.
      - Renders 'passwords/password_form.html' with the form in context.

    POST:
      - Binds the submitted data to PasswordForm.
      - If valid, saves the new Password instance and redirects to 'password_list'.
      - If invalid, re-renders the form with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, either GET (to display the form) or POST (to submit it).

    Returns
    -------
    django.http.HttpResponse
        - On GET or invalid POST: renders the password creation form template.
        - On valid POST: redirects to the password list view.
    """
    if request.method == 'POST':
        form = PasswordForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('password_list')
    else:
        form = PasswordForm()
    return render(request, 'passwords/password_form.html', {'form': form})


def password_edit(request, pk):
    """
    Display and process the form to edit an existing Password record.

    GET:
      - Retrieves the Password instance by primary key or returns HTTP 404.
      - Instantiates a PasswordForm initialized with the instance.
      - Renders 'passwords/password_form.html' with the form in context.

    POST:
      - Retrieves the Password instance by primary key or returns HTTP 404.
      - Binds submitted data to PasswordForm with the instance.
      - If valid, saves changes and redirects to 'password_list'.
      - If invalid, re-renders the form with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, either GET (to display the form) or POST (to submit it).
    pk : int
        Primary key of the Password record to edit.

    Returns
    -------
    django.http.HttpResponse
        - On GET or invalid POST: renders the password edit form template.
        - On valid POST: redirects to the password list view.
    """
    password = get_object_or_404(Password, pk=pk)
    if request.method == 'POST':
        form = PasswordForm(request.POST, instance=password)
        if form.is_valid():
            form.save()
            return redirect('password_list')
    else:
        form = PasswordForm(instance=password)
    return render(request, 'passwords/password_form.html', {'form': form})


def password_delete(request, pk):
    """
    Soft-delete a Password record and redirect to the password list.

    Marks the specified Password instance as deleted by setting its `deleted` flag
    to True and stamping `deleted_at` with the current time, then saves the record.
    Finally, redirects back to the 'password_list' view.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    pk : int
        Primary key of the Password record to soft-delete.

    Returns
    -------
    django.http.HttpResponseRedirect
        Redirects to the 'password_list' URL after marking the record as deleted.
    """
    password = get_object_or_404(Password, pk=pk)
    password.deleted = True
    password.deleted_at = timezone.now()
    password.save()
    return redirect('password_list')


def deleted_passwords(request):
    """
    Display a list of soft-deleted Password records.

    Retrieves all Password instances where `deleted=True`, ordered by most
    recent `deleted_at` timestamp first, and renders them in the
    'passwords/deleted_passwords.html' template.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP GET request.

    Returns
    -------
    django.http.HttpResponse
        Renders the "passwords/deleted_passwords.html" template with context:
          - deleted_passwords: QuerySet of deleted Password objects.
    """
    deleted_passwords = Password.objects.filter(deleted=True).order_by('-deleted_at')
    return render(request, 'passwords/deleted_passwords.html', {'deleted_passwords': deleted_passwords})


def password_recover(request, pk):
    """
    Restore a soft-deleted Password record and redirect to the password list.

    Retrieves the Password instance by primary key. If it is marked as deleted,
    clears the `deleted` flag and `deleted_at` timestamp, saves the record,
    and then redirects to the 'password_list' view.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    pk : int
        Primary key of the Password record to restore.

    Returns
    -------
    django.http.HttpResponseRedirect
        Redirects to the 'password_list' URL after restoring the record.
    """
    password = get_object_or_404(Password, pk=pk)
    if password.deleted:
        password.deleted = False
        password.deleted_at = None
        password.save()
    return redirect('password_list')
