from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_redirect, name="home"),

    # Auth redirect targets
    path("dashboard/", views.dashboard, name="dashboard"),
    path("me/", views.student_dashboard, name="student_dashboard"),

    # Admin
    path("admin-panel/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/teachers/create/", views.teacher_create, name="teacher_create"),
    path("admin-panel/students/create/", views.student_onboard_create, name="student_onboard_create"),
    path("admin-panel/students/", views.student_access_manage, name="student_access_manage"),
    path("admin-panel/students/<int:student_id>/toggle-access/", views.student_toggle_access, name="student_toggle_access"),

    # Teacher -> groups / students
    path("students/", views.student_list, name="student_list"),
    path("students/group/<str:group_name>/", views.student_group_detail, name="student_group_detail"),
    path("students/<int:student_id>/dashboard/", views.student_detail_dashboard, name="student_detail_dashboard"),

    # Optional student CRUD
    path("students/add/", views.student_add, name="student_add"),
    path("students/<int:pk>/edit/", views.student_edit, name="student_edit"),
    path("students/<int:pk>/delete/", views.student_delete, name="student_delete"),

    # ML
    path("students/<int:pk>/predict/", views.predict_student, name="predict_student"),
    path("students/predict-all/", views.predict_all, name="predict_all"),

    # Analytics
    path("analytics/", views.analytics, name="analytics"),

    # Teacher quizzes
    path("quizzes/", views.quiz_list_teacher, name="quiz_list_teacher"),
    path("quizzes/create/", views.quiz_create, name="quiz_create"),
    path("quizzes/ai-create/", views.quiz_ai_create, name="quiz_ai_create"),
    path("quizzes/<int:quiz_id>/edit/", views.quiz_edit, name="quiz_edit"),
    path("quizzes/<int:quiz_id>/results/", views.quiz_results, name="quiz_results"),
    path("quizzes/<int:quiz_id>/question-add/", views.question_add, name="question_add"),
    path("questions/<int:question_id>/choice-add/", views.choice_add, name="choice_add"),

    # Student quizzes
    path("me/quizzes/", views.quiz_list_student, name="quiz_list_student"),
    path("me/quizzes/<int:quiz_id>/take/", views.quiz_take, name="quiz_take"),

    # Materials
    path("materials/", views.material_list, name="material_list"),
    path("materials/upload/", views.material_upload, name="material_upload"),
    path("materials/<int:material_id>/ai-test/", views.ai_quiz_from_material, name="ai_quiz_from_material"),
]