import asyncio

from src.app.context import get_request_id, new_request_id, request_scope


def test_new_request_id_is_prefixed():
    rid = new_request_id()
    assert rid.startswith("req_")
    assert len(rid) == 4 + 8


def test_scope_sets_and_resets_context():
    assert get_request_id() is None
    with request_scope(request_id="req-1", operation="seed"):
        assert get_request_id() == "req-1"
    assert get_request_id() is None


def test_nested_scopes_merge_fields():
    with request_scope(request_id="req-1"):
        with request_scope(operation="seed"):
            from src.app.context import get_context

            ctx = get_context()
            assert ctx["request_id"] == "req-1"
            assert ctx["operation"] == "seed"


def test_concurrent_tasks_do_not_leak_context():
    async def worker(i: int) -> str:
        rid = new_request_id()
        with request_scope(request_id=rid):
            for _ in range(5):
                await asyncio.sleep(0)  # force interleaving
            assert get_request_id() == rid
            return rid

    async def main():
        return await asyncio.gather(*[worker(i) for i in range(10)])

    results = asyncio.run(main())
    assert len(results) == 10
    assert all(r.startswith("req_") for r in results)
    assert len(set(results)) == 10