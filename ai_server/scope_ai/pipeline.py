\
\
\
\
\
   
from .workflow import (prepare_submission, edit_submission, confirm_submission,
                       finish_confirmation, start_secondary_review)


def run_submission_pipeline(story_id, submission_number, submission_text, *, top_k=5, data_root=None):
                                                                                   
    return prepare_submission(story_id, submission_number, submission_text, data_root=data_root)
