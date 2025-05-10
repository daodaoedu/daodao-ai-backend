from sqlalchemy.orm import Session
from models import Project
from fastapi import HTTPException

def get_project_data(db: Session, project_id: int):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="找不到相關專案")
    return project
