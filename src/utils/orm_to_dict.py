from sqlalchemy.orm import class_mapper


def orm_to_dict(obj):
    return {
        column.key: getattr(obj, column.key)
        for column in class_mapper(obj.__class__).columns
    }
