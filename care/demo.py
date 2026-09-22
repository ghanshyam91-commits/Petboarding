from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

DEMO_GROUP = 'public-demo-readonly'
DEMO_CITY = 'Bengaluru · Demo'
DEMO_USERS = {'parent': 'guest_parent_demo', 'provider': 'guest_provider_demo'}


def is_demo_user(user):
    return user.is_authenticated and user.groups.filter(name=DEMO_GROUP).exists()


def demo_context(request):
    return {'demo_enabled': settings.ENABLE_DEMO_LOGIN,
            'is_demo': getattr(request, 'is_demo', False)}


@require_POST
def demo_login(request):
    if not settings.ENABLE_DEMO_LOGIN:
        raise Http404
    role = request.POST.get('role', 'parent')
    username = DEMO_USERS.get(role)
    if not username:
        raise Http404
    user = User.objects.filter(username=username, groups__name=DEMO_GROUP,
                               is_active=True, is_staff=False, is_superuser=False).first()
    if not user:
        messages.info(request, 'The demo is being prepared. Please try again shortly.')
        return redirect('login')
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.set_expiry(3600)
    return redirect('operations' if role == 'provider' else 'home')


class DemoReadOnly:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_demo = is_demo_user(request.user)
        if request.is_demo:
            if not settings.ENABLE_DEMO_LOGIN or request.user.is_staff or request.user.is_superuser:
                logout(request)
                return redirect('login')
            if request.path.startswith('/admin/') or request.path.startswith('/trust/'):
                return HttpResponseForbidden('Demo accounts do not have admin access.')
            if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.path not in ('/logout/', '/demo/login/'):
                messages.info(request, 'This shared demo is read-only. Browse the sample stays and care updates.')
                return redirect('operations' if request.user.username == DEMO_USERS['provider'] else 'home')
        return self.get_response(request)
