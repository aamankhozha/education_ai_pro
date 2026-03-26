import json
from collections import Counter, defaultdict

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import models, transaction
from django.db.models import Avg, Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ChoiceForm, LessonMaterialForm, QuestionForm, QuizForm, StudentForm
from .models import (
    AIAnalysis,
    Answer,
    Choice,
    LessonMaterial,
    Question,
    Quiz,
    Student,
    Submission,
)
from .permissions import (
    admin_required,
    is_admin,
    is_student,
    is_teacher,
    student_required,
    teacher_required,
)
from .services.openai_service import AIQuotaError, generate_mcq_from_topic, generate_mcq_json
from .services.pdf_service import extract_text_from_file
from .services_ml import load_metrics, model_ready, predict_student_summary


# =========================================================
# Admin forms
# =========================================================

class TeacherCreateForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Мұғалім аты-жөні")
    username = forms.CharField(max_length=150, label="Логин")
    password = forms.CharField(widget=forms.PasswordInput, label="Құпиясөз")


class StudentOnboardForm(forms.Form):
    name = forms.CharField(max_length=150, label="Студент аты-жөні")
    group = forms.CharField(max_length=50, label="Тобы")
    username = forms.CharField(max_length=150, label="Логин")
    password = forms.CharField(widget=forms.PasswordInput, label="Құпиясөз")
    can_access_platform = forms.BooleanField(
        required=False,
        initial=True,
        label="Платформаға доступ беру"
    )


class AIQuizRequestForm(forms.Form):
    subject = forms.CharField(max_length=120)
    topic = forms.CharField(max_length=200)
    num_questions = forms.IntegerField(min_value=1, max_value=50, initial=10)
    time_limit_minutes = forms.IntegerField(min_value=1, max_value=180, initial=20)


# =========================================================
# Admin views
# =========================================================

@login_required
@admin_required
def admin_dashboard(request):
    teacher_count = User.objects.filter(groups__name="Teacher").count()
    student_count = Student.objects.count()
    active_student_count = Student.objects.filter(
        can_access_platform=True,
        user__isnull=False
    ).count()

    return render(request, "students/admin/dashboard.html", {
        "teacher_count": teacher_count,
        "student_count": student_count,
        "active_student_count": active_student_count,
        "model_ready": model_ready(),
    })


@login_required
@admin_required
def teacher_create(request):
    if request.method == "POST":
        form = TeacherCreateForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]

            if User.objects.filter(username=username).exists():
                messages.error(request, "Мұндай логинмен қолданушы бұрыннан бар.")
                return redirect("teacher_create")

            user = User.objects.create_user(
                username=username,
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["full_name"],
            )

            teacher_group, _ = Group.objects.get_or_create(name="Teacher")
            user.groups.add(teacher_group)

            messages.success(request, "Мұғалім аккаунты сәтті ашылды.")
            return redirect("admin_dashboard")
    else:
        form = TeacherCreateForm()

    return render(request, "students/admin/teacher_create.html", {
        "form": form,
        "model_ready": model_ready(),
    })


@login_required
@admin_required
def student_onboard_create(request):
    if request.method == "POST":
        form = StudentOnboardForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]

            if User.objects.filter(username=username).exists():
                messages.error(request, "Мұндай логинмен қолданушы бұрыннан бар.")
                return redirect("student_onboard_create")

            user = User.objects.create_user(
                username=username,
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["name"],
            )

            student_group, _ = Group.objects.get_or_create(name="Student")
            user.groups.add(student_group)

            Student.objects.create(
                user=user,
                name=form.cleaned_data["name"],
                group=form.cleaned_data["group"],
                can_access_platform=form.cleaned_data["can_access_platform"],
            )

            messages.success(request, "Студент аккаунты сәтті ашылды.")
            return redirect("student_access_manage")
    else:
        form = StudentOnboardForm()

    return render(request, "students/admin/student_onboard_create.html", {
        "form": form,
        "model_ready": model_ready(),
    })


@login_required
@admin_required
def student_access_manage(request):
    students = Student.objects.select_related("user").order_by("group", "name")

    return render(request, "students/admin/student_access_manage.html", {
        "students": students,
        "model_ready": model_ready(),
    })


