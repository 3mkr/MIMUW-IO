import functools

from sqlalchemy import Column, create_engine, Date, Numeric, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Refund(Base):
    __tablename__ = 'refunds'

    ean = Column(String(13), primary_key=True)
    announcement_date = Column(Date, primary_key=True)
    refund_level = Column(String, primary_key=True)
    active_ingredient = Column(String, nullable=False)
    form = Column(String, nullable=False)
    dose = Column(String, nullable=False)
    unit_price = Column(Numeric(8, 4), nullable=False)
    description_label = Column(String, nullable=False)
    description_dropdown = Column(String, nullable=False)
    description_list_item = Column(String, nullable=False)



engine = create_engine('postgres://io_user:io_password@localhost/io_database')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def provide_session(function):
    @functools.wraps(function)
    def wrapped_function(*args, **kwargs):
        session = Session()
        try:
            return function(session=Session(), *args, **kwargs)
        finally:
            session.close()  # pylint: disable=no-member
    return wrapped_function
