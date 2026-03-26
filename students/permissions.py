from functools import wraps
from django.http import HttpResponseForbidden


def is_admin(user):
    return user.is_authenticated and user.is_superuser


def is_teacher(user):
    return user.is_authenticated and user.groups.filter(name="Teacher").exists()


def is_student(user):
    return user.is_authenticated and user.groups.filter(name="Student").exists()


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            return HttpResponseForbidden("Бұл бөлімге тек админ кіре алады.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (is_admin(request.user) or is_teacher(request.user)):
            return HttpResponseForbidden("Бұл бөлімге тек мұғалім немесе админ кіре алады.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def student_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_student(request.user):
            return HttpResponseForbidden("Бұл бөлімге тек студент кіре алады.")

        student_profile = getattr(request.user, "student_profile", None)
        if not student_profile or not student_profile.can_access_platform:
            return HttpResponseForbidden("Сізге платформаға доступ берілмеген.")

        return view_func(request, *args, **kwargs)
    return _wrapped