@login_required
@admin_required
def student_toggle_access(request, student_id):
    student = get_object_or_404(Student, id=student_id)

    student.can_access_platform = not student.can_access_platform
    student.save(update_fields=["can_access_platform"])

    if student.can_access_platform:
        messages.success(request, f"{student.name} үшін платформа доступы қосылды.")
    else:
        messages.warning(request, f"{student.name} үшін платформа доступы өшірілді.")

    return redirect("student_access_manage")


# =========================================================
# Main redirects / teacher dashboard
# =========================================================

def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if is_admin(request.user):
        return redirect("admin_dashboard")

    if is_teacher(request.user):
        return redirect("dashboard")

    if is_student(request.user):
        student_profile = getattr(request.user, "student_profile", None)
        if student_profile and student_profile.can_access_platform:
            return redirect("student_dashboard")
        return HttpResponseForbidden("Сізге платформаға доступ берілмеген.")

    return HttpResponseForbidden("Сіздің аккаунтыңызға рөл берілмеген.")


@login_required
@teacher_required
def dashboard(request):
    total_students = Student.objects.filter(can_access_platform=True, user__isnull=False).count()

    students = list(Student.objects.filter(can_access_platform=True, user__isnull=False))
    risk_count = sum(1 for s in students if s.risk_status() == "Тәуекел")

    high = Student.objects.filter(predicted_performance="Жоғары").count()
    mid = Student.objects.filter(predicted_performance="Орташа").count()
    low = Student.objects.filter(predicted_performance="Төмен").count()

    context = {
        "total_students": total_students,
        "risk_percent": round((risk_count / total_students) * 100, 2) if total_students else 0,
        "model_ready": model_ready(),
        "pred_counts": {"Жоғары": high, "Орташа": mid, "Төмен": low},
        "metrics": load_metrics(),
    }
    return render(request, "students/dashboard.html", context)


# =========================================================
# Teacher: groups / student dashboards
# =========================================================

