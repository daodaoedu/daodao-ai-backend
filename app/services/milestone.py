from models import Milestone
from sqlalchemy.orm import Session


def get_milestones_data(db: Session, project_id: int):
    return db.query(Milestone).filter(Milestone.project_id == project_id).all()
