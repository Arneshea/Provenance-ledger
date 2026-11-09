"""A tiny application to package; the ledger itself does not execute artifacts."""


def greeting(name):
    return f"Hello, {name}! This application has verified provenance."


if __name__ == "__main__":
    print(greeting("faculty"))
