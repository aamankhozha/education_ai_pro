import json
from collections import Counter

from django.db import transaction

from students.models import AIAnalysis, Answer, Choice, Question, Quiz, Submission
from students.services.openai_service import (
    AIQuotaError,
    generate_mcq_from_weak_topics,
    infer_weak_topics,
)
from students.services_ml import predict_student_summary, recommend_difficulty_from_prediction


def _extract_wrong_topics(submission: Submission) -> list[str]:
    """
    Студент қате жіберген сұрақтардың topic өрістерін жинайды.
    """
    wrong_topics = []

    answers = (
        Answer.objects.filter(submission=submission)
        .select_related("question", "selected_choice")
    )

    for answer in answers:
        if not answer.selected_choice or not answer.selected_choice.is_correct:
            topic = (answer.question.topic or submission.quiz.topic or "").strip()
            if topic:
                wrong_topics.append(topic)

    return wrong_topics


def _extract_wrong_questions(submission: Submission) -> list[str]:
    """
    Қате жауап берілген сұрақ мәтіндерін жинайды.
    """
    wrong_questions = []

    answers = (
        Answer.objects.filter(submission=submission)
        .select_related("question", "selected_choice")
    )

    for answer in answers:
        if not answer.selected_choice or not answer.selected_choice.is_correct:
            if answer.question and answer.question.text:
                wrong_questions.append(answer.question.text.strip())

    return wrong_questions


def _fallback_topics(submission: Submission) -> list[str]:
    """
    Егер OpenAI әлсіз тақырыптарды анықтай алмаса,
    қате сұрақтардың topic өрістерінен жиілік бойынша аламыз.
    """
    wrong_topics = _extract_wrong_topics(submission)

    if not wrong_topics:
        return [submission.quiz.topic] if submission.quiz.topic else ["Қайталау"]

    freq = Counter(wrong_topics)
    return [topic for topic, _ in freq.most_common(3)]


@transaction.atomic
def analyze_and_generate_remedial(submission: Submission):
    """
    Егер submission < 80% болса:
    - weak topics анықтайды
    - AIAnalysis кестесіне сақтайды
    - жаңа remedial quiz жасайды

    Егер remedial already бар болса, қайталап жасамайды.
    """
    quiz = submission.quiz
    student = submission.student

    # Егер студент 80%-дан асса — remedial керек емес
    if submission.passed:
        return None

    # Бастапқы түбір тестті анықтаймыз
    root_quiz = quiz.root_quiz if getattr(quiz, "root_quiz", None) else quiz

    # Егер осы root_quiz бойынша студентке актив remedial already бар болса — қайталап жасамаймыз
    existing = None

    active_remedials = Quiz.objects.filter(
        target_student=student,
        root_quiz=root_quiz,
        is_active=True,
        quiz_type="remedial",
    )

    for rq in active_remedials:
        sub = Submission.objects.filter(quiz=rq, student=student).first()

        if sub is None or sub.submitted_at is None:
            existing = rq
            break

    if existing:
        return existing

    # Қате сұрақтар мәтінін аламыз
    wrong_questions = _extract_wrong_questions(submission)

    # OpenAI арқылы weak topics анықтау
    weak_topics = []
    try:
        if wrong_questions:
            ai_result = infer_weak_topics(
                subject=quiz.subject,
                original_topic=quiz.topic,
                wrong_questions=wrong_questions,
            )
            weak_topics = ai_result.get("weak_topics", [])
    except Exception:
        weak_topics = []

    # Егер OpenAI ештеңе бермесе — fallback логика
    if not weak_topics:
        weak_topics = _fallback_topics(submission)

    # AIAnalysis кестесіне сақтаймыз
    AIAnalysis.objects.create(
        student=student,
        quiz=quiz,
        percent=submission.percent,
        weak_topics_json=json.dumps(weak_topics, ensure_ascii=False),
    )

    # Бастапқы параметрлерді root_quiz-тен аламыз
    question_count = getattr(root_quiz, "requested_question_count", None) or 10
    time_limit = root_quiz.time_limit_minutes or quiz.time_limit_minutes or 20

    # ML recommendation engine
    difficulty = "medium"
    predicted_score = 0.0
    pass_probability = 0.0

    try:
        ml_summary = predict_student_summary(student)
        predicted_score = float(ml_summary["predicted_score"])
        pass_probability = float(ml_summary["pass_probability"])
        difficulty = recommend_difficulty_from_prediction(predicted_score)
    except Exception:
        difficulty = "medium"

    # Жаңа remedial quiz жасаймыз
    remedial_quiz = Quiz.objects.create(
        title=f"Қайталау тесті: {quiz.subject} / {', '.join(weak_topics[:2])} ({difficulty})",
        description=(
            "AI студенттің әлсіз тақырыптары бойынша автоматты түрде құрған тест. "
            f"Ұсынылған difficulty: {difficulty}. "
            f"ML predicted_score: {round(predicted_score, 2)}%, "
            f"pass_probability: {round(pass_probability * 100, 2)}%"
        ),
        is_active=True,
        time_limit_minutes=time_limit,
        quiz_type="remedial",
        subject=quiz.subject,
        topic=", ".join(weak_topics),
        parent_quiz=quiz,
        root_quiz=root_quiz,
        target_student=student,
        created_by=getattr(quiz, "created_by", None),
        requested_question_count=question_count,
    )

    # OpenAI арқылы remedial сұрақтар генерация
    try:
        data = generate_mcq_from_weak_topics(
            subject=quiz.subject,
            weak_topics=weak_topics,
            n=question_count,
            difficulty=difficulty,
        )
    except AIQuotaError:
        data = {"questions": []}

    created_count = 0

    for q in data.get("questions", []):
        choices = q.get("choices", [])
        correct_count = sum(1 for c in choices if c.get("is_correct") is True)

        # тек 4 вариант, 1 дұрыс жауап
        if correct_count != 1 or len(choices) != 4:
            continue

        new_question = Question.objects.create(
            quiz=remedial_quiz,
            text=q.get("text", "").strip(),
            points=int(q.get("points", 1)),
            topic=q.get("topic", remedial_quiz.topic),
        )

        for c in choices:
            Choice.objects.create(
                question=new_question,
                text=c.get("text", "").strip(),
                is_correct=bool(c.get("is_correct")),
            )

        created_count += 1

    return remedial_quiz if created_count > 0 else None