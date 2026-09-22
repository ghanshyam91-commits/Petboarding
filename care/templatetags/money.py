from django import template
register=template.Library()
@register.filter
def inr(value):
    try: return f'₹{int(value)/100:,.0f}'
    except (ValueError,TypeError): return '—'
