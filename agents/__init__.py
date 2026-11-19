__all__ = ["root_agent"]


def __getattr__(name):
    # Factory/configuration imports must not construct the application singleton.
    if name == "root_agent":
        from .agent import root_agent
        return root_agent
    raise AttributeError(name)
