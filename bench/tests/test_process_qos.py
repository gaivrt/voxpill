from __future__ import annotations

import ctypes
import unittest

from process_qos import (
    PROCESS_POWER_THROTTLING,
    PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
    ProcessPowerThrottlingState,
    enable_high_qos,
)


class FakeCall:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeKernel32:
    def __init__(self, result=True):
        self.GetCurrentProcess = FakeCall(123)
        self.SetProcessInformation = FakeCall(result)


class ProcessQosTest(unittest.TestCase):
    def test_high_qos_clears_execution_speed_throttling(self):
        dll = FakeKernel32()
        logs = []

        self.assertTrue(
            enable_high_qos(logs.append, kernel32=dll, platform_name="nt")
        )

        handle, info_class, state_pointer, size = dll.SetProcessInformation.calls[0]
        state = ctypes.cast(
            state_pointer, ctypes.POINTER(ProcessPowerThrottlingState)
        ).contents
        self.assertEqual(handle, 123)
        self.assertEqual(info_class, PROCESS_POWER_THROTTLING)
        self.assertEqual(size, ctypes.sizeof(ProcessPowerThrottlingState))
        self.assertEqual(state.Version, 1)
        self.assertEqual(
            state.ControlMask, PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        )
        self.assertEqual(state.StateMask, 0)
        self.assertIn("HighQoS enabled", logs[0])

    def test_failure_is_logged_and_does_not_raise(self):
        logs = []

        self.assertFalse(
            enable_high_qos(
                logs.append,
                kernel32=FakeKernel32(result=False),
                platform_name="nt",
            )
        )

        self.assertIn("continuing", logs[0])


if __name__ == "__main__":
    unittest.main()