@login_required
@teacher_required
def student_list(request):
    groups = (
        Student.objects.filter(
            can_access_platform=True,
            user__isnull=False
        )
        .exclude(group__isnull=True)
        .exclude(group__exact="")
        .values("group")
        .annotate(student_count=Count("id"))
        .order_by("group")
    )

    total_groups = groups.count()
    total_students = Student.objects.filter(
        can_access_platform=True,
        user__isnull=False
    ).count()

    return render(request, "students/student_groups.html", {
        "groups": groups,
        "total_groups": total_groups,
        "total_students": total_students,
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def student_group_detail(request, group_name):
    students = (
        Student.objects.filter(
            group=group_name,
            can_access_platform=True,
            user__isnull=False
        )
        .order_by("name")
    )

    avg_percent = (
        Submission.objects.filter(
            student__group=group_name,
            student__can_access_platform=True,
            student__user__isnull=False,
            submitted_at__isnull=False
        ).aggregate(avg=Avg("percent"))["avg"] or 0
    )

    total_tests = Submission.objects.filter(
        student__group=group_name,
        student__can_access_platform=True,
        student__user__isnull=False,
        submitted_at__isnull=False
    ).count()

    return render(request, "students/student_group_detail.html", {
        "group_name": group_name,
        "students": students,
        "avg_percent": round(avg_percent, 2),
        "total_tests": total_tests,
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def student_detail_dashboard(request, student_id):
    student = get_object_or_404(
        Student,
        id=student_id,
        can_access_platform=True,
        user__isnull=False
    )

    submissions = (
        Submission.objects.select_related("quiz")
        .filter(student=student, submitted_at__isnull=False)
        .order_by("submitted_at", "id")
    )

    progress_labels = []
    progress_values = []

    for sub in submissions:
        progress_labels.append(sub.quiz.title)
        progress_values.append(float(sub.percent or 0))

    analyses = AIAnalysis.objects.filter(student=student).order_by("-created_at")

    weak_topic_counter = {}
    for a in analyses:
        if a.weak_topics_json:
            try:
                topics = json.loads(a.weak_topics_json)
                for t in topics:
                    weak_topic_counter[t] = weak_topic_counter.get(t, 0) + 1
            except Exception:
                pass

    weak_topic_labels = list(weak_topic_counter.keys())
    weak_topic_values = list(weak_topic_counter.values())

    avg_percent = submissions.aggregate(avg=Avg("percent"))["avg"] or 0
    total_tests = submissions.count()
    passed_tests = submissions.filter(percent__gte=80).count()
    failed_tests = submissions.filter(percent__lt=80).count()

    remedial_submissions = submissions.filter(quiz__quiz_type="remedial")
    remedial_avg = remedial_submissions.aggregate(avg=Avg("percent"))["avg"] or 0

    ml_summary = None
    if model_ready():
        try:
            ml_summary = predict_student_summary(student)
        except Exception:
            ml_summary = None

    interventions = []

    if total_tests == 0:
        interventions.append("Студент әлі тест тапсырмаған. Алдымен бастапқы диагностикалық тест тапсыру ұсынылады.")
    else:
        if avg_percent < 50:
            interventions.append("Жалпы нәтиже өте төмен. Жеңіл деңгейдегі remedial тесттерден бастау ұсынылады.")
        elif avg_percent < 80:
            interventions.append("Нәтиже орташа деңгейде. Әлсіз тақырыптар бойынша targeted remedial тесттер ұсынылады.")
        else:
            interventions.append("Нәтиже жақсы. Келесі деңгейдегі күрделірек тесттер ұсынуға болады.")

        if failed_tests > passed_tests:
            interventions.append("Сәтсіз тапсырылған тесттер көп. Оқытушы тарапынан қосымша түсіндіру қажет.")
        if weak_topic_labels:
            interventions.append(f"Негізгі назар аудару керек тақырып: {weak_topic_labels[0]}.")
        if remedial_submissions.count() >= 2 and remedial_avg < 80:
            interventions.append("Бірнеше remedial тесттен кейін де 80%-дан аспады. Оқу материалын қайта қарау қажет.")

    if ml_summary:
        if ml_summary["risk"] == "Жоғары тәуекел":
            interventions.append("ML болжамы бойынша студент жоғары тәуекел тобында. Жеке оқу жоспары ұсынылады.")
        elif ml_summary["risk"] == "Орташа тәуекел":
            interventions.append("ML болжамы бойынша студент орташа тәуекелде. Жүйелі қайталау және бақылау қажет.")

    return render(request, "students/student_detail_dashboard.html", {
        "student": student,
        "submissions": submissions,
        "analyses": analyses[:10],
        "avg_percent": round(avg_percent, 2),
        "remedial_avg": round(remedial_avg, 2),
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests,
        "progress_labels": json.dumps(progress_labels, ensure_ascii=False),
        "progress_values": json.dumps(progress_values),
        "weak_topic_labels": json.dumps(weak_topic_labels, ensure_ascii=False),
        "weak_topic_values": json.dumps(weak_topic_values),
        "ml_summary": ml_summary,
        "interventions": interventions,
        "model_ready": model_ready(),
    })


# =========================================================
# Optional student CRUD
# =========================================================

@login_required
@teacher_required
def student_add(request):
    if request.method == "POST":
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Студент қосылды.")
            return redirect("student_list")
    else:
        form = StudentForm()

    return render(
        request,
        "students/student_form.html",
        {"form": form, "title": "Студент қосу", "model_ready": model_ready()},
    )


@login_required
@teacher_required
def student_edit(request, pk: int):
    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Өзгерістер сақталды.")
            return redirect("student_list")
    else:
        form = StudentForm(instance=student)

    return render(
        request,
        "students/student_form.html",
        {"form": form, "title": "Студентті өңдеу", "model_ready": model_ready()},
    )


@login_required
@teacher_required
def student_delete(request, pk: int):
    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        student.delete()
        messages.info(request, "Студент жойылды.")
        return redirect("student_list")

    return render(
        request,
        "students/student_delete.html",
        {"student": student, "model_ready": model_ready()},
    )


# =========================================================
# ML prediction
# =========================================================

@login_required
@teacher_required
def predict_student(request, pk: int):
    if not model_ready():
        messages.error(request, "Модель табылмады. Алдымен модельді оқытыңыз: python ml_models/train_models.py")
        return redirect("dashboard")

    student = get_object_or_404(Student, pk=pk)

    summary = predict_student_summary(student)
    pred = summary["label"]

    student.predicted_performance = pred
    student.save(update_fields=["predicted_performance"])

    messages.success(
        request,
        f"Болжам: {pred} | Келесі тесттің болжамды пайызы: {summary['predicted_score']}% | "
        f"Өту ықтималдығы: {round(summary['pass_probability'] * 100, 2)}% | "
        f"Тәуекел: {summary['risk']}"
    )
    return redirect("student_list")


@login_required
@teacher_required
def predict_all(request):
    if not model_ready():
        messages.error(request, "Модель табылмады. Алдымен модельді оқытыңыз: python ml_models/train_models.py")
        return redirect("dashboard")

    updated = 0
    for s in Student.objects.all():
        summary = predict_student_summary(s)
        s.predicted_performance = summary["label"]
        s.save(update_fields=["predicted_performance"])
        updated += 1

    messages.success(request, f"{updated} студент үшін ML болжам жаңартылды.")
    return redirect("student_list")


# =========================================================
# Analytics
# =========================================================

@login_required
@teacher_required
def analytics(request):
    students = list(Student.objects.all())

    perf_counts = {"Жоғары": 0, "Орташа": 0, "Төмен": 0}
    risk_counts = {"Тәуекел": 0, "Қалыпты": 0}
    avg_scores = {"labels": [], "values": []}

    for s in students:
        if s.predicted_performance:
            perf_counts[s.predicted_performance] += 1
        risk_counts[s.risk_status()] += 1
        avg_scores["labels"].append(s.name)
        avg_scores["values"].append(s.average_score())

    progress_labels = []
    progress_values = []

    submissions = (
        Submission.objects.select_related("student", "quiz")
        .filter(submitted_at__isnull=False)
        .order_by("submitted_at")
    )

    for sub in submissions:
        progress_labels.append(f"{sub.student.name} / {sub.quiz.title}")
        progress_values.append(float(sub.percent or 0))

    topic_counter = Counter()

    analyses = AIAnalysis.objects.select_related("student", "quiz").all()
    for a in analyses:
        if a.weak_topics_json:
            try:
                topics = json.loads(a.weak_topics_json)
                for t in topics:
                    if t:
                        topic_counter[t] += 1
            except Exception:
                pass

    weak_topic_labels = list(topic_counter.keys())
    weak_topic_values = list(topic_counter.values())

    remedial_groups = defaultdict(list)

    remedial_submissions = (
        Submission.objects.select_related("student", "quiz", "quiz__root_quiz")
        .filter(submitted_at__isnull=False)
        .order_by("submitted_at")
    )

    for sub in remedial_submissions:
        root_id = sub.quiz.root_quiz_id if sub.quiz.root_quiz_id else sub.quiz.id
        key = (sub.student.id, root_id)
        remedial_groups[key].append(sub)

    remedial_labels = []
    remedial_before = []
    remedial_after = []

    for _, subs in remedial_groups.items():
        if len(subs) >= 2:
            first_sub = subs[0]
            last_sub = subs[-1]

            label = f"{first_sub.student.name} / {first_sub.quiz.subject}"
            remedial_labels.append(label)
            remedial_before.append(float(first_sub.percent or 0))
            remedial_after.append(float(last_sub.percent or 0))

    avg_test_percent = sum(progress_values) / len(progress_values) if progress_values else 0

    remedial_gains = [after - before for before, after in zip(remedial_before, remedial_after)]
    avg_remedial_gain = sum(remedial_gains) / len(remedial_gains) if remedial_gains else 0

    passed_80_count = Submission.objects.filter(
        submitted_at__isnull=False,
        percent__gte=80
    ).count()

    top_weak_topic = topic_counter.most_common(1)[0][0] if topic_counter else "—"

    ml_prediction_rows = []
    pass_probabilities = []
    predicted_scores = []
    high_risk_students = []

    if model_ready():
        for student in students:
            try:
                summary = predict_student_summary(student)

                row = {
                    "student_name": student.name,
                    "predicted_score": float(summary["predicted_score"]),
                    "pass_probability": float(summary["pass_probability"]),
                    "risk": summary["risk"],
                    "label": summary["label"],
                }
                ml_prediction_rows.append(row)

                pass_probabilities.append(row["pass_probability"] * 100.0)
                predicted_scores.append(row["predicted_score"])

                if row["risk"] == "Жоғары тәуекел":
                    high_risk_students.append(student.name)
            except Exception:
                pass

    avg_next_pass_probability = round(
        sum(pass_probabilities) / len(pass_probabilities), 2
    ) if pass_probabilities else 0

    avg_predicted_score = round(
        sum(predicted_scores) / len(predicted_scores), 2
    ) if predicted_scores else 0

    high_risk_count = len(high_risk_students)

    context = {
        "perf_counts": perf_counts,
        "risk_counts": risk_counts,
        "avg_scores": avg_scores,
        "metrics": load_metrics(),
        "model_ready": model_ready(),

        "context_progress_labels": json.dumps(progress_labels, ensure_ascii=False),
        "context_progress_values": json.dumps(progress_values),

        "context_weak_topic_labels": json.dumps(weak_topic_labels, ensure_ascii=False),
        "context_weak_topic_values": json.dumps(weak_topic_values),

        "context_remedial_labels": json.dumps(remedial_labels, ensure_ascii=False),
        "context_remedial_before": json.dumps(remedial_before),
        "context_remedial_after": json.dumps(remedial_after),

        "avg_test_percent": round(avg_test_percent, 2),
        "avg_remedial_gain": round(avg_remedial_gain, 2),
        "passed_80_count": passed_80_count,
        "top_weak_topic": top_weak_topic,

        "avg_next_pass_probability": avg_next_pass_probability,
        "avg_predicted_score": avg_predicted_score,
        "high_risk_count": high_risk_count,
        "high_risk_students": high_risk_students[:10],
        "ml_prediction_rows": ml_prediction_rows[:20],
    }
    return render(request, "students/analytics.html", context)


# =========================================================
# Student dashboard
# =========================================================

@login_required
@student_required
def student_dashboard(request):
    student_profile = getattr(request.user, "student_profile", None)
    if not student_profile:
        return HttpResponseForbidden("Сіз студент аккаунтымен кірмедіңіз.")

    return render(request, "students/student_dashboard.html", {
        "student": student_profile,
        "model_ready": model_ready(),
    })


# =========================================================
# Teacher quiz views
# =========================================================

@login_required
@teacher_required
def quiz_list_teacher(request):
    quizzes = Quiz.objects.order_by("-created_at")
    return render(request, "students/quizzes/teacher_list.html", {"quizzes": quizzes, "model_ready": model_ready()})


@login_required
@teacher_required
def quiz_create(request):
    if request.method == "POST":
        form = QuizForm(request.POST)
        if form.is_valid():
            q = form.save(commit=False)
            q.created_by = request.user
            q.save()
            q.root_quiz = q
            q.save(update_fields=["root_quiz"])
            return redirect("quiz_edit", quiz_id=q.id)
    else:
        form = QuizForm()

    return render(request, "students/quizzes/quiz_form.html", {
        "form": form,
        "mode": "create",
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def quiz_edit(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)

    if request.method == "POST" and request.POST.get("action") == "save_quiz":
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            messages.success(request, "Тест сақталды.")
            return redirect("quiz_edit", quiz_id=quiz.id)
    else:
        form = QuizForm(instance=quiz)

    questions = quiz.questions.prefetch_related("choices").all()
    return render(
        request,
        "students/quizzes/quiz_edit.html",
        {"quiz": quiz, "form": form, "questions": questions, "model_ready": model_ready()},
    )


@login_required
@teacher_required
def question_add(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)

    if request.method == "POST":
        qf = QuestionForm(request.POST)
        if qf.is_valid():
            q = qf.save(commit=False)
            q.quiz = quiz
            q.save()
            messages.success(request, "Сұрақ қосылды.")
            return redirect("quiz_edit", quiz_id=quiz.id)
    else:
        qf = QuestionForm()

    return render(request, "students/quizzes/question_form.html", {
        "quiz": quiz,
        "form": qf,
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def choice_add(request, question_id):
    question = get_object_or_404(Question.objects.select_related("quiz"), id=question_id)

    if request.method == "POST":
        cf = ChoiceForm(request.POST)
        if cf.is_valid():
            c = cf.save(commit=False)
            c.question = question
            c.save()
            messages.success(request, "Жауап варианты қосылды.")
            return redirect("quiz_edit", quiz_id=question.quiz.id)
    else:
        cf = ChoiceForm()

    return render(request, "students/quizzes/choice_form.html", {
        "question": question,
        "form": cf,
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def quiz_results(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    subs = (
        Submission.objects.filter(quiz=quiz, submitted_at__isnull=False)
        .select_related("student")
        .order_by("-score")
    )
    return render(request, "students/quizzes/results.html", {
        "quiz": quiz,
        "subs": subs,
        "model_ready": model_ready(),
    })


# =========================================================
# Student quiz views
# =========================================================

@login_required
@student_required
def quiz_list_student(request):
    student = request.user.student_profile

    quizzes = (
        Quiz.objects.filter(is_active=True)
        .filter(models.Q(target_student__isnull=True) | models.Q(target_student=student))
        .order_by("-created_at")
    )

    taken_ids = set(
        Submission.objects.filter(student=student, submitted_at__isnull=False)
        .values_list("quiz_id", flat=True)
    )

    return render(
        request,
        "students/quizzes/student_list.html",
        {"quizzes": quizzes, "taken_ids": taken_ids, "model_ready": model_ready()},
    )


@login_required
@student_required
@transaction.atomic
def quiz_take(request, quiz_id):
    student = request.user.student_profile

    quiz = get_object_or_404(
        Quiz.objects.prefetch_related("questions__choices"),
        id=quiz_id,
        is_active=True,
    )

    questions = quiz.questions.all()

    submission, _ = Submission.objects.get_or_create(quiz=quiz, student=student)

    if submission.submitted_at:
        return render(
            request,
            "students/quizzes/student_done.html",
            {"quiz": quiz, "sub": submission, "model_ready": model_ready()},
        )

    if request.method == "POST":
        score = 0
        max_score = 0

        submission.answers.all().delete()

        for q in questions:
            max_score += q.points
            choice_id = request.POST.get(f"q_{q.id}")
            selected = None

            if choice_id:
                selected = Choice.objects.filter(id=choice_id, question=q).first()

            Answer.objects.create(
                submission=submission,
                question=q,
                selected_choice=selected,
            )

            if selected and selected.is_correct:
                score += q.points

        submission.score = score
        submission.max_score = max_score

        percent = (score / max_score * 100.0) if max_score else 0.0
        submission.percent = round(percent, 2)
        submission.passed = percent >= 80.0
        submission.submitted_at = timezone.now()

        root = quiz.root_quiz if quiz.root_quiz else quiz
        previous_attempts = Submission.objects.filter(
            student=student,
            quiz__root_quiz=root
        ).exclude(id=submission.id).count()

        submission.attempt_no = previous_attempts + 1
        submission.save()

        if not submission.passed:
            from .tasks import generate_remedial_for_submission
            generate_remedial_for_submission.delay(submission.id)

            messages.warning(
                request,
                "Нәтиже 80%-дан төмен. AI сізге әлсіз тақырыптар бойынша жаңа тест дайындап жатыр."
            )
        else:
            messages.success(
                request,
                "Құттықтаймыз! Сіздің нәтижеңіз 80%-дан асты."
            )

        return render(
            request,
            "students/quizzes/student_done.html",
            {"quiz": quiz, "sub": submission, "model_ready": model_ready()},
        )

    return render(
        request,
        "students/quizzes/student_take.html",
        {"quiz": quiz, "questions": questions, "model_ready": model_ready()},
    )


# =========================================================
# AI quiz generation
# =========================================================

@login_required
@teacher_required
def quiz_ai_create(request):
    if request.method == "POST":
        form = AIQuizRequestForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data["subject"]
            topic = form.cleaned_data["topic"]
            num_questions = form.cleaned_data["num_questions"]
            time_limit = form.cleaned_data["time_limit_minutes"]

            try:
                data = generate_mcq_from_topic(
                    subject=subject,
                    topic=topic,
                    n=num_questions,
                )
            except AIQuotaError as e:
                messages.error(request, str(e))
                return redirect("quiz_ai_create")

            quiz = Quiz.objects.create(
                title=f"{subject}: {topic} (AI)",
                description=f"AI генерацияланған тест. Пән: {subject}, тақырып: {topic}",
                is_active=True,
                time_limit_minutes=time_limit,
                quiz_type="ai",
                subject=subject,
                topic=topic,
                created_by=request.user,
                requested_question_count=num_questions,
                root_quiz=None,
                parent_quiz=None,
            )

            quiz.root_quiz = quiz
            quiz.save(update_fields=["root_quiz"])

            created_count = 0

            for q in data.get("questions", []):
                choices = q.get("choices", [])
                correct_count = sum(1 for c in choices if c.get("is_correct") is True)

                if correct_count != 1 or len(choices) != 4:
                    continue

                qq = Question.objects.create(
                    quiz=quiz,
                    text=q.get("text", "").strip(),
                    points=int(q.get("points", 1)),
                    topic=q.get("topic", topic),
                )

                for c in choices:
                    Choice.objects.create(
                        question=qq,
                        text=c.get("text", "").strip(),
                        is_correct=bool(c.get("is_correct")),
                    )

                created_count += 1

            messages.success(request, f"AI тест дайын болды ✅ Сақталған сұрақ саны: {created_count}")
            return redirect("quiz_edit", quiz_id=quiz.id)
    else:
        form = AIQuizRequestForm()

    return render(request, "students/quizzes/ai_create.html", {
        "form": form,
        "model_ready": model_ready(),
    })


# =========================================================
# Materials
# =========================================================

@login_required
@teacher_required
def material_list(request):
    materials = LessonMaterial.objects.order_by("-created_at")
    return render(request, "students/materials/list.html", {
        "materials": materials,
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def material_upload(request):
    if request.method == "POST":
        form = LessonMaterialForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save(commit=False)
            m.extracted_text = ""
            m.save()
            messages.success(request, "Материал жүктелді.")
            return redirect("material_list")
    else:
        form = LessonMaterialForm()

    return render(request, "students/materials/upload.html", {
        "form": form,
        "model_ready": model_ready(),
    })


@login_required
@teacher_required
def ai_quiz_from_material(request, material_id):
    material = get_object_or_404(LessonMaterial, id=material_id)

    if request.method == "POST":
        num_questions = int(request.POST.get("num_questions", "10"))
        time_limit = int(request.POST.get("time_limit_minutes", "20"))

        if not material.extracted_text:
            material.extracted_text = extract_text_from_file(material.file.path)
            material.save()

        try:
            data = generate_mcq_json(
                subject=material.subject,
                topic=material.topic,
                source_text=material.extracted_text,
                n=num_questions,
            )
        except AIQuotaError as e:
            messages.error(request, str(e))
            return redirect("ai_quiz_from_material", material_id=material.id)

        quiz = Quiz.objects.create(
            title=f"{material.subject}: {material.topic} (AI)",
            description=f"AI тест. Материал: {material.title}",
            is_active=True,
            time_limit_minutes=time_limit,
            quiz_type="ai",
            subject=material.subject,
            topic=material.topic,
            created_by=request.user,
            requested_question_count=num_questions,
            root_quiz=None,
            parent_quiz=None,
        )

        quiz.root_quiz = quiz
        quiz.save(update_fields=["root_quiz"])

        created_count = 0

        for q in data.get("questions", []):
            choices = q.get("choices", [])
            correct_count = sum(1 for c in choices if c.get("is_correct") is True)

            if correct_count != 1 or len(choices) != 4:
                continue

            qq = Question.objects.create(
                quiz=quiz,
                text=q.get("text", "").strip(),
                points=int(q.get("points", 1)),
                topic=q.get("topic", material.topic),
            )

            for c in choices:
                Choice.objects.create(
                    question=qq,
                    text=c.get("text", "").strip(),
                    is_correct=bool(c.get("is_correct")),
                )

            created_count += 1

        messages.success(request, f"PDF/Word арқылы AI тест жасалды ✅ Сақталған сұрақ саны: {created_count}")
        return redirect("quiz_edit", quiz_id=quiz.id)

    return render(request, "students/quizzes/ai_from_material.html", {
        "material": material,
        "model_ready": model_ready(),
    })