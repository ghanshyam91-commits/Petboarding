from care.models import Provider
from django.db.models import Q

def workspace(request):
    user = request.user
    if not user.is_authenticated:
        return {'is_provider': False}
    return {'is_provider': Provider.objects.filter(Q(owner=user) | Q(staffmembership__user=user, staffmembership__role__in=['manager','caregiver'])).exists()}
