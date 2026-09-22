from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from .demo import is_demo_user
from .forms import SearchForm
from .models import Provider
from .services.stays import eligibility, quote


@login_required
@require_GET
def provider_preview(request, pk):
    provider = get_object_or_404(Provider.objects.select_related('jurisdiction', 'owner'), pk=pk)
    if is_demo_user(request.user) != is_demo_user(provider.owner):
        raise Http404
    form = SearchForm(request.GET or None, user=request.user)
    errors = []
    estimate = None
    eligible = False
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        if data['city'] != provider.jurisdiction.city:
            errors = ['Choose dates and pets for this provider’s city.']
        else:
            errors = eligibility(provider, list(data['pets']), data['starts'], data['ends'])
            if not errors:
                estimate = quote(provider, list(data['pets']), data['starts'], data['ends'])
                eligible = True
    return render(request, 'care/provider_preview.html', {
        'provider': provider, 'form': form, 'eligibility_errors': errors,
        'estimate': estimate, 'eligible': eligible, 'nav': 'Explore',
    })
