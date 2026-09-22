from django import forms
from .models import Pet


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

    def clean(self):
        data = super().clean()
        if (
            data.get("starts")
            and data.get("ends")
            and not 0 < (data["ends"] - data["starts"]).days <= 60
        ):
            raise forms.ValidationError("Choose a stay of 1–60 nights.")
        return data
