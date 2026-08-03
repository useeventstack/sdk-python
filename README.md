# useeventstack — Python SDK

Official Python SDK for [useEventStack](https://useeventstack.com), the Operational OS for Company Behavior.

## Install

```bash
pip install useeventstack
```

## Quick Start

```python
from useeventstack import UseEventStackClient

client = UseEventStackClient(
    api_key="useeventstack_your_key",
    base_url="https://api.useeventstack.com",
    organization_id="your-org-id",
)

# Emit an event
event = client.events.emit(
    "deployment.completed",
    payload={"service": "api", "version": "2.1.0", "environment": "production", "status": "healthy"},
)
print(f"Event: {event['event']['id']}")

# Query events
events = client.events.query(event_type="deployment.completed")

# Manage workflows
workflows = client.workflows.list()
```

## Async Usage (FastAPI / asyncio)

```python
from useeventstack import AsyncUseEventStackClient

async with AsyncUseEventStackClient(api_key="useeventstack_your_key") as client:
    event = await client.events.emit("customer.created", payload={"name": "Acme"})
```

## API Surface

| Namespace | Methods |
|-----------|---------|
| `client.events` | `emit()`, `query()`, `get()`, `trace()` |
| `client.workflows` | `list()`, `get()`, `create()`, `update()`, `delete()`, `enable()`, `disable()`, `query()` |
| `client.custom_actions` | `list()`, `get()`, `delete()`, `simulate()` |
| `client.replay` | `single()`, `bulk()` |
| `client.dlq` | `list()`, `reprocess(event_id)`, `clear()` |
| `client.api_keys` | `list()`, `create()`, `delete()` |
| `client.projections` | `query()`, `service_status()` |

## License

MIT
