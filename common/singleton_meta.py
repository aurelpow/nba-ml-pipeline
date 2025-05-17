# This file contains the SingletonMeta class which is a metaclass that can be used to create singleton classes.
class SingletonMeta(type):
    """
    A metaclass that can be used to create singleton classes.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]