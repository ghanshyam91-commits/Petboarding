from django import forms
from .models import Pet
from django.utils import timezone


class PetForm(forms.ModelForm):
    class Meta:
        model = Pet
        fields = [
            "name",
            "species",
            "breed",
            "birth_date",
            "weight",
            "sex",
            "neutered",
            "compatible_cats",
            "compatible_dogs",
            "aggression_history",
            "medication_required",
        ]
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}


    def clean_weight(self):
        weight = self.cleaned_data.get("weight")
        if weight is not None and weight <= 0:
            raise forms.ValidationError("Enter a weight greater than zero.")
        return weight

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if birth_date and birth_date > timezone.localdate():
            raise forms.ValidationError("Birth date cannot be in the future.")
        return birth_date


class SearchForm(forms.Form):
    city = forms.ChoiceField(
        choices=[
            (x, x)
            for x in [
                "Bengaluru",
                "Delhi NCR",
                "Mumbai",
                "Pune",
                "Hyderabad",
                "Chennai",
                "Kolkata",
            ]
        ]
    )
    starts = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    ends = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    pets = forms.ModelMultipleChoiceField(
        queryset=Pet.objects.none(), widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pets"].queryset = Pet.objects.filter(owner=user)
        from .demo import is_demo_user, DEMO_CITY
        if is_demo_user(user):
            self.fields["city"].choices = [(DEMO_CITY, "Bengaluru · Demo")]
            self.initial["city"] = DEMO_CITY

    def clean(self):
        data = super().clean()
        if data.get("starts") and data["starts"] < timezone.localdate():
            self.add_error("starts", "Choose today or a future date.")
        if (
            data.get("starts")
            and data.get("ends")
            and not 0 < (data["ends"] - data["starts"]).days <= 60
        ):
            raise forms.ValidationError("Choose a stay of 1–60 nights.")
        return data
