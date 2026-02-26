print('starting debug script')
import asyncio
from live_executor import LiveExecutor

async def run_test():
    import inspect
    print('run_test source:\n', inspect.getsource(run_test))
    print('in run_test start')
    executor = LiveExecutor()
    print('created executor')
    print('about to request approval')
    ok,msg = await executor.request_live_approval(user_confirmation=True)
    print('approval result', ok, msg)
    print('about to place order')
    success, oid, details = await executor.place_order('BTC/USDT','buy',0.001,10000)
    print('order result', success, oid)
    print('about to close position', oid)
    ok, closed = await executor.close_position(oid,10500)
    print('closed result', ok, closed)
    print('about to emergency close')
    result = await executor.emergency_close_all()
    print('emergency result', result)

asyncio.run(run_test())
