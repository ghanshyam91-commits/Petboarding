"""Forms and POST-only endpoints for the provider and custody lifecycle."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from care.models import Booking, Provider
from care.services.provider_flow import (confirm_booking, checkin_booking, checkout_booking,
                                       record_care_event, create_care_task)


class CareUpdateForm(forms.Form):
    pet = forms.IntegerField(min_value=1)
    kind = forms.CharField(max_length=80)
    notes = forms.CharField(max_length=4000, widget=forms.Textarea)


class CareTaskForm(forms.Form):
    pet = forms.IntegerField(min_value=1)
    kind = forms.CharField(max_length=50)
    due_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    critical = forms.BooleanField(required=False)


def _action(request, pk, operation, success, *args, **kwargs):
    try:
        operation(request.user, pk, *args, **kwargs)
        messages.success(request, success)
    except (Booking.DoesNotExist, Provider.DoesNotExist):
        raise Http404
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('stay', pk=pk)


@login_required
@require_POST
def confirm_stay(request, pk):
    return _action(request, pk, confirm_booking, 'Reservation confirmed. Check-in becomes available on the arrival date.')


@login_required
@require_POST
def checkin(request, pk):
    return _action(request, pk, checkin_booking, 'Check-in acknowledgement recorded.',
                   request.POST.get('condition', '')[:4000], request.POST.get('belongings', '')[:4000],
                   request.POST.get('food', '')[:4000], request.POST.get('emergency_verified') == 'on')


@login_required
@require_POST
def checkout(request, pk):
    return _action(request, pk, checkout_booking, 'Checkout acknowledgement recorded.',
                   request.POST.get('condition', '')[:4000], request.POST.get('belongings', '')[:4000])


@login_required
@require_POST
def record_care(request, pk):
    form = CareUpdateForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose a pet, update type, and care note (up to 4,000 characters).')
        return redirect('stay', pk=pk)
    data = form.cleaned_data
    return _action(request, pk, record_care_event, 'Care update added to the timeline.',
                   data['pet'], data['kind'], data['notes'])


@login_required
@require_POST
def add_task(request, pk):
    form = CareTaskForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose a pet, task name, and valid due date and time.')
        return redirect('stay', pk=pk)
    data = form.cleaned_data
    return _action(request, pk, create_care_task, 'Care task scheduled.',
                   data['pet'], data['kind'], data['due_at'], data['critical'])
