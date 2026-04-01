from prefect import flow, task


@task
def hello_world_task():
    """Simple task that logs a message."""
    print("Hello from Prefect! 🎉")
    return "Hello, World!"


@flow
def hello_world():
    """Simple hello-world flow to verify Prefect server connection."""
    result = hello_world_task()
    print(f"Flow result: {result}")
    return result


if __name__ == "__main__":
    hello_world()
