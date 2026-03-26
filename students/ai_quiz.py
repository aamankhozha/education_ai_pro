import random
from django.db import transaction
from .models import Quiz, Question, Choice

def _make_mcq(question_text: str, correct: str, wrongs: list[str], topic: str, points: int = 1):
    """1 дұрыс + 3 қате жауап. Қате жауаптар shuffle."""
    all_choices = [(correct, True)] + [(w, False) for w in wrongs]
    random.shuffle(all_choices)
    return question_text, topic, points, all_choices

@transaction.atomic
def generate_ai_quiz(teacher, subject: str, topic: str, num_questions: int, time_limit: int) -> Quiz:
    quiz = Quiz.objects.create(
        title=f"{subject}: {topic} (AI тест)",
        description=f"AI генерацияланған тест. Пән: {subject}. Тақырып: {topic}.",
        is_active=True,
        time_limit_minutes=time_limit,
        quiz_type="ai",
        subject=subject,
        topic=topic,
        created_by=teacher,
    )

    # 1) Егер банкте дайын сұрақтар болса (сол тақырып бойынша бұрынғы тесттерден):
    bank = (Question.objects
            .filter(topic__icontains=topic)
            .exclude(quiz=quiz)
            .order_by("?")[:num_questions])

    picked = list(bank)

    # 2) Егер жетпесе — template сұрақтар қосамыз
    need = num_questions - len(picked)

    for q in picked:
        # банктен алған сұрақты көшіріп саламыз (Choices бірге)
        new_q = Question.objects.create(quiz=quiz, text=q.text, points=q.points, topic=q.topic)
        for c in q.choices.all():
            Choice.objects.create(question=new_q, text=c.text, is_correct=c.is_correct)

    for i in range(need):
        # қарапайым AI шаблон (кейін TensorFlow/LLM қосуға болады)
        qtext, qtopic, pts, choices = _make_mcq(
            question_text=f"{topic} бойынша негізгі ұғым #{i+1}. Дұрыс анықтаманы таңдаңыз.",
            correct="Дұрыс жауап (AI)",
            wrongs=["Қате жауап A", "Қате жауап B", "Қате жауап C"],
            topic=topic,
            points=1
        )
        qq = Question.objects.create(quiz=quiz, text=qtext, points=pts, topic=qtopic)
        for text, is_correct in choices:
            Choice.objects.create(question=qq, text=text, is_correct=is_correct)

    return quiz

from django.utils import timezone
from .models import Submission, Answer

@transaction.atomic
def generate_remedial_quiz(submission: Submission) -> Quiz:
    quiz = submission.quiz
    student = submission.student

    # Қате жауап берген сұрақтар:
    wrong_answers = (Answer.objects
                     .filter(submission=submission)
                     .select_related("question", "selected_choice"))

    wrong_topics = []
    for a in wrong_answers:
        # дұрыс таңдалмады немесе бос
        if not a.selected_choice or not a.selected_choice.is_correct:
            t = (a.question.topic or quiz.topic or "").strip()
            if t:
                wrong_topics.append(t)

    # Егер topic бос болса — fallback
    if not wrong_topics:
        wrong_topics = [quiz.topic or "Қайталау тақырып"]

    # Ең көп кездескен 1-2 topic аламыз
    # (simple frequency)
    freq = {}
    for t in wrong_topics:
        freq[t] = freq.get(t, 0) + 1
    top_topics = [k for k, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:2]]

    remedial = Quiz.objects.create(
        title=f"Қайта тест (80% үшін): {quiz.title}",
        description="AI қате тақырыптар бойынша қайта тест құрды.",
        is_active=True,
        time_limit_minutes=quiz.time_limit_minutes,
        quiz_type="remedial",
        subject=quiz.subject,
        topic=", ".join(top_topics),
        parent_quiz=quiz,
        target_student=student,
        created_by=quiz.created_by,
    )

    # Әр topic бойынша 5 сұрақтан (барлығы ~10)
    per_topic = 5
    for t in top_topics:
        bank = (Question.objects
                .filter(topic__icontains=t)
                .order_by("?")[:per_topic])

        if bank:
            for q in bank:
                new_q = Question.objects.create(quiz=remedial, text=q.text, points=q.points, topic=q.topic)
                for c in q.choices.all():
                    Choice.objects.create(question=new_q, text=c.text, is_correct=c.is_correct)
        else:
            # банк жоқ болса — template
            for i in range(per_topic):
                qtext, qtopic, pts, choices = _make_mcq(
                    question_text=f"{t} бойынша қайталау сұрағы #{i+1}. Дұрысын таңдаңыз.",
                    correct="Дұрыс жауап (AI)",
                    wrongs=["Қате жауап A", "Қате жауап B", "Қате жауап C"],
                    topic=t,
                    points=1
                )
                qq = Question.objects.create(quiz=remedial, text=qtext, points=pts, topic=qtopic)
                for text, is_correct in choices:
                    Choice.objects.create(question=qq, text=text, is_correct=is_correct)

    return remedial