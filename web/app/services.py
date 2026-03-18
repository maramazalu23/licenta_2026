import json
import uuid

from app import db
from app.models import EvaluationResult


def save_evaluation(input_payload, result_payload):
    token = uuid.uuid4().hex[:16]

    row = EvaluationResult(
        token=token,
        input_json=json.dumps(input_payload, ensure_ascii=False),
        result_json=json.dumps(result_payload, ensure_ascii=False),
    )
    db.session.add(row)
    db.session.commit()

    return row


def get_evaluation_by_token(token):
    row = EvaluationResult.query.filter_by(token=token).first()
    if not row:
        return None

    return {
        "id": row.id,
        "token": row.token,
        "created_at": row.created_at,
        "input": json.loads(row.input_json),
        "result": json.loads(row.result_json),
    }