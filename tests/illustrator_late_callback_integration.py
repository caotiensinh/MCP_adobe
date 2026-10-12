"""Exercise the installed Python bridge; never starts a socket or Adobe call."""
import asyncio
import base64
import hashlib
import json
import unittest
from unittest.mock import AsyncMock, patch

from illustrator_mcp.websocket_bridge import WebSocketBridge
from illustrator_mcp.execution.coordinator import ExecutionCoordinator, HostUnresolvedError


class LateCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.coordinator = ExecutionCoordinator()
        self.bridge = WebSocketBridge()
        self.bridge.loop = asyncio.get_running_loop()
        self.bridge._payload_capable = True
        self.bridge.server.is_connected = lambda: True
        self.bridge.server.send = AsyncMock()
        self.authority = patch('illustrator_mcp.execution.get_coordinator', return_value=self.coordinator)
        self.authority.start()
        self.addCleanup(self.authority.stop)

    async def timed_out_request(self):
        response = await self.bridge.execute_script_async('read_only_test()', timeout=0.02)
        self.assertEqual(response['execution'], 'unknown')
        request = json.loads(self.bridge.server.send.call_args_list[0].args[0])
        job = self.coordinator.get(request['jobId'])
        self.assertTrue(job.awaiting_host)
        return request, job

    async def deliver(self, request, *, corrupt=False):
        raw = b'{"ok":true,"data":{"documentName":"fixture.ai"}}'
        descriptor = dict(version=1, jobId=request['jobId'], requestId=request['id'],
            requestToken=request['requestToken'], sessionId=request['transport']['sessionId'],
            hostSession='test-host-epoch', documentId='test-document',
            payloadId=request['transport']['payloadId'], encoding='utf-8', byteLength=len(raw),
            digestAlgorithm='sha256', digest=hashlib.sha256(raw).hexdigest(),
            transferMode='pages', pageBytes=12288)
        frame = dict(id=request['id'], requestToken=request['requestToken'])
        await self.bridge._handle_message(json.dumps(dict(frame, type='payload_descriptor', descriptor=descriptor)))
        delivered = raw[:-1] + b'X' if corrupt else raw
        await self.bridge._handle_message(json.dumps(dict(frame, type='payload_chunk',
            payloadId=descriptor['payloadId'], offset=0, data=base64.b64encode(delivered).decode())))
        await self.bridge._handle_message(json.dumps(dict(frame, type='complete')))
        await asyncio.sleep(0)

    async def test_verified_late_result_releases_execution_fence_without_replaying(self):
        request, job = await self.timed_out_request()
        await self.deliver(request)
        self.assertFalse(job.awaiting_host)
        self.assertEqual(job.outcome_source, 'late_host_callback')
        self.assertEqual(job.result['hostRequestResult']['integrity']['status'], 'verified')
        self.coordinator.assert_host_available()
        dispatches = [json.loads(c.args[0]) for c in self.bridge.server.send.call_args_list]
        self.assertEqual(sum('script' in d for d in dispatches), 1)

    async def test_corrupt_late_result_remains_unknown_and_blocks_new_dispatch(self):
        request, job = await self.timed_out_request()
        await self.deliver(request, corrupt=True)
        self.assertTrue(job.awaiting_host)
        with self.assertRaises(HostUnresolvedError):
            self.coordinator.assert_host_available()
        self.assertIn('digest_mismatch', job.error)

    async def test_idle_heartbeat_cannot_release_an_unresolved_request(self):
        request, job = await self.timed_out_request()
        await self.bridge._handle_message(json.dumps(dict(type='heartbeat', busy=False,
            activeRequestId=None, capabilities=['payload-v1'])))
        self.assertTrue(job.awaiting_host)
        self.assertFalse(self.bridge.get_panel_health()['busy'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
