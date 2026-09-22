"""Illustrative stock photos for fictional demo records only."""
from django import template
from care.demo import DEMO_CITY, DEMO_USERS

register = template.Library()
BASE = 'https://images.unsplash.com/'
PHOTOS = {
    'dog': 'photo-1552053831-71594a27632d',
    'cat': 'photo-1514888286974-6c03e2ca1dba',
    'room': 'photo-1600210492486-724fe5c67fb0',
    'lounge': 'photo-1600566753086-00f18fb6b3ea',
}

@register.simple_tag
def sample_photo(kind, width=900):
    return f'{BASE}{PHOTOS.get(kind, PHOTOS["room"])}?auto=format&fit=crop&w={width}&q=80'

@register.simple_tag
def pet_photo(pet):
    if pet.owner.username != DEMO_USERS['parent']:
        return ''
    return sample_photo('cat' if pet.species == 'cat' else 'dog', 480)

@register.simple_tag
def provider_photo(provider):
    if provider.jurisdiction.city != DEMO_CITY:
        return ''
    return sample_photo('room' if provider.name.startswith('Little') else 'lounge', 900)
