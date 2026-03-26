from django import forms
from .models import Choice, LessonMaterial, Question, Quiz, Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["name", "group", "user", "can_access_platform", "predicted_performance"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "group": forms.TextInput(attrs={"class": "form-control"}),
            "user": forms.Select(attrs={"class": "form-select"}),
            "can_access_platform": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "predicted_performance": forms.Select(attrs={"class": "form-select"}),
        }


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["title", "description", "is_active", "time_limit_minutes"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "time_limit_minutes": forms.NumberInput(attrs={"class": "form-control"}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["text", "points"]
        widgets = {
            "text": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "points": forms.NumberInput(attrs={"class": "form-control"}),
        }


class ChoiceForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ["text", "is_correct"]
        widgets = {
            "text": forms.TextInput(attrs={"class": "form-control"}),
            "is_correct": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class LessonMaterialForm(forms.ModelForm):
    class Meta:
        model = LessonMaterial
        fields = ["title", "subject", "topic", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "topic": forms.TextInput(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }