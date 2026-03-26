import json
import os

from openai import OpenAI, RateLimitError, OpenAIError


class AIQuotaError(Exception):
    pass


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AIQuotaError(
            "OPENAI_API_KEY табылмады. .env немесе environment variables ішіне OPENAI_API_KEY қосыңыз."
        )
    return OpenAI(api_key=api_key)


def _safe_json_loads(text: str) -> dict:
    text = text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "", 1).strip()
    if text.startswith("```"):
        text = text.replace("```", "", 1).strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    return json.loads(text)


def generate_mcq_json(subject: str, topic: str, source_text: str, n: int = 10) -> dict:
    client = get_openai_client()

    prompt = f"""
Сен мұғалімге арналған тест генераторысың.

Пән: {subject}
Тақырып: {topic}

Төмендегі материалдан ғана сүйеніп, {n} сұрақтан тұратын MCQ тест жаса.

Талаптар:
- Әр сұрақта 4 вариант болсын
- Тек 1 дұрыс жауап болсын
- Сұрақтар нақты, түсінікті, қайшылықсыз болсын
- Placeholder қолданба ("Дұрыс жауап", "Қате жауап A" т.б. болмайды)
- Тек материалға негізделген болсын
- Нәтижені тек JSON ретінде қайтар

JSON форматы:
{{
  "questions":[
    {{
      "text":"Сұрақ мәтіні",
      "topic":"{topic}",
      "points":1,
      "choices":[
        {{"text":"Дұрыс жауап","is_correct":true}},
        {{"text":"Вариант 2","is_correct":false}},
        {{"text":"Вариант 3","is_correct":false}},
        {{"text":"Вариант 4","is_correct":false}}
      ]
    }}
  ]
}}

Материал:
\"\"\"{source_text[:12000]}\"\"\"
"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        return _safe_json_loads(resp.output_text)

    except RateLimitError as e:
        raise AIQuotaError("OpenAI квота/баланс жоқ. Billing қосыңыз немесе кредит толтырыңыз.") from e
    except OpenAIError as e:
        raise AIQuotaError(f"OpenAI қатесі: {str(e)}") from e


def generate_mcq_from_topic(subject: str, topic: str, n: int = 10) -> dict:
    client = get_openai_client()

    prompt = f"""
Сен университет мұғаліміне арналған тест генераторысың.

Пән: {subject}
Тақырып: {topic}

Міндет:
Осы тақырып бойынша {n} сұрақтан тұратын сапалы MCQ тест жаса.

Талаптар:
- Әр сұрақта 4 жауап варианты болсын
- Тек 1 дұрыс жауап болсын
- Placeholder қолданба ("Дұрыс жауап", "Қате жауап A/B/C" болмайды)
- Нақты, мағыналы, оқу процесіне жарамды сұрақтар болсын
- Нәтижені тек JSON форматында қайтар

JSON форматы:
{{
  "questions":[
    {{
      "text":"Сұрақ мәтіні",
      "topic":"{topic}",
      "points":1,
      "choices":[
        {{"text":"Дұрыс жауап","is_correct":true}},
        {{"text":"Вариант 2","is_correct":false}},
        {{"text":"Вариант 3","is_correct":false}},
        {{"text":"Вариант 4","is_correct":false}}
      ]
    }}
  ]
}}
"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        return _safe_json_loads(resp.output_text)

    except RateLimitError as e:
        raise AIQuotaError("OpenAI квота/баланс жоқ. Billing қосыңыз немесе кредит толтырыңыз.") from e
    except OpenAIError as e:
        raise AIQuotaError(f"OpenAI қатесі: {str(e)}") from e


def infer_weak_topics(subject: str, original_topic: str, wrong_questions: list[str]):
    client = get_openai_client()

    prompt = f"""
Пән: {subject}
Бастапқы тақырып: {original_topic}

Студент қате жауап берген сұрақтар тізімі:
{wrong_questions}

Міндет:
- Қателерге қарап 1-5 әлсіз тақырып (subtopics) шығар
- Нәтижені тек JSON қайтар

JSON:
{{"weak_topics":["...","..."]}}
"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        return _safe_json_loads(resp.output_text)

    except RateLimitError as e:
        raise AIQuotaError("OpenAI квота/баланс жоқ. Billing қосыңыз немесе кредит толтырыңыз.") from e
    except OpenAIError as e:
        raise AIQuotaError(f"OpenAI қатесі: {str(e)}") from e


def generate_mcq_from_weak_topics(subject: str, weak_topics: list[str], n: int, difficulty: str = "medium") -> dict:
    client = get_openai_client()

    topics_text = ", ".join(weak_topics)

    difficulty_instruction = {
        "easy": "Сұрақтар жеңіл деңгейде болсын. Негізгі ұғымдар мен қарапайым түсініктерге сүйен.",
        "medium": "Сұрақтар орташа деңгейде болсын. Теория мен қолдануды бірге тексер.",
        "hard": "Сұрақтар күрделі деңгейде болсын. Терең түсіну мен талдауды қажет етсін.",
    }.get(difficulty, "Сұрақтар орташа деңгейде болсын.")

    prompt = f"""
Сен университет мұғаліміне көмектесетін AI тест генераторысың.

Пән: {subject}
Әлсіз тақырыптар: {topics_text}
Қиындық деңгейі: {difficulty}

Міндет:
Студент қате жіберген осы тақырыптар бойынша {n} сұрақтан тұратын жаңа MCQ тест жаса.

Талаптар:
- Әр сұрақта 4 жауап варианты болсын
- Тек 1 дұрыс жауап болсын
- Сұрақтар тек әлсіз тақырыптарға байланысты болсын
- Placeholder қолданба
- Нақты, мағыналы, оқу процесіне жарамды жауаптар жаз
- {difficulty_instruction}
- Нәтижені тек JSON форматында қайтар

JSON форматы:
{{
  "questions":[
    {{
      "text":"Сұрақ мәтіні",
      "topic":"әлсіз тақырып атауы",
      "points":1,
      "choices":[
        {{"text":"Дұрыс жауап","is_correct":true}},
        {{"text":"Вариант 2","is_correct":false}},
        {{"text":"Вариант 3","is_correct":false}},
        {{"text":"Вариант 4","is_correct":false}}
      ]
    }}
  ]
}}
"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        return _safe_json_loads(resp.output_text)

    except RateLimitError as e:
        raise AIQuotaError("OpenAI квота/баланс жоқ. Billing қосыңыз немесе кредит толтырыңыз.") from e
    except OpenAIError as e:
        raise AIQuotaError(f"OpenAI қатесі: {str(e)}") from e