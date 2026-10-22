"""Platform-funded chat trials: count accepted attempts in the same transaction."""
from datetime import datetime, timedelta, timezone

from .store import Problem, now

USER_DAILY = 50
GLOBAL_DAILY = 50


def enabled(rule):
    return rule.get("billing_policy") == "sponsored"


def record(db, user_id, job_id):
    day = datetime.fromisoformat(now()).astimezone(timezone(timedelta(hours=8))).date().isoformat()
    user_count = db.execute("SELECT count(*) FROM gateway_trial_calls WHERE day=? AND user_id=?", (day, user_id)).fetchone()[0]
    total = db.execute("SELECT count(*) FROM gateway_trial_calls WHERE day=?", (day,)).fetchone()[0]
    if user_count >= USER_DAILY or total >= GLOBAL_DAILY:
        raise Problem(429, "trial_limit", "今日 AI 赞助试用调用已达上限，请明日继续；未发起供应商请求")
    db.execute("INSERT INTO gateway_trial_calls VALUES(?,?,?,?)", (job_id, user_id, day, now()))
