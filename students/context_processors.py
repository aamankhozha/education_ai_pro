from .permissions import is_admin, is_teacher, is_student


def role_flags(request):
    user = request.user

    if not user.is_authenticated:
        return {
            "is_admin": False,
            "is_teacher": False,
            "is_student": False,
        }

    return {
        "is_admin": is_admin(user),
        "is_teacher": is_teacher(user),
        "is_student": is_student(user),
    }