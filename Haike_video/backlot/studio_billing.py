"""Video billing policy; provider quote ceilings and durable intents stay intact."""
from backlot.work_catalog import WorkError

ACTUAL_USAGE = 'actual_usage'


def authorization(maximum=None):
    if maximum is None:
        return {'billing_policy': ACTUAL_USAGE, 'max_charge_micros': None}
    # Only frozen legacy submissions retain their explicit aggregate limit.
    if type(maximum) is not int or not 1 <= maximum <= 1_000_000_000:
        raise WorkError('原制作费用上限无效，请重新提交制作')
    return {'billing_policy': 'limited', 'max_charge_micros': maximum}


def check_total(request, total):
    if request.get('billing_policy') == ACTUAL_USAGE:
        return
    maximum = request.get('max_charge_micros')
    if maximum is None:
        raise WorkError('原制作计费授权缺失，请从创作任务继续制作')
    authorization(maximum)
    if total > maximum:
        raise WorkError('后续报价与原调用合计超过原制作上限，已完成内容保留，可继续原任务', 'budget_exceeded')
