from django.core.exceptions import ValidationError
from django.forms import (
    BooleanField,
    CharField,
    ChoiceField,
    EmailField,
    Form,
    IntegerField,
    Textarea,
)


class ContactForm(Form):
    name = CharField(max_length=100)
    email = EmailField()
    age = IntegerField(min_value=0, max_value=150)
    message = CharField(widget=Textarea, required=False)
    agree = BooleanField(required=False)
    category = ChoiceField(
        choices=[
            ("general", "General"),
            ("support", "Support"),
            ("feedback", "Feedback"),
        ]
    )

    def clean_name(self):
        name = self.cleaned_data["name"]
        if name == "banned":
            raise ValidationError("This name is not allowed")
        return name

    def clean(self):
        cleaned_data = super().clean()
        age = cleaned_data.get("age")
        category = cleaned_data.get("category")
        if age is not None and age < 18 and category == "support":
            raise ValidationError("Support requests require an adult")
        return cleaned_data
