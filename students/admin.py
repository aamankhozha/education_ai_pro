from django.contrib import admin
from .models import Student
from .models import AIAnalysis


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "user", "can_access_platform")
    list_filter = ("group", "can_access_platform")
    search_fields = ("name", "group", "user__username")

@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "percent", "created_at")
    search_fields = ("student__name", "quiz__title")

