__all__ = ["master_agent"]


def __getattr__(name):
    if name == "master_agent":
        from .agent import master_agent
        return master_agent
    raise AttributeError(name)
