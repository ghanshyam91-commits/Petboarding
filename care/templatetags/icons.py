from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()
PATHS = {
 'home':'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-8h6v8"/>',
 'search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 'calendar':'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h3m2 0h3"/>',
 'message':'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V7a4 4 0 0 1 4-4h6a8 8 0 0 1 8 8Z"/><path d="M7 9h9m-9 4h6"/>',
 'paw':'<ellipse cx="6" cy="8" rx="2" ry="3"/><ellipse cx="12" cy="5" rx="2" ry="3"/><ellipse cx="18" cy="8" rx="2" ry="3"/><path d="M6 18c0-3 4-7 6-7s6 4 6 7c0 4-4 1-6 1s-6 3-6-1Z"/>',
 'user':'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
 'check':'<path d="m5 12 4 4L19 6"/>',
 'shield':'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
 'tasks':'<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 10h6m-6 5h6"/>',
 'plus':'<path d="M12 4v16M4 12h16"/>',
 'arrow':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
 'back':'<path d="M20 12H4m6-6-6 6 6 6"/>',
 'edit':'<path d="m14 4 6 6M3 21l2-7L17 2l5 5L10 19Z"/>',
 'upload':'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
 'health':'<path d="M4 3h16v18H4Z M9 3v3h6V3m-3 7v7m-3-3h6"/>',
 'clock':'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 'star':'<path d="m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z"/>',
 'exit':'<path d="M9 4H3v16h6m-1-8h14m-5-5 5 5-5 5"/>',
 'building':'<path d="M4 21V3h16v18M2 21h20M8 7h2m4 0h2M8 11h2m4 0h2M10 21v-6h4v6"/>',
 'alert':'<path d="m12 3 10 18H2Z M12 9v5m0 3v1"/>',
}
@register.simple_tag
def icon(name):
    return format_html('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>', mark_safe(PATHS.get(name, PATHS['paw'])))
