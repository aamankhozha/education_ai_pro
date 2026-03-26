# Education AI (Django + SQLite + TensorFlow)

## 1) Орнату
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

## 2) Дерекқор
```bash
python manage.py migrate
python manage.py createsuperuser
```

## 3) ML модельді оқыту
Мысал датасетпен:
```bash
python ml_models/train_models.py
```
Нәтижесінде файлдар пайда болады:
- `ml_models/saved/tf_model.keras`
- `ml_models/saved/scaler.pkl`
- `ml_models/saved/labels.json`
- `ml_models/saved/metrics.json`

## 4) Серверді іске қосу
```bash
python manage.py runserver
```
Сайт:
- Login: http://127.0.0.1:8000/login/
- Dashboard: http://127.0.0.1:8000/

## 5) CSV жүктеу форматы
Міндетті бағандар:
- name, attendance, homework, midterm, final

Қосымша:
- group, actual_performance

## Ескерту
Бұл проект дипломға арналған демонстрациялық нұсқа. Production-қа шығарғанда:
- SECRET_KEY ауыстыру
- DEBUG=False
- ALLOWED_HOSTS нақтылау
