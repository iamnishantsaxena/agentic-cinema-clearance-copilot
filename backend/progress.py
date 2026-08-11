import asyncio

# ponytail: queues are never evicted after a stream finishes; fine at demo
# scale (one process, short-lived jobs), add a TTL sweep if this runs long-lived.
_queues: dict[str, asyncio.Queue] = {}


def get_queue(report_id: str) -> asyncio.Queue:
    return _queues.setdefault(report_id, asyncio.Queue())


async def publish(report_id: str, message: str) -> None:
    await get_queue(report_id).put(message)


async def close(report_id: str) -> None:
    await get_queue(report_id).put(None)


if __name__ == "__main__":

    async def main():
        rid = "test"
        await publish(rid, "step 1")
        await publish(rid, "step 2")
        await close(rid)
        q = get_queue(rid)
        messages = []
        while True:
            msg = await q.get()
            if msg is None:
                break
            messages.append(msg)
        assert messages == ["step 1", "step 2"], messages
        print("ok")

    asyncio.run(main())
