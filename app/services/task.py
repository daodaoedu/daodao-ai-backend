from sqlalchemy.orm import Session
from models import Task
from sqlalchemy import func, case

def get_tasks_stats(db: Session, milestone_ids: list[int]):
    if not milestone_ids:
        return {'total': 0, 'completed': 0}

    stats = db.query(
        func.count(Task.id).label('total'),
        func.sum(case((Task.is_completed == True, 1), else_=0)).label('completed')

    ).filter(Task.milestone_id.in_(milestone_ids)).first()

    return {
        'total': stats.total or 0,
        'completed': stats.completed or 0
    }
