from sqlalchemy.orm import Session
from models import Milestone

def get_milestones_data(db: Session, project_id: int):
    return db.query(Milestone).filter(Milestone.project_id == project_id).all()
