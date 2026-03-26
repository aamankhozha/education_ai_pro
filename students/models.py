from django.conf import settings
from django.db import models


class Student(models.Model):
    PERFORMANCE_CHOICES = [
        ("Жоғары", "Жоғары"),
        ("Орташа", "Орташа"),
        ("Төмен", "Төмен"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )
    name = models.CharField(max_length=150)
    group = models.CharField(max_length=50, blank=True, default="")
    can_access_platform = models.BooleanField(default=False)

    predicted_performance = models.CharField(
        max_length=20,
        choices=PERFORMANCE_CHOICES,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def average_score(self) -> float:
        subs = self.submissions.filter(submitted_at__isnull=False)
        if not subs.exists():
            return 0.0
        return round(sum(float(s.percent or 0) for s in subs) / subs.count(), 2)

    def risk_status(self) -> str:
        subs = self.submissions.filter(submitted_at__isnull=False).order_by("-submitted_at")
        if not subs.exists():
            return "Қалыпты"

        last_sub = subs.first()
        avg_percent = self.average_score()

        if float(last_sub.percent or 0) < 50 or avg_percent < 60:
            return "Тәуекел"
        return "Қалыпты"

    def __str__(self):
        return self.name


class Quiz(models.Model):
    QUIZ_TYPE_CHOICES = [
        ("manual", "Manual"),
        ("ai", "AI"),
        ("remedial", "Remedial"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    subject = models.CharField(max_length=120, blank=True, default="")
    topic = models.CharField(max_length=200, blank=True, default="")

    quiz_type = models.CharField(max_length=20, choices=QUIZ_TYPE_CHOICES, default="manual")
    is_active = models.BooleanField(default=True)
    time_limit_minutes = models.PositiveIntegerField(default=20)
    requested_question_count = models.PositiveIntegerField(default=10)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_quizzes",
    )

    target_student = models.ForeignKey(
        "Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_quizzes",
    )

    parent_quiz = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remedials",
    )

    root_quiz = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="descendant_quizzes",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    topic = models.CharField(max_length=200, blank=True, default="")
    points = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.text[:80]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text[:80]


class Submission(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="submissions")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="submissions")

    score = models.FloatField(default=0)
    max_score = models.FloatField(default=0)
    percent = models.FloatField(default=0)
    passed = models.BooleanField(default=False)

    attempt_no = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at", "-created_at"]

    def __str__(self):
        return f"{self.student.name} - {self.quiz.title}"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"Answer #{self.id}"


class LessonMaterial(models.Model):
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=120, blank=True, default="")
    topic = models.CharField(max_length=200, blank=True, default="")
    file = models.FileField(upload_to="materials/")
    extracted_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class AIAnalysis(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    percent = models.FloatField(default=0.0)
    weak_topics_json = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.name} / {self.quiz.title}"