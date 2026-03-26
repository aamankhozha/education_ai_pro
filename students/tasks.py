from celery import shared_task
from .models import Submission
from .services.adaptive_service import analyze_and_generate_remedial


@shared_task
def generate_remedial_for_submission(submission_id: int):
    try:
        submission = Submission.objects.select_related("student", "quiz").get(id=submission_id)
        analyze_and_generate_remedial(submission)
        return f"Remedial quiz generated for submission {submission_id}"
    except Submission.DoesNotExist:
        return f"Submission {submission_id} not found"
    except Exception as e:
        return f"Error: {str(e)}"